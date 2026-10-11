"""Phase 9: growth & conversion platform (attribution, follow-ups, briefing, scheduler, outreach, SMS,
website visibility, integrations). External services are mocked; nothing leaves the test process."""
import base64
import hashlib
import hmac
from datetime import date, timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment, AppointmentOffer
from apps.conversations.models import Conversation
from apps.growth import attribution, followups, jobs, outreach, visibility
from apps.growth.briefing import send_briefing
from apps.growth.consent import is_opted_out, unsubscribe_token
from apps.growth.models import (BriefingLog, FollowUpTask, GrowthSettings, InquiryAttribution, Integration, JobRun,
                                RecallContact, SmsMessage)
from apps.practices.models import BookingRules, KnowledgeEntry, Practice, UnansweredQuestion
from apps.users.models import User

HOURS = {d: {'open': '09:00', 'close': '17:00', 'closed': False} for d in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday')}
HOURS.update({'saturday': {'closed': True}, 'sunday': {'closed': True}})


def make_user(email, role, practice):
    return User.objects.create_user(username=email, email=email, password='Str0ng-Test-Passphrase-91', role=role, practice=practice)


def client_for(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return c


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.p = Practice.objects.create(name='Alpha Dental', slug='alpha', email='front@alpha.test', phone='(919) 555-0100',
                                         address='12 Main St', city='Raleigh', state='NC', zip_code='27601',
                                         website='https://alpha.test', timezone='America/New_York')
        self.q = Practice.objects.create(name='Beta Dental', slug='beta', email='front@beta.test')
        BookingRules.objects.update_or_create(practice=self.p, defaults={'business_hours': HOURS})
        self.p.refresh_from_db()
        self.admin = make_user('doc@alpha.test', 'PRACTICE_ADMIN', self.p)
        self.desk = make_user('desk@alpha.test', 'FRONT_DESK', self.p)
        self.desk_b = make_user('desk@beta.test', 'FRONT_DESK', self.q)

    def appt(self, hours_ago=6, **kw):
        a = Appointment.objects.create(practice=kw.pop('practice', self.p), patient_name=kw.pop('name', 'Jamie Rivera'),
                                       patient_email=kw.pop('email', 'jamie@patient.test'), intent='cleaning',
                                       service_name='Cleaning', **kw)
        Appointment.objects.filter(id=a.id).update(created_at=timezone.now() - timedelta(hours=hours_ago))
        a.refresh_from_db()
        return a


class AttributionTests(Base):
    def test_classification(self):
        c = attribution.classify
        self.assertEqual(c('https://alpha.test/?gclid=abc', '')['channel'], 'google_ads')
        self.assertEqual(c('https://alpha.test/', 'https://www.google.com/')['channel'], 'organic_search')
        self.assertEqual(c('https://alpha.test/', 'https://chatgpt.com/')['channel'], 'ai_assistant')
        self.assertEqual(c('https://alpha.test/?utm_source=gbp&utm_medium=organic', '')['channel'], 'google_business')
        self.assertEqual(c('https://alpha.test/', 'https://l.facebook.com/')['channel'], 'social')
        self.assertEqual(c('https://alpha.test/?utm_source=news&utm_medium=email', '')['channel'], 'email')
        self.assertEqual(c('https://alpha.test/team', 'https://alpha.test/')['channel'], 'direct')  # same site
        self.assertEqual(c('not a url', 'also bad')['channel'], 'direct')
        r = c('https://alpha.test/implants?utm_source=Spring&utm_campaign=implants', 'https://blog.example.org/x')
        self.assertEqual((r['channel'], r['landing_path'], r['utm_campaign']), ('campaign', '/implants', 'implants'))

    def test_widget_init_records_source_once_and_request_shows_it(self):
        c = APIClient()
        body = {'client_key': self.p.api_key, 'session_id': 's-1', 'url': 'https://alpha.test/new-patients?utm_source=google&utm_medium=cpc',
                'referrer': 'https://www.google.com/'}
        r = c.post('/api/v1/widget/conversation/', body, format='json', HTTP_ORIGIN='https://alpha.test')
        self.assertEqual(r.status_code, 200, r.content)
        conv = Conversation.objects.get(id=r.json()['conversation_id'])
        c.post('/api/v1/widget/conversation/', {**body, 'url': 'https://alpha.test/other'}, format='json', HTTP_ORIGIN='https://alpha.test')
        self.assertEqual(InquiryAttribution.objects.filter(conversation=conv).count(), 1)
        att = conv.attribution
        self.assertEqual((att.channel, att.landing_path), ('google_ads', '/new-patients'))
        a = Appointment.objects.create(practice=self.p, conversation=conv, patient_name='W', patient_email='w@x.test')
        data = client_for(self.desk).get(f'/api/requests/{a.id}/').json()
        self.assertEqual(data['source']['channel'], 'google_ads')


@override_settings(EMAIL_CONFIGURED=True)
class FollowUpTests(Base):
    def test_waiting_request_creates_one_task_and_one_alert(self):
        a = self.appt(hours_ago=6)
        self.appt(hours_ago=1, name='Too Fresh', email='f@x.test')
        self.appt(hours_ago=9, practice=self.q, name='Other Practice', email='o@x.test')
        r1 = followups.scan_practice(self.p)
        r2 = followups.scan_practice(self.p)
        self.assertEqual(r1['waiting']['created'], 1)
        self.assertEqual(r2['waiting']['created'], 0)
        task = FollowUpTask.objects.get(practice=self.p)
        self.assertEqual((task.kind, task.appointment_id), (FollowUpTask.KIND_WAITING_REPLY, a.id))
        self.assertIn('Jamie', task.draft_body)
        alerts = [m for m in mail.outbox if 'follow-up' in m.subject]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].to, ['front@alpha.test'])
        self.assertNotIn('jamie@patient.test', alerts[0].body)  # staff alert carries first names only

    def test_task_resolves_after_staff_reply(self):
        a = self.appt()
        followups.scan_practice(self.p)
        a.status, a.response_sent_at = 'contacted', timezone.now()
        a.save()
        followups.scan_practice(self.p)
        self.assertEqual(FollowUpTask.objects.get().status, FollowUpTask.STATUS_DONE)

    def test_send_from_queue_emails_patient_marks_contacted_and_cannot_send_twice(self):
        a = self.appt()
        c = client_for(self.desk)
        tasks = c.get('/api/v1/growth/follow-ups/').json()['results']
        self.assertEqual(len(tasks), 1)
        tid = tasks[0]['id']
        r = c.post(f'/api/v1/growth/follow-ups/{tid}/send/', {'subject': 'Hello', 'body': 'Hi Jamie, when suits you?'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        a.refresh_from_db()
        self.assertEqual(a.status, 'contacted')
        self.assertIsNotNone(a.response_sent_at)
        sent = [m for m in mail.outbox if m.to == ['jamie@patient.test']]
        self.assertEqual(len(sent), 1)
        self.assertIn('when suits you', sent[0].body)
        r2 = c.post(f'/api/v1/growth/follow-ups/{tid}/send/', {'subject': 'Hello', 'body': 'again'}, format='json')
        self.assertEqual(r2.status_code, 400)

    def test_tenant_isolation(self):
        self.appt()
        followups.scan_practice(self.p)
        task = FollowUpTask.objects.get()
        other = client_for(self.desk_b)
        self.assertEqual(other.get('/api/v1/growth/follow-ups/').json()['results'], [])
        self.assertEqual(other.patch(f'/api/v1/growth/follow-ups/{task.id}/', {'action': 'dismiss'}, format='json').status_code, 404)
        self.assertEqual(other.post(f'/api/v1/growth/follow-ups/{task.id}/send/', {'subject': 's', 'body': 'b'}, format='json').status_code, 404)
        self.assertEqual(APIClient().get('/api/v1/growth/follow-ups/').status_code, 401)

    def test_snooze_and_wake(self):
        self.appt()
        followups.scan_practice(self.p)
        task = FollowUpTask.objects.get()
        c = client_for(self.desk)
        c.patch(f'/api/v1/growth/follow-ups/{task.id}/', {'action': 'snooze', 'hours': 2}, format='json')
        task.refresh_from_db()
        self.assertEqual(task.status, 'snoozed')
        followups.wake_snoozed(self.p, timezone.now() + timedelta(hours=3))
        task.refresh_from_db()
        self.assertEqual(task.status, 'open')

    def test_batch_send_requires_batch_policy(self):
        self.appt()
        followups.scan_practice(self.p)
        task = FollowUpTask.objects.get()
        c = client_for(self.desk)
        self.assertEqual(c.post('/api/v1/growth/follow-ups/send-batch/', {'ids': [str(task.id)]}, format='json').status_code, 400)
        GrowthSettings.objects.filter(practice=GrowthSettings.for_practice(self.p).practice).update(approval_policy='approve_batch')
        r = c.post('/api/v1/growth/follow-ups/send-batch/', {'ids': [str(task.id)]}, format='json').json()
        self.assertEqual(r['sent'], 1)

    def test_unconfirmed_offer_nudge_reissues_link(self):
        from apps.appointments.offers import create_offer
        a = self.appt(status='contacted', response_sent_at=timezone.now())
        offer, _ = create_offer(a, date.today() + timedelta(days=5), '10:00 AM', self.desk)
        AppointmentOffer.objects.filter(id=offer.id).update(created_at=timezone.now() - timedelta(hours=30))
        followups.scan_practice(self.p)
        task = FollowUpTask.objects.get(kind=FollowUpTask.KIND_UNCONFIRMED)
        r = client_for(self.desk).post(f'/api/v1/growth/follow-ups/{task.id}/send/', {}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        offer.refresh_from_db()
        self.assertEqual(offer.status, AppointmentOffer.STATUS_SUPERSEDED)
        new = AppointmentOffer.objects.exclude(id=offer.id).get()
        self.assertEqual((new.status, new.offered_time), (AppointmentOffer.STATUS_PENDING, '10:00 AM'))
        msg = [m for m in mail.outbox if m.to == ['jamie@patient.test']][-1]
        self.assertIn('/appointment/', msg.body)

    def test_reschedule_request_becomes_task_and_closes_when_new_time_sent(self):
        from apps.appointments.offers import activate_offer, create_offer
        a = self.appt(status='contacted', response_sent_at=timezone.now())
        offer, _ = create_offer(a, date.today() + timedelta(days=5), '10:00 AM', self.desk)
        AppointmentOffer.objects.filter(id=offer.id).update(status=AppointmentOffer.STATUS_RESCHEDULE, responded_at=timezone.now())
        followups.scan_practice(self.p)
        task = FollowUpTask.objects.get(kind=FollowUpTask.KIND_RESCHEDULE)
        newer, _ = create_offer(a, date.today() + timedelta(days=6), '11:00 AM', self.desk)
        activate_offer(newer)
        followups.scan_practice(self.p)
        task.refresh_from_db()
        self.assertEqual(task.status, 'done')


@override_settings(EMAIL_CONFIGURED=True)
class BriefingAndSchedulerTests(Base):
    def test_briefing_sent_once_per_week_to_practice_admins(self):
        self.appt(hours_ago=30)
        UnansweredQuestion.objects.create(practice=self.p, question='parking?', normalized='parking')
        monday = date.today() - timedelta(days=date.today().weekday())
        r1 = send_briefing(self.p, force_week=monday)
        r2 = send_briefing(self.p, force_week=monday)
        self.assertEqual((r1['status'], r2['status']), ('sent', 'skipped'))
        msgs = [m for m in mail.outbox if 'Your week at' in m.subject]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].to, ['doc@alpha.test'])
        html = msgs[0].alternatives[0][0]
        self.assertIn('Weekly briefing', html)
        log = BriefingLog.objects.get()
        self.assertEqual(log.payload['numbers']['requests'], 1)
        self.assertEqual(log.payload['waiting']['unanswered_questions'], 1)

    def test_briefing_preview_and_send_permissions(self):
        self.assertEqual(client_for(self.desk).get('/api/v1/growth/briefing/').status_code, 200)
        self.assertEqual(client_for(self.desk).post('/api/v1/growth/briefing/send/').status_code, 403)
        self.assertEqual(client_for(self.admin).post('/api/v1/growth/briefing/send/').status_code, 200)
        self.assertEqual(client_for(self.admin).post('/api/v1/growth/briefing/send/').status_code, 400)  # once per week

    def test_jobs_run_once_per_window(self):
        now = timezone.now()
        first = jobs.run_due_jobs(now=now, only=['followups', 'cleanup'])
        second = jobs.run_due_jobs(now=now, only=['followups', 'cleanup'])
        self.assertEqual([r['status'] for r in first], ['ok', 'ok'])
        self.assertEqual([r['status'] for r in second], ['skipped', 'skipped'])
        self.assertEqual(JobRun.objects.count(), 2)

    @override_settings(CRON_SECRET='s3cret-value')
    def test_cron_endpoint_requires_secret(self):
        self.assertEqual(APIClient().post('/api/v1/growth/cron/run/', {}, format='json').status_code, 403)
        bad = APIClient().post('/api/v1/growth/cron/run/', {}, format='json', HTTP_X_CRON_SECRET='nope')
        self.assertEqual(bad.status_code, 403)
        ok = APIClient().post('/api/v1/growth/cron/run/', {'jobs': ['followups']}, format='json', HTTP_X_CRON_SECRET='s3cret-value')
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()['ran'][0]['job'], 'followups')
        self.assertEqual(client_for(self.admin).get('/api/v1/growth/cron/status/').status_code, 403)

    def test_analytics_funnel_and_channels(self):
        conv = Conversation.objects.create(practice=self.p, session_id='x')
        attribution.record_attribution(conv, 'https://alpha.test/', 'https://www.bing.com/')
        a = self.appt(hours_ago=3)
        a.conversation, a.status = conv, 'confirmed'
        a.save()
        data = client_for(self.desk).get('/api/v1/growth/analytics/?days=30').json()
        self.assertEqual(data['funnel']['requests'], 1)
        self.assertEqual(data['funnel']['confirmed'], 1)
        self.assertEqual(data['channels'][0]['channel'], 'organic_search')
        self.assertIsNone(data['value_estimate'])
        other = client_for(self.desk_b).get('/api/v1/growth/analytics/').json()
        self.assertEqual(other['funnel']['requests'], 0)


