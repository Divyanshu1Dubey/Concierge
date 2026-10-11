"""Overnight QA: attribution edge cases, analytics boundaries, confirmation links across DST,
inbound email parsing and the 'patient replied' follow-up."""
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentOffer
from apps.conversations.models import Conversation
from apps.emails.inbound import _plain_body, ingest_email_message
from apps.emails.models import Email, EmailThread
from apps.growth import analytics, attribution, followups
from apps.growth.models import FollowUpTask, InquiryAttribution, SmsMessage
from apps.practices.models import Practice

C = attribution.classify


@pytest.mark.parametrize('url,ref,channel', [
    ('https://p.test/?utm_source=Google&utm_medium=CPC', '', 'google_ads'),
    ('https://p.test/?UTM_SOURCE=news&UTM_MEDIUM=Email', '', 'email'),
    ('https://p.test/?utm_source=facebook&utm_medium=paid_social', '', 'paid_social'),
    ('https://p.test/?utm_source=ig&utm_medium=social', '', 'social'),
    ('https://p.test/?msclkid=abc', 'https://www.bing.com/', 'organic_search'),  # Microsoft click id is not Google Ads
    ('https://p.test/', 'https://www.google.co.uk/', 'organic_search'),
    ('https://p.test/', 'https://WWW.GOOGLE.COM/search?q=dentist', 'organic_search'),
    ('https://p.test/', 'https://perplexity.ai/search', 'ai_assistant'),
    ('https://p.test/', 'https://gemini.google.com/app', 'ai_assistant'),
    ('https://p.test/', 'android-app://com.google.android.gm/', 'email'),
    ('https://p.test/', 'android-app://com.google.android.googlequicksearchbox/', 'organic_search'),
    ('https://p.test/', 'https://mail.google.com/', 'email'),
    ('https://p.test/', 'https://t.co/abc', 'social'),
    ('https://p.test/', 'https://www.yelp.com/biz/x', 'referral'),
    ('https://p.test/', '', 'direct'),
    ('', '', 'direct'),
    ('https://p.test/%E2%9C%93?utm_campaign=caf%C3%A9', '', 'campaign'),
    ('https://p.test/#utm_source=google&utm_medium=cpc', '', 'direct'),  # fragments never reach servers; not trusted
    ('https://p.test/?utm_source=gmb', '', 'google_business'),
])
def test_channel_classification(url, ref, channel):
    assert C(url, ref)['channel'] == channel


def test_fields_are_length_bounded_and_decoded():
    r = C('https://p.test/' + 'a' * 5000 + '?utm_campaign=' + 'c' * 500 + '&utm_source=' + 's' * 500)
    assert len(r['landing_path']) <= 300 and len(r['utm_campaign']) <= 150 and len(r['utm_source']) <= 100
    assert C('https://p.test/x?utm_campaign=caf%C3%A9')['utm_campaign'] == 'café'


def test_malformed_inputs_never_raise():
    for url, ref in (('http://[::1', 'http://[bad'), ('\x00\x01', None), ('https://p.test/?%%%', '::::')):
        assert C(url, ref or '')['channel'] in dict(InquiryAttribution.CHANNEL_CHOICES)


class AnalyticsBoundaryTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='A', slug='a', email='a@x.test', timezone='America/New_York')
        self.other = Practice.objects.create(name='B', slug='b', email='b@x.test')

    def _appt(self, when, **kw):
        a = Appointment.objects.create(practice=kw.pop('practice', self.p), patient_name='P', **kw)
        Appointment.objects.filter(id=a.id).update(created_at=when)
        return a

    def test_window_edges_spam_and_other_practices(self):
        now = timezone.now()
        self._appt(now - timedelta(days=30) + timedelta(minutes=1))  # inside
        self._appt(now - timedelta(days=30) - timedelta(minutes=1))  # previous period
        self._appt(now - timedelta(days=1), status='spam')
        self._appt(now - timedelta(days=1), practice=self.other)
        data = analytics.overview(self.p, 30, now=now)
        self.assertEqual(data['funnel']['requests'], 1)
        self.assertEqual(data['previous']['requests'], 1)

    def test_rates_are_none_without_data_not_zero(self):
        f = analytics.funnel(self.p, timezone.now() - timedelta(days=7), timezone.now())
        for k in ('request_rate', 'contact_rate', 'confirm_rate', 'median_first_reply_minutes', 'replied_within_1h'):
            self.assertIsNone(f[k], k)
        self.assertIsNone(f['after_hours_requests'])  # no office hours configured

    def test_confirmed_counted_once_from_offer_or_status(self):
        now = timezone.now()
        a = self._appt(now - timedelta(hours=5), status='confirmed', response_sent_at=now - timedelta(hours=4))
        AppointmentOffer.objects.create(appointment=a, practice=self.p, offered_date=date.today(), offered_time='9:00 AM',
                                        token_hash='h1', status='confirmed', expires_at=now + timedelta(days=1))
        f = analytics.funnel(self.p, now - timedelta(days=1), now)
        self.assertEqual((f['confirmed'], f['offered_time'], f['median_first_reply_minutes']), (1, 1, 60))

    def test_trend_has_eight_weeks_and_sums_match(self):
        now = timezone.now()
        for d in (1, 8, 15, 50):
            self._appt(now - timedelta(days=d))
        trend = analytics.weekly_trend(self.p, now=now)
        self.assertEqual(len(trend), 8)
        self.assertEqual(sum(w['requests'] for w in trend), 4)

    def test_value_estimate_only_with_practice_figure(self):
        from apps.growth.models import GrowthSettings
        self.assertIsNone(analytics.value_estimate(self.p, 3))
        GrowthSettings.for_practice(self.p)
        GrowthSettings.objects.filter(practice=self.p).update(average_visit_value=200)
        est = analytics.value_estimate(self.p, 3)
        self.assertEqual(est['estimated_value'], 600.0)
        self.assertIn('Estimate', est['note'])

    def test_untracked_requests_reported_honestly(self):
        self._appt(timezone.now() - timedelta(hours=1))
        rows = analytics.channels(self.p, timezone.now() - timedelta(days=1), timezone.now())
        self.assertEqual(rows[0]['channel'], 'untracked')


class OfferDstTests(TestCase):
    def test_offer_expiry_is_local_midnight_across_dst_change(self):
        from apps.appointments.offers import create_offer
        p = Practice.objects.create(name='NY', slug='ny', email='n@x.test', timezone='America/New_York')
        a = Appointment.objects.create(practice=p, patient_name='P', patient_email='p@x.test')
        offer, _ = create_offer(a, date(2026, 10, 31), '10:00 AM', None)  # US clocks change Nov 1, 2026
        local = offer.expires_at.astimezone(ZoneInfo('America/New_York'))
        self.assertEqual((local.date(), local.hour, local.minute), (date(2026, 11, 1), 0, 0))


def _reply(parent_id, body='Thanks!', html=None, charset=None, sender='pat@x.test', msgid='<r1@mail.test>'):
    m = EmailMessage()
    m['From'] = sender
    m['Subject'] = '=?utf-8?q?Re=3A_Your_visit_=E2=9C=93?='
    m['In-Reply-To'] = parent_id
    m['Message-ID'] = msgid
    if html and body is None:
        m.set_content(html, subtype='html')
    else:
        m.set_content(body)
        if html:
            m.add_alternative(html, subtype='html')
    if charset:
        m.replace_header('Content-Type', f'text/plain; charset="{charset}"')
    return m


