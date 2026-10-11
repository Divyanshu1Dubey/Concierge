"""Phase 6: practice insights (attention, setup, results) and practice-timezone office hours."""
from datetime import datetime, timedelta, timezone as dt_tz

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment
from apps.conversations.state_machine import office_open_at
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


class OfficeHoursTimezoneTests(TestCase):
    def test_hours_are_checked_in_the_practice_timezone(self):
        p = Practice.objects.create(name='NY', slug='ny', email='n@x.test', timezone='America/New_York')
        BookingRules.objects.update_or_create(practice=p, defaults={'business_hours': HOURS})
        p.refresh_from_db()
        # Wednesday 14:00 UTC = 10:00 New York (open); 23:00 UTC = 19:00 New York (closed).
        self.assertTrue(office_open_at(p, datetime(2026, 10, 14, 14, 0, tzinfo=dt_tz.utc)))
        self.assertFalse(office_open_at(p, datetime(2026, 10, 14, 23, 0, tzinfo=dt_tz.utc)))
        self.assertFalse(office_open_at(p, datetime(2026, 10, 17, 15, 0, tzinfo=dt_tz.utc)))  # Saturday


@override_settings(EMAIL_CONFIGURED=True, IMAP_HOST='')
class InsightsTests(TestCase):
    def setUp(self):
        self.a = Practice.objects.create(name='Alpha', slug='alpha', email='a@x.test', timezone='America/New_York')
        self.b = Practice.objects.create(name='Beta', slug='beta', email='b@x.test')
        BookingRules.objects.update_or_create(practice=self.a, defaults={'business_hours': HOURS})
        BookingRules.objects.get_or_create(practice=self.b)
        self.desk = make_user('desk@alpha.test', 'FRONT_DESK', self.a)
        self.desk_b = make_user('desk@beta.test', 'FRONT_DESK', self.b)
        now = timezone.now()
        self.stale = Appointment.objects.create(practice=self.a, patient_name='Old Waiting', intent='cleaning',
                                                created_at=now - timedelta(hours=30))
        Appointment.objects.create(practice=self.a, patient_name='Fresh New', intent='cleaning', created_at=now - timedelta(hours=2))
        Appointment.objects.create(practice=self.a, patient_name='Done Reply', intent='cleaning', status='contacted',
                                   created_at=now - timedelta(hours=40), response_sent_at=now - timedelta(hours=39))
        Appointment.objects.create(practice=self.b, patient_name='Other Practice', intent='cleaning', created_at=now - timedelta(hours=50))
        UnansweredQuestion.objects.create(practice=self.a, question='parking?', normalized='parking')

    def test_attention_counts_only_real_waiting_requests(self):
        data = client_for(self.desk).get('/api/practices/insights/').json()
        att = data['attention']
        self.assertEqual(att['waiting_over_24h'], 1)
        self.assertEqual(att['waiting_examples'][0]['name'], 'Old')
        self.assertEqual(att['unanswered_questions'], 1)
        self.assertNotIn('Other', str(att))

    def test_setup_checklist_reflects_configuration(self):
        setup = {s['key']: s for s in client_for(self.desk).get('/api/practices/insights/').json()['setup']}
        self.assertTrue(setup['email']['done'])
        self.assertTrue(setup['hours']['done'])
        self.assertFalse(setup['knowledge']['done'])
        self.assertFalse(setup['replies']['done'])
        for i in range(3):
            KnowledgeEntry.objects.create(practice=self.a, title=f'Q{i}', content='A')
        setup = {s['key']: s for s in client_for(self.desk).get('/api/practices/insights/').json()['setup']}
        self.assertTrue(setup['knowledge']['done'])

    def test_results_from_real_records(self):
        r = client_for(self.desk).get('/api/practices/insights/').json()['results_30d']
        self.assertEqual(r['requests'], 3)
        self.assertEqual(r['replied'], 1)
        self.assertEqual(r['median_minutes_to_reply'], 60)
        self.assertIsNotNone(r['after_hours_requests'])

    def test_other_practice_sees_only_its_own(self):
        att = client_for(self.desk_b).get('/api/practices/insights/').json()['attention']
        self.assertEqual(att['waiting_over_24h'], 1)
        self.assertEqual(att['waiting_examples'][0]['name'], 'Other')
        self.assertEqual(att['unanswered_questions'], 0)