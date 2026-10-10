"""Regression tests: no public demo credentials, secure first admin, access requests, inbound replies."""
import io
from email.message import EmailMessage
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment
from apps.emails.inbound import ingest_email_message
from apps.emails.models import Email, EmailCadence, EmailThread
from apps.practices.models import AccessRequest, Practice
from apps.users.models import User

STRONG = 'Str0ng-Test-Passphrase-91'


def make_user(email, role, practice=None, **extra):
    return User.objects.create_user(username=email, email=email, password=STRONG, role=role, practice=practice, **extra)


def client_for(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return c


class NoPublicDemoCredentialsTests(TestCase):
    @override_settings(DEMO_ACCOUNTS_ENABLED=True)
    def test_auth_config_never_returns_accounts_or_passwords(self):
        res = APIClient().get('/api/auth/config/')
        self.assertEqual(res.status_code, 200)
        body = res.content.decode()
        self.assertNotIn('demo_accounts', res.json())
        self.assertNotIn('password', body.lower())
        self.assertNotIn('raleighdentistry.com', body)

    def test_seed_definitions_contain_no_passwords(self):
        from apps.users import seed_data
        self.assertTrue(all('password' not in info for info in seed_data.DEMO_ACCOUNTS.values()))
        self.assertFalse(hasattr(seed_data, 'public_demo_accounts'))

    @override_settings(DEMO_ACCOUNTS_ENABLED=True, DEMO_ACCOUNT_PASSWORD='')
    def test_demo_account_without_configured_password_cannot_log_in(self):
        from apps.users.seed_data import ensure_demo_account
        user = ensure_demo_account('desk@raleighdentistry.com')
        self.assertFalse(user.has_usable_password())

    @override_settings(DEMO_ACCOUNTS_ENABLED=True, DEMO_ACCOUNT_PASSWORD='Internal-Only-Passphrase-77')
    def test_demo_password_comes_from_environment_only(self):
        from apps.users.seed_data import ensure_demo_account
        user = ensure_demo_account('desk@raleighdentistry.com')
        self.assertTrue(user.check_password('Internal-Only-Passphrase-77'))


class LockDemoAccountsTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='Raleigh', slug='raleigh-dentistry', email='r@x.test')
        self.demo = make_user('admin@raleighdentistry.com', 'AGENCY_ADMIN', practice=self.p)
        self.real = make_user('owner@real-agency.test', 'AGENCY_ADMIN')

    def test_dry_run_changes_nothing(self):
        call_command('lock_demo_accounts', stdout=io.StringIO())
        self.demo.refresh_from_db()
        self.assertTrue(self.demo.check_password(STRONG))

    def test_confirm_deactivate_blocks_password_and_existing_tokens(self):
        refresh = RefreshToken.for_user(self.demo)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        self.assertEqual(c.get('/api/auth/me/').status_code, 200)
        call_command('lock_demo_accounts', '--confirm', '--deactivate', stdout=io.StringIO())
        self.demo.refresh_from_db()
        self.assertFalse(self.demo.has_usable_password())
        self.assertFalse(self.demo.is_active)
        self.assertEqual(c.get('/api/auth/me/').status_code, 401)
        self.assertEqual(APIClient().post('/api/auth/token/refresh/', {'refresh': str(refresh)}, format='json').status_code, 401)
        self.real.refresh_from_db()
        self.assertTrue(self.real.check_password(STRONG))


@override_settings(APP_PUBLIC_URL='https://concierge.example', EMAIL_CONFIGURED=False)
class CreateAgencyAdminTests(TestCase):
    def test_creates_admin_with_one_time_link_and_no_password(self):
        out = io.StringIO()
        call_command('create_agency_admin', '--email', 'Owner@Agency.example', '--first-name', 'Ana', stdout=out)
        user = User.objects.get(email='owner@agency.example')
        self.assertTrue(user.is_agency_admin)
        self.assertFalse(user.has_usable_password())
        link = [l for l in out.getvalue().splitlines() if l.startswith('https://concierge.example/reset-password?')][0]
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(link).query)
        res = APIClient().post('/api/auth/password-reset/confirm/', {
            'uid': q['uid'][0], 'token': q['token'][0], 'new_password': STRONG, 'new_password_confirm': STRONG}, format='json')
        self.assertEqual(res.status_code, 200)
        again = APIClient().post('/api/auth/password-reset/confirm/', {
            'uid': q['uid'][0], 'token': q['token'][0], 'new_password': STRONG + 'x', 'new_password_confirm': STRONG + 'x'}, format='json')
        self.assertEqual(again.status_code, 400)  # single use
        login = APIClient().post('/api/auth/login/', {'email': 'owner@agency.example', 'password': STRONG}, format='json')
        self.assertEqual(login.status_code, 200)

    def test_rerun_does_not_duplicate(self):
        call_command('create_agency_admin', '--email', 'owner@agency.example', stdout=io.StringIO())
        call_command('create_agency_admin', '--email', 'owner@agency.example', stdout=io.StringIO())
        self.assertEqual(User.objects.filter(email='owner@agency.example').count(), 1)

    def test_refuses_to_promote_practice_account_silently(self):
        p = Practice.objects.create(name='Alpha', slug='alpha', email='a@x.test')
        make_user('doc@alpha.test', 'PRACTICE_ADMIN', practice=p)
        with self.assertRaises(CommandError):
            call_command('create_agency_admin', '--email', 'doc@alpha.test', stdout=io.StringIO())
        self.assertEqual(User.objects.get(email='doc@alpha.test').role, 'PRACTICE_ADMIN')


class AccessRequestTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='Alpha', slug='alpha', email='a@x.test')
        self.agency = make_user('agency@platform.test', 'AGENCY_ADMIN')
        self.doc = make_user('doc@alpha.test', 'PRACTICE_ADMIN', practice=self.p)

    def test_public_request_is_stored_without_creating_accounts(self):
        users = User.objects.count()
        res = APIClient().post('/api/practices/access-requests/new/', {
            'practice_name': 'Oak Dental', 'contact_name': 'Dr. Oak', 'email': 'oak@example.test', 'message': 'Hi'}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(AccessRequest.objects.get().practice_name, 'Oak Dental')
        self.assertEqual(User.objects.count(), users)

    def test_validation_and_honeypot(self):
        self.assertEqual(APIClient().post('/api/practices/access-requests/new/', {'email': 'bad'}, format='json').status_code, 400)
        res = APIClient().post('/api/practices/access-requests/new/', {
            'practice_name': 'Bot', 'contact_name': 'Bot', 'email': 'b@example.test', 'company_fax': 'x'}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(AccessRequest.objects.count(), 0)

    def test_only_agency_admins_can_review(self):
        AccessRequest.objects.create(practice_name='Oak', contact_name='O', email='o@example.test')
        self.assertEqual(client_for(self.doc).get('/api/practices/access-requests/').status_code, 403)
        self.assertEqual(APIClient().get('/api/practices/access-requests/').status_code, 401)
        res = client_for(self.agency).get('/api/practices/access-requests/')
        self.assertEqual(len(res.json()['results']), 1)
        rid = res.json()['results'][0]['id']
        self.assertEqual(client_for(self.doc).patch(f'/api/practices/access-requests/{rid}/', {'status': 'onboarded'}, format='json').status_code, 403)
        self.assertEqual(client_for(self.agency).patch(f'/api/practices/access-requests/{rid}/', {'status': 'onboarded'}, format='json').json()['status'], 'onboarded')


class InboundReplyTests(TestCase):
    def setUp(self):
        self.a = Practice.objects.create(name='Alpha Dental', slug='alpha', email='a@alpha.test')
        self.b = Practice.objects.create(name='Beta Dental', slug='beta', email='b@beta.test')
        self.desk_a = make_user('desk@alpha.test', 'FRONT_DESK', practice=self.a)
        self.desk_b = make_user('desk@beta.test', 'FRONT_DESK', practice=self.b)
        self.appt = Appointment.objects.create(practice=self.a, patient_name='Pat Synthetic',
                                               patient_email='pat@example.test', intent='cleaning')
        self.cadence = EmailCadence.objects.create(practice=self.a, patient_email='pat@example.test', template='follow-up',
                                                   status=EmailCadence.STATUS_ACTIVE)

    def _send_reply(self, body='Hello Pat, which morning works?'):
        res = client_for(self.desk_a).post(f'/api/requests/{self.appt.id}/send-reply/', {
            'to_email': 'pat@example.test', 'subject': 'Your visit request', 'body': body}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        return mail.outbox[-1]

    def _patient_reply(self, sent, text='Thursday morning works for me.', msgid='<reply-1@mail.example>'):
        msg = EmailMessage()
        msg['From'] = 'Pat Synthetic <pat@example.test>'
        msg['To'] = 'a@alpha.test'
        msg['Subject'] = 'Re: Your visit request'
        msg['Message-ID'] = msgid
        msg['In-Reply-To'] = sent.extra_headers['Message-ID']
        msg.set_content(text + '\n\nOn Mon, Alpha Dental wrote:\n> Hello Pat')
        return msg

    def test_sent_email_carries_recorded_message_id(self):
        sent = self._send_reply()
        rec = Email.objects.get(direction=Email.DIRECTION_OUTGOING)
        self.assertEqual(sent.extra_headers['Message-ID'], rec.provider_message_id)
        self.assertTrue(rec.provider_message_id.endswith('.heyjarvis.ai>'))

    def test_reply_is_threaded_pauses_cadence_and_returns_request_to_inbox(self):
        sent = self._send_reply()
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'contacted')
        result = ingest_email_message(self._patient_reply(sent))
        self.assertEqual(result['status'], 'stored')
        reply = Email.objects.get(direction=Email.DIRECTION_INCOMING)
        self.assertEqual(reply.body, 'Thursday morning works for me.')
        self.assertEqual(reply.thread, Email.objects.get(direction=Email.DIRECTION_OUTGOING).thread)
        self.cadence.refresh_from_db()
        self.assertEqual(self.cadence.status, EmailCadence.STATUS_PAUSED)
        self.assertEqual(self.cadence.metadata['paused_reason'], 'patient_replied')
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'pending')
        self.assertIn('Patient replied', self.appt.internal_notes[-1]['text'])
        # Duplicate delivery is ignored.
        self.assertEqual(ingest_email_message(self._patient_reply(sent))['status'], 'duplicate')

    def test_unrelated_mail_is_never_imported(self):
        msg = EmailMessage()
        msg['From'] = 'someone@example.test'
        msg['Subject'] = 'Newsletter'
        msg['Message-ID'] = '<n@x>'
        msg.set_content('hello')
        self.assertEqual(ingest_email_message(msg)['status'], 'ignored')
        msg2 = self._patient_reply(type('S', (), {'extra_headers': {'Message-ID': '<forged@alpha.heyjarvis.ai>'}})())
        self.assertEqual(ingest_email_message(msg2)['status'], 'unmatched')
        self.assertFalse(Email.objects.filter(direction=Email.DIRECTION_INCOMING).exists())

    def test_history_visible_to_practice_only_and_follow_up_is_threaded(self):
        sent = self._send_reply()
        ingest_email_message(self._patient_reply(sent))
        detail = client_for(self.desk_a).get(f'/api/requests/{self.appt.id}/').json()
        self.assertEqual([e['direction'] for e in detail['email_history']], ['outgoing', 'incoming'])
        self.assertEqual(client_for(self.desk_b).get(f'/api/requests/{self.appt.id}/').status_code, 404)
        follow = self._send_reply('Great, Thursday 9am is held pending your confirmation.')
        self.assertEqual(follow.extra_headers.get('In-Reply-To'), '<reply-1@mail.example>')
        self.assertEqual(EmailThread.objects.filter(practice=self.a).count(), 1)

    def test_ai_draft_answers_the_latest_reply(self):
        sent = self._send_reply()
        ingest_email_message(self._patient_reply(sent, text='Can I bring my daughter too?'))
        with mock.patch('apps.ai_service.engine.AIEngine.available', new_callable=mock.PropertyMock, return_value=True), \
                mock.patch('apps.ai_service.engine.AIEngine.chat', return_value={'content': 'Draft text', 'intent': 'question'}) as chat:
            res = client_for(self.desk_a).post(f'/api/requests/{self.appt.id}/ai-draft/', {'action': 'draft'}, format='json')
        self.assertEqual(res.json()['result'], 'Draft text')
        self.assertIn('Can I bring my daughter too?', chat.call_args[0][0])

    def test_reply_check_endpoint_requires_auth_or_secret(self):
        self.assertEqual(APIClient().post('/api/emails/inbound/check/').status_code, 401)
        with override_settings(CRON_SECRET='s3cret-value', IMAP_HOST=''):
            self.assertEqual(APIClient().post('/api/emails/inbound/check/', HTTP_X_CRON_SECRET='wrong').status_code, 401)
            res = APIClient().post('/api/emails/inbound/check/', HTTP_X_CRON_SECRET='s3cret-value')
            self.assertEqual(res.status_code, 200)
            self.assertFalse(res.json()['configured'])
            self.assertFalse(client_for(self.desk_a).post('/api/emails/inbound/check/').json()['configured'])

class SchedulingPolicyTests(TestCase):
    def setUp(self):
        from apps.practices.models import BookingRules
        self.p = Practice.objects.create(name='Alpha', slug='alpha', email='a@x.test')
        BookingRules.objects.get_or_create(practice=self.p)
        self.doc = make_user('doc@alpha.test', 'PRACTICE_ADMIN', practice=self.p)
        self.desk = make_user('desk@alpha.test', 'FRONT_DESK', practice=self.p)

    def test_policies_persist_and_only_financing_reaches_the_assistant(self):
        from apps.ai_service.engine import build_practice_facts
        payload = {'new_patient_duration': 90, 'confirmation_hours': 48, 'no_show_fee': '65.00',
                   'financing_options': ['Cherry', 'CareCredit']}
        res = client_for(self.doc).put('/api/practices/booking-rules/', payload, format='json')
        self.assertIn(res.status_code, (200, 201), res.content)
        data = client_for(self.doc).get('/api/practices/booking-rules/').json()
        self.assertEqual(data['financing_options'], ['Cherry', 'CareCredit'])
        self.assertEqual(int(data['confirmation_hours']), 48)
        self.assertEqual(float(data['no_show_fee']), 65.0)
        facts = build_practice_facts(Practice.objects.get(pk=self.p.pk))
        self.assertIn('Cherry, CareCredit', facts)
        self.assertNotIn('65', facts)  # fee is not asserted to patients unless the practice adds it to guidance

    def test_front_desk_cannot_change_policies(self):
        res = client_for(self.desk).put('/api/practices/booking-rules/', {'no_show_fee': '0'}, format='json')
        self.assertIn(res.status_code, (403, 404))
