"""Overnight phases 10-14: prioritisation, installation check, practice openings, Google review tasks,
confirmation-code collisions and the strict widget-origin option."""
import json
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment
from apps.core.security import encrypt_secret, is_allowed_origin
from apps.growth import followups, visibility
from apps.growth import integrations as I
from apps.growth.models import FollowUpTask, Integration
from apps.practices.models import Practice
from apps.users.models import User


def client_for(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return c


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.p = Practice.objects.create(name='Alpha', slug='alpha', email='a@alpha.test', website='https://alpha.test')
        self.desk = User.objects.create_user(username='d@x.test', email='d@x.test', password='Str0ng-Test-Passphrase-91',
                                             role='FRONT_DESK', practice=self.p)
        self.other = Practice.objects.create(name='Beta', slug='beta', email='b@beta.test')
        self.desk_b = User.objects.create_user(username='b@x.test', email='b@x.test', password='Str0ng-Test-Passphrase-91',
                                               role='FRONT_DESK', practice=self.other)

    def overdue(self, hours=6, **kw):
        a = Appointment.objects.create(practice=self.p, patient_name=kw.pop('name', 'P'), patient_email=kw.pop('email', 'p@x.test'), **kw)
        Appointment.objects.filter(id=a.id).update(created_at=timezone.now() - timedelta(hours=hours))
        return a


class PriorityTests(Base):
    def test_urgent_and_long_waiting_requests_come_first(self):
        self.overdue(hours=5, name='Routine', email='r@x.test')
        self.overdue(hours=5, name='Emergency', email='e@x.test', urgency='URGENT', intent='emergency')
        self.overdue(hours=5, name='New Pt', email='n@x.test', intent='new_patient')
        followups.scan_practice(self.p)
        FollowUpTask.objects.filter(patient_name='Routine').update(created_at=timezone.now() - timedelta(hours=30))
        res = client_for(self.desk).get('/api/v1/growth/follow-ups/').json()['results']
        order = [r['patient_name'] for r in res]
        self.assertEqual(order[0], 'Emergency')
        self.assertEqual(res[0]['priority']['level'], 'high')
        self.assertIn('urgent request', res[0]['priority']['reasons'])
        self.assertLess(order.index('Routine'), order.index('New Pt'))  # waiting a day outranks "new patient"
        self.assertIn('waiting 1 day', next(r for r in res if r['patient_name'] == 'Routine')['priority']['reasons'])

    def test_outreach_ranks_below_waiting_patients(self):
        a = self.overdue()
        followups.scan_practice(self.p)
        followups.ensure_task(self.p, 'recall:x', kind=FollowUpTask.KIND_RECALL, title='Recall', patient_name='Recall Pt')
        res = client_for(self.desk).get('/api/v1/growth/follow-ups/').json()['results']
        self.assertEqual(res[-1]['patient_name'], 'Recall Pt')
        self.assertEqual(res[-1]['priority']['level'], 'low')


PAGE = '''<html><head><script async src="https://app.heyjarvis.test/widget.js" data-api-url="https://app.heyjarvis.test"
data-practice="alpha" data-heyjarvis-client="{key}"></script></head><body>Hi</body></html>'''


@override_settings(APP_PUBLIC_URL='https://app.heyjarvis.test')
class InstallCheckTests(Base):
    def run_check(self, html, url='https://alpha.test/'):
        with mock.patch('apps.growth.visibility.safe_get', return_value=(url, 200, {}, html, 100, len(html))):
            return client_for(self.desk).post('/api/v1/growth/install-check/', {}, format='json')

    def test_correct_installation(self):
        r = self.run_check(PAGE.format(key=self.p.api_key)).json()
        self.assertTrue(r['installed'], r)
        self.assertEqual({c['key'] for c in r['checks']}, {'page', 'script', 'key', 'server', 'domain'})

    def test_wrong_key_wrong_server_and_missing_script(self):
        r = self.run_check(PAGE.format(key='someone-elses-key').replace('app.heyjarvis.test', 'other.example')).json()
        bad = {c['key'] for c in r['checks'] if not c['ok']}
        self.assertEqual(bad, {'key', 'server'})
        self.assertFalse(r['installed'])
        cache.clear()
        r = self.run_check('<html><body>No chat here</body></html>').json()
        self.assertEqual([c['key'] for c in r['checks'] if not c['ok']], ['script'])
        self.assertIn('Tag Manager', next(c for c in r['checks'] if c['key'] == 'script')['fix'])

    def test_domain_not_allowed(self):
        r = self.run_check(PAGE.format(key=self.p.api_key), url='https://copycat.example/').json()
        self.assertFalse(next(c for c in r['checks'] if c['key'] == 'domain')['ok'])

    def test_fetch_errors_and_rate_limit(self):
        with mock.patch('apps.growth.visibility.safe_get', side_effect=visibility.CheckError('Only public websites can be checked.')):
            r = client_for(self.desk).post('/api/v1/growth/install-check/', {'url': 'http://10.0.0.1/'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(client_for(self.desk).post('/api/v1/growth/install-check/', {}, format='json').status_code, 429)

    def test_requires_login(self):
        self.assertEqual(APIClient().post('/api/v1/growth/install-check/', {}, format='json').status_code, 401)


class QueueFreshnessTests(Base):
    def test_new_overdue_request_appears_immediately_despite_recent_scan(self):
        c = client_for(self.desk)
        self.assertEqual(c.get('/api/v1/growth/follow-ups/').json()['results'], [])  # scan ran, throttle set
        self.overdue(name='Just In')
        names = [r['patient_name'] for r in c.get('/api/v1/growth/follow-ups/').json()['results']]
        self.assertEqual(names, ['Just In'])


class OpeningsTests(Base):
    def test_not_connected_is_a_quiet_answer(self):
        r = client_for(self.desk).get('/api/v1/growth/integrations/nexhealth/slots/')
        self.assertEqual(r.json(), {'connected': False, 'slots': []})

    def test_connected_practice_gets_slots_other_practice_does_not(self):
        Integration.objects.create(practice=self.p, kind='nexhealth', status='connected', config={'subdomain': 'alpha', 'location_id': 1},
                                   secret=encrypt_secret(json.dumps({'api_key': 'k', 'token': 't', 'token_expires': '2999-01-01'})))
        data = {'data': [{'pid': 1, 'slots': [{'time': '2026-10-14T09:00:00.000-04:00', 'end_time': '2026-10-14T09:30:00.000-04:00'}]}]}
        resp = mock.Mock(status_code=200, json=lambda: data)
        with mock.patch('apps.growth.integrations.requests.get', return_value=resp):
            r = client_for(self.desk).get('/api/v1/growth/integrations/nexhealth/slots/?start_date=2026-10-14').json()
        self.assertTrue(r['connected'])
        self.assertEqual(r['slots'][0]['time'], '2026-10-14T09:00:00.000-04:00')
        self.assertFalse(client_for(self.desk_b).get('/api/v1/growth/integrations/nexhealth/slots/').json()['connected'])


@override_settings(GOOGLE_BUSINESS_CLIENT_ID='cid', GOOGLE_BUSINESS_CLIENT_SECRET='cs')
class ReviewTaskTests(Base):
    def setUp(self):
        super().setUp()
        self.integ = Integration.objects.create(practice=self.p, kind='google_business', status='connected',
                                                config={'account': 'accounts/1', 'location': 'locations/2'})
        I.write_secret(self.integ, {'access_token': 'at', 'refresh_token': 'rt',
                                    'expires_at': (timezone.now() + timedelta(hours=1)).isoformat()})
        self.integ.save()

    def reviews(self, replied=False):
        return {'reviews': [
            {'name': 'accounts/1/locations/2/reviews/r1', 'reviewer': {'displayName': 'Sam Lee'}, 'starRating': 'TWO',
             'comment': 'Long wait', **({'reviewReply': {'comment': 'Sorry!'}} if replied else {})},
            {'name': 'accounts/1/locations/2/reviews/r2', 'reviewer': {'displayName': 'Ana'}, 'starRating': 'FIVE',
             'comment': 'Great', 'reviewReply': {'comment': 'Thanks'}}]}

    def test_unanswered_reviews_become_tasks_once_and_close_when_answered(self):
        with mock.patch('apps.growth.integrations.requests.request', return_value=mock.Mock(status_code=200, content=b'1', json=lambda: self.reviews())):
            self.assertEqual(followups.scan_google_reviews(self.p)['created'], 1)
            self.assertEqual(followups.scan_google_reviews(self.p)['created'], 0)
        task = FollowUpTask.objects.get(kind=FollowUpTask.KIND_REVIEW_REPLY)
        self.assertEqual(task.channel, 'google')
        self.assertIn('contact our office', task.draft_body)
        with mock.patch('apps.growth.integrations.requests.request', return_value=mock.Mock(status_code=200, content=b'1', json=lambda: self.reviews(True))):
            followups.scan_google_reviews(self.p)
        task.refresh_from_db()
        self.assertEqual(task.status, 'done')

    def test_staff_send_publishes_reply_on_google(self):
        with mock.patch('apps.growth.integrations.requests.request', return_value=mock.Mock(status_code=200, content=b'1', json=lambda: self.reviews())):
            followups.scan_google_reviews(self.p)
        task = FollowUpTask.objects.get(kind=FollowUpTask.KIND_REVIEW_REPLY)
        put = mock.Mock(status_code=200, content=b'1', json=lambda: {'comment': 'x'})
        with mock.patch('apps.growth.integrations.requests.request', return_value=put) as req:
            r = client_for(self.desk).post(f'/api/v1/growth/follow-ups/{task.id}/send/', {'body': 'Thank you, please call us.'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(req.call_args.args[0], 'PUT')
        self.assertEqual(req.call_args.kwargs['json'], {'comment': 'Thank you, please call us.'})
        task.refresh_from_db()
        self.assertEqual(task.status, 'sent')

    def test_job_skips_unconnected_and_isolates_errors(self):
        from apps.growth import jobs
        with mock.patch('apps.growth.integrations.requests.request', return_value=mock.Mock(status_code=403, content=b'', json=lambda: {})):
            r = jobs.run_job('google_reviews')
        self.assertEqual((r['status'], r['result']['practices'], r['result']['errors']), ('ok', 1, 1))
        self.integ.refresh_from_db()
        self.assertEqual(self.integ.status, 'error')


class ConfirmationCodeTests(TestCase):
    def test_collision_retries_instead_of_failing(self):
        p = Practice.objects.create(name='A', slug='a', email='a@x.test')
        Appointment.objects.create(practice=p, patient_name='First', confirmation_code='APT-AAAAAAAA')
        with mock.patch('secrets.token_hex', side_effect=['aaaaaaaa', 'aaaaaaaa', 'bbbbbbbb']):
            a = Appointment.objects.create(practice=p, patient_name='Second')
        self.assertEqual(a.confirmation_code, 'APT-BBBBBBBB')


class OriginSettingTests(TestCase):
    def test_default_keeps_local_previews_working(self):
        self.assertTrue(is_allowed_origin('null', ['alpha.test']))
        self.assertTrue(is_allowed_origin('http://localhost:3000', ['alpha.test']))

    @override_settings(WIDGET_ALLOW_LOCAL_ORIGINS=False)
    def test_strict_mode_enforces_domain_list(self):
        self.assertFalse(is_allowed_origin('null', ['alpha.test']))
        self.assertFalse(is_allowed_origin('file:///C:/demo.html', ['alpha.test']))
        self.assertFalse(is_allowed_origin('http://localhost:3000', ['alpha.test']))
        self.assertTrue(is_allowed_origin('https://www.alpha.test', ['alpha.test']))
        self.assertFalse(is_allowed_origin('https://alpha.test.evil.example', ['alpha.test']))