@override_settings(EMAIL_CONFIGURED=False)
class InboundTests(TestCase):
    def setUp(self):
        cache.clear()
        self.p = Practice.objects.create(name='A', slug='a', email='a@x.test')
        self.appt = Appointment.objects.create(practice=self.p, patient_name='Pat', patient_email='pat@x.test',
                                               status='contacted', response_sent_at=timezone.now() - timedelta(hours=10))
        self.thread = EmailThread.objects.create(practice=self.p, patient_email='pat@x.test', subject='Your visit',
                                                 metadata={'appointment_id': str(self.appt.id)})
        self.parent = Email.objects.create(thread=self.thread, direction=Email.DIRECTION_OUTGOING, status='sent',
                                           from_email='desk@x.test', to_email='pat@x.test', subject='Your visit', body='Hi',
                                           provider_message_id='<abc123@mail.heyjarvis.ai>')

    def test_html_only_reply_gets_readable_text(self):
        m = _reply(self.parent.provider_message_id, body=None,
                   html='<html><body><p>Tuesday works &amp; thanks</p><blockquote>On Mon you wrote...</blockquote></body></html>')
        r = ingest_email_message(m)
        self.assertEqual(r['status'], 'stored')
        self.assertEqual(Email.objects.get(id=r['email_id']).body, 'Tuesday works & thanks')

    def test_unknown_charset_does_not_crash(self):
        m = _reply(self.parent.provider_message_id, body='hello there', charset='x-unknown-charset')
        self.assertIn('hello', _plain_body(m))

    def test_reply_from_different_address_is_flagged(self):
        ingest_email_message(_reply(self.parent.provider_message_id, sender='someone.else@x.test'))
        self.appt.refresh_from_db()
        self.assertIn('different address', self.appt.internal_notes[-1]['text'])

    def test_encoded_subject_decoded_and_status_reopened(self):
        r = ingest_email_message(_reply(self.parent.provider_message_id))
        self.assertIn('✓', Email.objects.get(id=r['email_id']).subject)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'pending')

    def test_patient_reply_creates_follow_up_and_resolves_after_answer(self):
        ingest_email_message(_reply(self.parent.provider_message_id, body='Can I come Thursday instead?'))
        Email.objects.filter(direction=Email.DIRECTION_INCOMING).update(created_at=timezone.now() - timedelta(hours=6))
        followups.scan_practice(self.p)
        task = FollowUpTask.objects.get(kind=FollowUpTask.KIND_PATIENT_REPLIED)
        self.assertIn('Thursday', task.reason)
        followups.scan_practice(self.p)
        self.assertEqual(FollowUpTask.objects.filter(kind=FollowUpTask.KIND_PATIENT_REPLIED).count(), 1)  # no duplicate
        Appointment.objects.filter(id=self.appt.id).update(response_sent_at=timezone.now())
        followups.scan_practice(self.p)
        task.refresh_from_db()
        self.assertEqual(task.status, 'done')

    def test_fresh_reply_waits_for_threshold(self):
        ingest_email_message(_reply(self.parent.provider_message_id))
        followups.scan_practice(self.p)
        self.assertFalse(FollowUpTask.objects.filter(kind=FollowUpTask.KIND_PATIENT_REPLIED).exists())

    def test_text_reply_also_counts(self):
        SmsMessage.objects.create(practice=self.p, appointment=self.appt, direction='in', to_number='+1', from_number='+19195550100',
                                  body='Running late', status='received', created_at=timezone.now() - timedelta(hours=6))
        followups.scan_practice(self.p)
        task = FollowUpTask.objects.get(kind=FollowUpTask.KIND_PATIENT_REPLIED)
        self.assertIn('text', task.reason)

    def test_unrelated_and_forged_threading_ignored(self):
        m = _reply('<abc123@evil.example>')
        self.assertEqual(ingest_email_message(m)['status'], 'ignored')
        m = _reply('<nope999@mail.heyjarvis.ai>', msgid='<r2@mail.test>')
        self.assertEqual(ingest_email_message(m)['status'], 'unmatched')