@override_settings(EMAIL_CONFIGURED=True)
class SettingsAndOutreachTests(Base):
    def test_only_admin_changes_settings_and_outreach_needs_acknowledgement(self):
        url = '/api/v1/growth/settings/'
        self.assertEqual(client_for(self.desk).patch(url, {'waiting_alert_hours': 8}, format='json').status_code, 403)
        c = client_for(self.admin)
        self.assertEqual(c.patch(url, {'waiting_alert_hours': 0}, format='json').status_code, 400)
        self.assertEqual(c.patch(url, {'recall_enabled': True}, format='json').status_code, 400)
        r = c.patch(url, {'recall_enabled': True, 'acknowledge_outreach': True}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['outreach_acknowledged'])
        self.assertEqual(c.patch(url, {'review_requests_enabled': True}, format='json').status_code, 400)  # needs link
        self.assertEqual(c.patch(url, {'review_requests_enabled': True, 'review_link': 'https://g.page/r/abc/review'},
                                 format='json').status_code, 200)

    def test_csv_import_aliases_dedupe_and_errors(self):
        csv_text = ('First Name,Last Name,Email,Mobile,Last Visit,Consent\n'
                    'Ana,Lopez,ana@x.test,919-555-0101,2026-01-15,yes\n'
                    'Ben,Cho,,(919) 555-0102,03/02/2025,\n'
                    'No Contact,,,,2026-01-01,\n'
                    'Bad Date,,bad@x.test,,13/45/2025,\n'
                    'Ana,Lopez,ANA@x.test,,2026-02-01,yes\n')
        r = outreach.import_recall_csv(self.p, csv_text, 6)
        self.assertEqual((r['created'], r['updated'], r['skipped']), (2, 1, 2))
        ana = RecallContact.objects.get(email='ana@x.test')
        self.assertEqual((ana.last_visit, ana.next_due, ana.consent_outreach), (date(2026, 2, 1), date(2026, 8, 1), True))
        self.assertEqual(RecallContact.objects.get(name='Ben Cho').phone, '+19195550102')
        self.assertTrue(any('Row 5' in e for e in r['errors']))

    def test_recall_tasks_only_when_enabled_and_respect_opt_out(self):
        RecallContact.objects.create(practice=self.p, name='Due Soon', email='due@x.test', next_due=date.today())
        RecallContact.objects.create(practice=self.p, name='Opted Out', email='out@x.test', next_due=date.today())
        from apps.growth.consent import set_opt_out
        set_opt_out(self.p, 'email', 'out@x.test')
        self.assertEqual(outreach.scan_outreach(self.p)['recall'], 0)  # off by default
        GrowthSettings.objects.filter(practice=GrowthSettings.for_practice(self.p).practice).update(recall_enabled=True)
        self.assertEqual(outreach.scan_outreach(self.p)['recall'], 0)  # not acknowledged
        GrowthSettings.objects.filter(practice=GrowthSettings.for_practice(self.p).practice).update(outreach_acknowledged_at=timezone.now())
        self.assertEqual(outreach.scan_outreach(self.p)['recall'], 1)
        self.assertEqual(outreach.scan_outreach(self.p)['recall'], 0)  # deduplicated
        self.assertEqual(FollowUpTask.objects.get().patient_email, 'due@x.test')

    def test_email_opt_out_falls_back_to_text_channel(self):
        GrowthSettings.objects.filter(practice=GrowthSettings.for_practice(self.p).practice).update(recall_enabled=True, outreach_acknowledged_at=timezone.now())
        RecallContact.objects.create(practice=self.p, name='Both Ways', email='both@x.test', phone='+19195550111', next_due=date.today())
        from apps.growth.consent import set_opt_out
        set_opt_out(self.p, 'email', 'both@x.test')
        outreach.scan_outreach(self.p)
        task = FollowUpTask.objects.get()
        self.assertEqual((task.channel, task.draft_subject), ('sms', ''))

    def test_outreach_email_has_unsubscribe_and_link_flow(self):
        GrowthSettings.objects.filter(practice=GrowthSettings.for_practice(self.p).practice).update(recall_enabled=True, outreach_acknowledged_at=timezone.now())
        RecallContact.objects.create(practice=self.p, name='Dana Due', email='dana@x.test', next_due=date.today())
        outreach.scan_outreach(self.p)
        task = FollowUpTask.objects.get()
        r = client_for(self.desk).post(f'/api/v1/growth/follow-ups/{task.id}/send/', {}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        body = [m for m in mail.outbox if m.to == ['dana@x.test']][0].body
        self.assertIn('/api/v1/growth/unsubscribe/', body)
        token = unsubscribe_token(self.p, 'dana@x.test')
        page = APIClient().get(f'/api/v1/growth/unsubscribe/{token}/')
        self.assertEqual(page.status_code, 200)
        self.assertFalse(is_opted_out(self.p, 'email', 'dana@x.test'))  # GET (link scanners) does nothing
        APIClient().post(f'/api/v1/growth/unsubscribe/{token}/')
        self.assertTrue(is_opted_out(self.p, 'email', 'dana@x.test'))
        self.assertFalse(is_opted_out(self.q, 'email', 'dana@x.test'))  # per practice
        self.assertIn(b'not valid', APIClient().get('/api/v1/growth/unsubscribe/forged-token/').content)

    def test_review_requests_only_for_completed_visits_once_a_year(self):
        GrowthSettings.objects.filter(practice=GrowthSettings.for_practice(self.p).practice).update(review_requests_enabled=True, review_link='https://g.page/r/x/review',
                                                               outreach_acknowledged_at=timezone.now())
        done = self.appt(status='completed')
        self.appt(name='Pending One', email='p@x.test')
        self.assertEqual(outreach.scan_outreach(self.p)['review'], 1)
        self.appt(status='completed', email='jamie@patient.test', name='Jamie Again')
        self.assertEqual(outreach.scan_outreach(self.p)['review'], 0)
        task = FollowUpTask.objects.get(kind=FollowUpTask.KIND_REVIEW)
        self.assertEqual(task.appointment_id, done.id)
        self.assertIn('https://g.page/r/x/review', task.draft_body)

    def test_completed_request_adds_patient_to_recall_list(self):
        a = self.appt()
        a.status = 'completed'
        a.save()
        c = RecallContact.objects.get(practice=self.p)
        self.assertEqual((c.email, c.source, c.last_visit), ('jamie@patient.test', 'heyjarvis', timezone.localdate()))


def twilio_sig(token, url, params):
    payload = url + ''.join(f'{k}{params[k]}' for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


@override_settings(SMS_BACKEND='console', TWILIO_ACCOUNT_SID='', TWILIO_AUTH_TOKEN='', TWILIO_FROM_NUMBER='')
class SmsTests(Base):
    def test_console_send_records_and_opt_out_blocks(self):
        a = self.appt(patient_phone='919-555-0199')
        c = client_for(self.desk)
        r = c.post('/api/v1/growth/sms/', {'appointment_id': str(a.id), 'body': 'Hi Jamie, we have Tuesday 10am.'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        m = SmsMessage.objects.get()
        self.assertEqual((m.to_number, m.status, m.provider), ('+19195550199', 'sent', 'console'))
        from apps.growth.consent import set_opt_out
        set_opt_out(self.p, 'sms', '9195550199')
        r = c.post('/api/v1/growth/sms/', {'appointment_id': str(a.id), 'body': 'again'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('STOP', r.json()['error'])

    def test_invalid_number_rejected(self):
        r = client_for(self.desk).post('/api/v1/growth/sms/', {'to': '12', 'body': 'x'}, format='json')
        self.assertEqual(r.status_code, 400)

    @override_settings(APP_PUBLIC_URL='https://app.heyjarvis.test')
    def test_inbound_stop_with_valid_signature(self):
        from apps.core.security import encrypt_secret
        import json
        Integration.objects.create(practice=self.p, kind='twilio', status='connected', config={'from_number': '+19195550000'},
                                   secret=encrypt_secret(json.dumps({'account_sid': 'AC' + 'x' * 32, 'auth_token': 'tok123'})))
        params = {'From': '+19195550199', 'To': '+19195550000', 'Body': 'STOP', 'MessageSid': 'SM1'}
        url = 'https://app.heyjarvis.test/api/v1/growth/sms/inbound/'
        bad = APIClient().post('/api/v1/growth/sms/inbound/', params, HTTP_X_TWILIO_SIGNATURE='wrong')
        self.assertEqual(bad.status_code, 403)
        ok = APIClient().post('/api/v1/growth/sms/inbound/', params, HTTP_X_TWILIO_SIGNATURE=twilio_sig('tok123', url, params))
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(is_opted_out(self.p, 'sms', '+19195550199'))
        self.assertEqual(SmsMessage.objects.get().direction, 'in')

    def test_outreach_text_gets_stop_notice(self):
        from apps.growth.sms import send_sms
        m = send_sms(self.p, '9195550123', 'Time for your check-up!', outreach=True)
        self.assertIn('Reply STOP to opt out', m.body)


SAMPLE_HTML = """<!doctype html><html lang="en"><head><title>Family Dentist in Raleigh | Alpha Dental</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Alpha Dental offers gentle family dentistry, cleanings and implants in downtown Raleigh, NC. New patients welcome.">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Dentist","name":"Alpha Dental","telephone":"+1-919-555-0100"}</script>
<script src="https://app.heyjarvis.test/widget.js" data-client-key="KEY"></script></head>
<body><h1>Alpha Dental</h1><a href="tel:+19195550100">(919) 555-0100</a><p>12 Main St, Raleigh NC 27601</p>
<p>Office hours: Monday - Friday 9am-5pm</p><a href="/book">Book an appointment</a><img src="a.jpg" alt="Our team"></body></html>"""


class VisibilityTests(Base):
    def test_analyze_good_page(self):
        html = SAMPLE_HTML.replace('KEY', self.p.api_key)
        findings = {f['id']: f for f in visibility.analyze(self.p, 'https://alpha.test', html, 'https://alpha.test/', 200, 800, 40000)}
        for fid in ('name', 'phone', 'tel_link', 'address', 'hours', 'widget', 'cta', 'title', 'description', 'h1',
                    'indexable', 'schema_local', 'schema_phone', 'https', 'viewport', 'speed', 'alt', 'lang'):
            self.assertEqual(findings[fid]['status'], 'pass', fid)

    def test_analyze_problem_page(self):
        html = '<html><head><meta name="robots" content="noindex"></head><body>Welcome. Call 555-9999</body></html>'
        f = {x['id']: x for x in visibility.analyze(self.p, 'http://alpha.test', html, 'http://alpha.test/', 200, 6000, 10,
                                                     robots_txt='User-agent: *\nDisallow: /', sitemap_found=False)}
        for fid in ('phone', 'address', 'widget', 'indexable', 'robots', 'https', 'schema_local', 'viewport', 'sitemap'):
            self.assertEqual(f[fid]['status'], 'fail', fid)
            self.assertTrue(f[fid]['fix'])
        self.assertLess(visibility.score(list(f.values())), 30)

    def test_private_and_local_addresses_refused(self):
        for url in ('http://localhost/', 'http://127.0.0.1/', 'http://10.0.0.5/', 'http://169.254.169.254/latest/',
                    'ftp://alpha.test/', 'http://alpha.test:8080/', 'http://intranet/'):
            with self.assertRaises(visibility.CheckError, msg=url):
                visibility.validate_url(url)

    def test_redirect_to_private_address_is_blocked(self):
        import socket
        calls = []
        resp = mock.Mock(status_code=302, headers={'Location': 'http://127.0.0.1/admin'})
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.215.14', 0))]
        with mock.patch('socket.getaddrinfo', return_value=public),                 mock.patch('requests.Session.get', lambda self, url, **kw: calls.append(url) or resp):
            with self.assertRaises(visibility.CheckError):
                visibility.safe_get('https://alpha.test/')
        self.assertEqual(calls, ['https://93.184.215.14/'])

    def test_run_endpoint_stores_report(self):
        html = SAMPLE_HTML.replace('KEY', self.p.api_key)

        def fake_get(url, **kw):
            if url.endswith('/robots.txt'):
                return (url, 200, {}, 'User-agent: *\nAllow: /\nSitemap: https://alpha.test/sitemap.xml', 10, 50)
            return ('https://alpha.test/', 200, {}, html, 700, 30000)
        with mock.patch('apps.growth.visibility.safe_get', side_effect=fake_get):
            r = client_for(self.desk).post('/api/v1/growth/visibility/run/', {}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertGreaterEqual(r.json()['score'], 90)
        self.assertEqual(r.json()['lighthouse']['status'], 'off')
        latest = client_for(self.desk).get('/api/v1/growth/visibility/').json()['latest']
        self.assertEqual(latest['id'], r.json()['id'])
        self.assertIsNone(client_for(self.desk_b).get('/api/v1/growth/visibility/').json()['latest'])

    def test_failed_fetch_is_reported_plainly(self):
        with mock.patch('apps.growth.visibility.safe_get', side_effect=visibility.CheckError('The website did not respond.')):
            r = client_for(self.desk).post('/api/v1/growth/visibility/run/', {'url': 'https://down.test'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()['status'], r.json()['error']), ('failed', 'The website did not respond.'))

    def test_facts_export(self):
        KnowledgeEntry.objects.create(practice=self.p, category='faq', title='Is there parking?', content='Free parking behind the building.')
        data = client_for(self.desk).get('/api/v1/growth/visibility/facts/').json()
        self.assertIn('"@type": "Dentist"', data['structured_data'])
        self.assertIn('(919) 555-0100', data['structured_data'])
        self.assertIn('"opens": "09:00"', data['structured_data'])
        self.assertIn('Is there parking?', data['faq_html'])
        self.assertIn('FAQPage', data['faq_structured_data'])


class IntegrationTests(Base):
    def test_overview_is_honest_without_credentials(self):
        rows = {r['key']: r for r in client_for(self.desk).get('/api/v1/growth/integrations/').json()['integrations']}
        self.assertEqual(rows['google_business']['state'], 'awaiting_approval')
        self.assertEqual(rows['nexhealth']['state'], 'not_connected')
        self.assertEqual(rows['scheduler']['state'], 'needs_setup')
        self.assertIn(rows['sms']['state'], ('not_connected', 'test_mode'))

    def test_google_connect_without_app_credentials(self):
        r = client_for(self.admin).post('/api/v1/growth/integrations/google/connect/')
        self.assertEqual(r.status_code, 503)
        self.assertEqual(client_for(self.desk).post('/api/v1/growth/integrations/google/connect/').status_code, 403)

    @override_settings(GOOGLE_BUSINESS_CLIENT_ID='cid', GOOGLE_BUSINESS_CLIENT_SECRET='csec', APP_PUBLIC_URL='https://app.test')
    def test_google_oauth_url_and_callback(self):
        url = client_for(self.admin).post('/api/v1/growth/integrations/google/connect/').json()['url']
        self.assertIn('business.manage', url)
        from urllib.parse import parse_qs, urlparse
        state = parse_qs(urlparse(url).query)['state'][0]
        token_resp = mock.Mock(status_code=200, content=b'1', json=lambda: {'access_token': 'at', 'refresh_token': 'rt', 'expires_in': 3600})
        with mock.patch('apps.growth.integrations.requests.post', return_value=token_resp):
            r = APIClient().get('/api/v1/growth/integrations/google/callback/', {'state': state, 'code': 'abc'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('google=connected', r['Location'])
        integ = Integration.objects.get(practice=self.p, kind='google_business')
        self.assertEqual(integ.status, 'connected')
        self.assertNotIn('rt', integ.secret)  # encrypted at rest
        forged = APIClient().get('/api/v1/growth/integrations/google/callback/', {'state': 'forged', 'code': 'abc'})
        self.assertIn('google=cancelled', forged['Location'])

    def test_review_reply_must_belong_to_selected_location(self):
        from apps.growth import integrations
        integ = integrations.get_integration(self.p, 'google_business')
        integ.config = {'account': 'accounts/1', 'location': 'locations/2'}
        integ.status = 'connected'
        integ.save()
        with self.assertRaises(integrations.IntegrationError):
            integrations.gbp_reply(self.p, 'accounts/9/locations/9/reviews/1', 'Thanks')

    def test_review_reply_draft_never_mentions_treatment(self):
        r = client_for(self.desk).post('/api/v1/growth/integrations/google/reviews/draft/',
                                       {'reviewer': 'Sam Lee', 'rating': 2, 'comment': 'Long wait'}, format='json').json()
        self.assertIn('contact our office', r['draft'])
        self.assertIn('(919) 555-0100', r['draft'])

    def test_nexhealth_save_test_and_secret_never_returned(self):
        c = client_for(self.admin)
        self.assertEqual(c.post('/api/v1/growth/integrations/nexhealth/', {'api_key': 'k', 'subdomain': 'alpha', 'location_id': 'x'},
                                format='json').status_code, 502)
        self.assertEqual(c.post('/api/v1/growth/integrations/nexhealth/', {'api_key': 'secret-key-1', 'subdomain': 'alpha', 'location_id': '42'},
                                format='json').status_code, 200)
        auth = mock.Mock(status_code=200, content=b'1', json=lambda: {'data': {'token': 'tkn'}})
        providers = mock.Mock(status_code=200, content=b'1', json=lambda: {'data': [{'id': 7, 'name': 'Dr. Lee'}]})
        with mock.patch('apps.growth.integrations.requests.post', return_value=auth) as post, \
                mock.patch('apps.growth.integrations.requests.get', return_value=providers) as get:
            r = c.post('/api/v1/growth/integrations/nexhealth/test/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['providers'], [{'id': 7, 'name': 'Dr. Lee'}])
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'secret-key-1')
        self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer tkn')
        self.assertEqual(get.call_args.kwargs['params']['subdomain'], 'alpha')
        overview = c.get('/api/v1/growth/integrations/').content.decode()
        self.assertNotIn('secret-key-1', overview)
        self.assertIn('"working"', overview)

    def test_knowledge_suggest_refuses_prices_and_handles_no_ai(self):
        q1 = UnansweredQuestion.objects.create(practice=self.p, question='How much is a crown?', normalized='crown price')
        q2 = UnansweredQuestion.objects.create(practice=self.p, question='Do you see kids?', normalized='kids')
        c = client_for(self.admin)
        self.assertIn('Prices', c.post(f'/api/v1/growth/knowledge-suggest/{q1.id}/').json()['reason'])
        r = c.post(f'/api/v1/growth/knowledge-suggest/{q2.id}/').json()
        self.assertEqual(r['suggestion'], '')
        self.assertEqual(client_for(self.desk).post(f'/api/v1/growth/knowledge-suggest/{q2.id}/').status_code, 403)
        q3 = UnansweredQuestion.objects.create(practice=self.q, question='Hours?', normalized='hours')
        self.assertEqual(c.post(f'/api/v1/growth/knowledge-suggest/{q3.id}/').status_code, 404)
