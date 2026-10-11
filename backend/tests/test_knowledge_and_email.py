"""Practice knowledge base, unanswered-question loop, and email reliability."""
import smtplib
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment
from apps.emails.models import Email
from apps.practices.models import BookingRules, EmailProvider, KnowledgeEntry, Practice, UnansweredQuestion
from apps.users.models import User

STRONG = 'Str0ng-Test-Passphrase-91'


def make_user(email, role, practice=None):
    return User.objects.create_user(username=email, email=email, password=STRONG, role=role, practice=practice)


def client_for(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return c


class Base(TestCase):
    def setUp(self):
        self.a = Practice.objects.create(name='Alpha Dental', slug='alpha', email='front@alpha.test', phone='(919) 555-0100', address='1 Main')
        self.b = Practice.objects.create(name='Beta Dental', slug='beta', email='b@beta.test', phone='2', address='2 Main')
        for p in (self.a, self.b):
            BookingRules.objects.get_or_create(practice=p)
        self.doc = make_user('doc@alpha.test', 'PRACTICE_ADMIN', self.a)
        self.desk = make_user('desk@alpha.test', 'FRONT_DESK', self.a)
        self.doc_b = make_user('doc@beta.test', 'PRACTICE_ADMIN', self.b)

    def chat(self, practice, *turns):
        c = APIClient()
        sid = f's-{practice.slug}-{len(turns)}-{turns[0][:5]}'
        c.post('/api/v1/widget/conversation/', {'client_key': practice.api_key, 'session_id': sid}, format='json')
        return [c.post('/api/v1/widget/message/', {'client_key': practice.api_key, 'session_id': sid, 'message': t},
                       format='json').json() for t in turns]


@override_settings(AI_PROVIDER='none')
class KnowledgeTests(Base):
    def test_admin_adds_entry_and_concierge_answers_from_it_without_ai(self):
        res = client_for(self.doc).post('/api/practices/knowledge/', {
            'category': 'insurance', 'title': 'Do you accept Delta Dental insurance?',
            'content': 'Yes, we are in network with Delta Dental PPO. Bring your card to your visit.'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        reply = self.chat(self.a, 'Do you take Delta Dental?')[0]['message']
        self.assertIn('in network with Delta Dental PPO', reply)
        self.assertFalse(UnansweredQuestion.objects.filter(practice=self.a).exists())

    def test_unknown_question_is_recorded_once_and_counted(self):
        self.chat(self.a, 'Is there parking near the office?')
        self.chat(self.a, 'Is there parking near the office?')
        q = UnansweredQuestion.objects.get(practice=self.a)
        self.assertEqual(q.times_asked, 2)

    def test_contact_details_are_removed_before_storing(self):
        from apps.practices.knowledge import record_unanswered
        record_unanswered(self.a, 'Can you email me at pat@example.test or text 919-555-0123 about whitening?')
        q = UnansweredQuestion.objects.get(practice=self.a)
        self.assertNotIn('555', q.question)
        self.assertNotIn('pat@example', q.question)
        self.assertIn('[phone]', q.question)

    def test_answering_a_question_creates_knowledge_and_closes_it(self):
        self.chat(self.a, 'Is there parking near the office?')
        q = UnansweredQuestion.objects.get(practice=self.a)
        listed = client_for(self.doc).get('/api/practices/knowledge/unanswered/').json()['results']
        self.assertEqual(listed[0]['id'], q.id)
        res = client_for(self.doc).post(f'/api/practices/knowledge/unanswered/{q.id}/', {
            'action': 'answer', 'content': 'Free parking is behind the building.'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(UnansweredQuestion.objects.get(pk=q.id).status, 'answered')
        reply = self.chat(self.a, 'Is there parking near the office please?')[0]['message']
        self.assertIn('Free parking is behind the building.', reply)

    def test_knowledge_reaches_the_ai_prompt(self):
        from apps.ai_service.engine import build_practice_facts
        KnowledgeEntry.objects.create(practice=self.a, category='doctor', title='Dr. Lee', content='Dr. Lee is a pediatric dentist.')
        facts = build_practice_facts(Practice.objects.get(pk=self.a.pk))
        self.assertIn('Dr. Lee is a pediatric dentist.', facts)
        self.assertIn('answer only from this', facts)
        self.assertNotIn('Dr. Lee', build_practice_facts(Practice.objects.get(pk=self.b.pk)))

    def test_permissions_and_tenant_isolation(self):
        entry = KnowledgeEntry.objects.create(practice=self.a, title='Hours note', content='Closed on holidays.')
        self.assertEqual(client_for(self.desk).get('/api/practices/knowledge/').status_code, 200)
        self.assertEqual(client_for(self.desk).post('/api/practices/knowledge/', {'title': 'x', 'content': 'y'}, format='json').status_code, 403)
        self.assertEqual(client_for(self.doc_b).patch(f'/api/practices/knowledge/{entry.id}/', {'content': 'hacked'}, format='json').status_code, 404)
        self.assertEqual(client_for(self.doc_b).get('/api/practices/knowledge/').json()['results'], [])
        self.assertEqual(client_for(self.doc).post('/api/practices/knowledge/', {'title': '', 'content': ''}, format='json').status_code, 400)

    def test_ai_deferral_is_recorded(self):
        with mock.patch('apps.ai_service.engine.AIEngine.available', new_callable=mock.PropertyMock, return_value=True), \
                mock.patch('apps.ai_service.engine.AIEngine.chat', return_value={'content': "I'm not sure about that. Please call us.", 'intent': 'question'}):
            self.chat(self.a, 'Do you offer sedation dentistry?')
        self.assertTrue(UnansweredQuestion.objects.filter(practice=self.a, question__icontains='sedation').exists())


@override_settings(DEFAULT_FROM_EMAIL='HeyJarvis Concierge <platform@mailer.test>')
class EmailReliabilityTests(Base):
    def setUp(self):
        super().setUp()
        self.appt = Appointment.objects.create(practice=self.a, patient_name='Pat', patient_email='pat@example.test', intent='cleaning')

    def send(self):
        return client_for(self.desk).post(f'/api/requests/{self.appt.id}/send-reply/', {
            'to_email': 'pat@example.test', 'subject': 'Hello', 'body': 'Hi Pat'}, format='json')

    def test_platform_mail_uses_aligned_sender_and_practice_reply_to(self):
        self.assertEqual(self.send().status_code, 200)
        msg = mail.outbox[-1]
        self.assertEqual(msg.from_email, 'Alpha Dental <platform@mailer.test>')
        self.assertEqual(msg.reply_to, ['front@alpha.test'])

    def test_failure_is_explained_and_never_shown_as_sent(self):
        err = smtplib.SMTPAuthenticationError(535, b'bad credentials')
        with mock.patch('django.core.mail.EmailMultiAlternatives.send', side_effect=err):
            res = self.send()
        self.assertEqual(res.status_code, 400)
        self.assertIn('rejected the login', res.json()['message'])
        rec = Email.objects.get(direction='outgoing')
        self.assertEqual(rec.status, 'failed')
        self.assertIn('app password', rec.error_message)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'pending')
        history = client_for(self.desk).get(f'/api/requests/{self.appt.id}/').json()['email_history']
        self.assertIn('rejected the login', history[0]['error_message'])

    def test_custom_smtp_keeps_the_practice_sender(self):
        EmailProvider.objects.create(practice=self.a, provider_type='smtp', smtp_host='smtp.alpha.test', smtp_port=587,
                                     from_email='hello@alpha.test', from_name='Alpha', is_active=True)
        with mock.patch('smtplib.SMTP') as smtp:
            res = self.send()
        self.assertEqual(res.status_code, 200, res.content)
        args = smtp.return_value.sendmail.call_args[0]
        self.assertEqual(args[0], 'hello@alpha.test')

    def test_error_descriptions_cover_common_failures(self):
        import socket
        from apps.emails.services import describe_send_error
        self.assertIn('did not respond', describe_send_error(socket.timeout()))
        self.assertIn('Could not connect', describe_send_error(ConnectionRefusedError()))
        self.assertIn('address was rejected', describe_send_error(smtplib.SMTPRecipientsRefused({})))

@override_settings(EMAIL_BACKEND='apps.emails.backends.ResendEmailBackend', RESEND_API_KEY='re_test_key',
                   DEFAULT_FROM_EMAIL='Concierge <mail@verified.test>')
class HttpsEmailBackendTests(Base):
    def setUp(self):
        super().setUp()
        self.appt = Appointment.objects.create(practice=self.a, patient_name='Pat', patient_email='pat@example.test', intent='cleaning')

    def test_payload_keeps_html_reply_to_and_threading_headers(self):
        with mock.patch('apps.emails.backends.ResendEmailBackend._post', return_value={'id': 'em_1'}) as post:
            from datetime import timedelta
            from django.utils import timezone
            res = client_for(self.desk).post(f'/api/requests/{self.appt.id}/send-reply/', {
                'to_email': 'pat@example.test', 'subject': 'Visit', 'body': 'Hi Pat',
                'offered_time': '10:00 AM', 'offered_date': (timezone.now() + timedelta(days=3)).date().isoformat(),
                'request_confirmation': True}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        payload = post.call_args[0][0]
        self.assertEqual(payload['from'], 'Alpha Dental <mail@verified.test>')
        self.assertEqual(payload['reply_to'], ['front@alpha.test'])
        self.assertIn('Confirm appointment', payload['html'])
        self.assertTrue(payload['headers']['Message-ID'].endswith('.heyjarvis.ai>'))
        self.assertEqual(Email.objects.get(direction='outgoing').status, 'sent')

    def test_api_rejection_is_explained(self):
        from apps.emails.backends import EmailAPIError
        with mock.patch('apps.emails.backends.ResendEmailBackend._post', side_effect=EmailAPIError(422)):
            res = client_for(self.desk).post(f'/api/requests/{self.appt.id}/send-reply/', {
                'to_email': 'pat@example.test', 'subject': 'Visit', 'body': 'Hi Pat'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('sending domain must be verified', res.json()['message'])
        self.assertEqual(Email.objects.get(direction='outgoing').status, 'failed')