"""Appointment confirmation requests: branded email, patient response page API, staff visibility."""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment, AppointmentOffer
from apps.practices.models import Practice, PracticeSettings
from apps.users.models import User

STRONG = 'Str0ng-Test-Passphrase-91'


def make_user(email, role, practice=None):
    return User.objects.create_user(username=email, email=email, password=STRONG, role=role, practice=practice)


def client_for(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return c


@override_settings(APP_PUBLIC_URL='https://concierge.example')
class ConfirmationRequestTests(TestCase):
    def setUp(self):
        self.a = Practice.objects.create(name='Alpha Family Dental', slug='alpha', email='front@alpha.test',
                                         phone='(919) 555-0100', address='1 Main St', city='Raleigh', state='NC',
                                         zip_code='27601', timezone='America/New_York')
        PracticeSettings.objects.get_or_create(practice=self.a, defaults={'widget_primary_color': '#1f4d3a'})
        self.b = Practice.objects.create(name='Beta Dental', slug='beta', email='b@beta.test')
        self.desk = make_user('desk@alpha.test', 'FRONT_DESK', self.a)
        self.desk_b = make_user('desk@beta.test', 'FRONT_DESK', self.b)
        self.appt = Appointment.objects.create(practice=self.a, patient_name='Pat Synthetic', patient_email='pat@example.test',
                                               patient_phone='5550199', intent='cleaning', service_name='Cleaning & exam')
        self.date = (timezone.now() + timedelta(days=5)).date()

    def send(self, client=None, **extra):
        payload = {'to_email': 'pat@example.test', 'subject': 'Your visit', 'body': 'Hi Pat,\nWe can see you then.',
                   'offered_time': '10:00 AM', 'offered_date': self.date.isoformat(), 'request_confirmation': True}
        payload.update(extra)
        return (client or client_for(self.desk)).post(f'/api/requests/{self.appt.id}/send-reply/', payload, format='json')

    def token_from_mail(self):
        text = mail.outbox[-1].body
        line = [l for l in text.splitlines() if l.startswith('https://concierge.example/appointment/')][0]
        return line.rsplit('/', 1)[1]

    def test_branded_email_with_summary_and_actions(self):
        res = self.send()
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['confirmation_requested'])
        msg = mail.outbox[-1]
        html = msg.alternatives[0][0]
        token = self.token_from_mail()
        for expected in ('Alpha Family Dental', self.date.strftime('%B'), '10:00 AM', 'Cleaning &amp; exam',
                         '1 Main St, Raleigh, NC 27601', '(919) 555-0100', 'Confirm appointment', 'Request a different time',
                         f'https://concierge.example/appointment/{token}?action=confirm',
                         f'https://concierge.example/appointment/{token}?action=reschedule'):
            self.assertIn(expected, html)
        self.assertIn('Hi Pat,<br>We can see you then.', html)
        offer = AppointmentOffer.objects.get()
        self.assertEqual(offer.status, 'pending')
        self.assertNotEqual(offer.token_hash, token)  # only the hash is stored
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'contacted')
        self.assertEqual(self.appt.offers.count(), 1)

    def test_validation_blocks_sending(self):
        self.assertEqual(self.send(offered_date='').status_code, 400)
        self.assertEqual(self.send(offered_time='').status_code, 400)
        self.assertEqual(self.send(offered_date=(timezone.now() - timedelta(days=2)).date().isoformat()).status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(AppointmentOffer.objects.exists())

    def test_plain_reply_unchanged_without_confirmation(self):
        res = self.send(request_confirmation=False, offered_date='')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['confirmation_requested'])
        self.assertEqual(mail.outbox[-1].alternatives, [])
        self.assertFalse(AppointmentOffer.objects.exists())

    def test_preview_renders_without_side_effects(self):
        res = client_for(self.desk).post(f'/api/requests/{self.appt.id}/offer-preview/', {
            'offered_date': self.date.isoformat(), 'offered_time': '9:30 AM', 'body': '<script>x</script> Hello'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('9:30 AM', res.json()['html'])
        self.assertIn('&lt;script&gt;', res.json()['html'])
        self.assertNotIn('<script>x', res.json()['html'])
        self.assertFalse(AppointmentOffer.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_public_view_is_read_only_and_minimal(self):
        self.send()
        token = self.token_from_mail()
        for _ in range(3):
            res = APIClient().get(f'/api/v1/appointment-offers/{token}/')
        data = res.json()
        self.assertEqual(data['state'], 'pending')
        self.assertEqual(data['patient_first_name'], 'Pat')
        body = res.content.decode()
        self.assertNotIn('pat@example.test', body)
        self.assertNotIn('5550199', body)
        self.assertEqual(AppointmentOffer.objects.get().status, 'pending')
        self.assertEqual(APIClient().get('/api/v1/appointment-offers/not-a-real-token/').status_code, 404)

    def test_confirm_then_reschedule_transitions(self):
        self.send()
        token = self.token_from_mail()
        c = APIClient()
        res = c.post(f'/api/v1/appointment-offers/{token}/confirm/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['changed'])
        self.assertEqual(res.json()['state'], 'confirmed')
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'confirmed')
        self.assertIsNotNone(self.appt.confirmed_at)
        self.assertIn('Patient confirmed', self.appt.internal_notes[-1]['text'])
        again = c.post(f'/api/v1/appointment-offers/{token}/confirm/')
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.json()['changed'])
        self.assertEqual(len(self.appt.internal_notes), 1)
        res = c.post(f'/api/v1/appointment-offers/{token}/reschedule/', {'note': 'Afternoons are better'}, format='json')
        self.assertEqual(res.json()['state'], 'reschedule_requested')
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'pending')
        self.assertIsNone(self.appt.confirmed_at)
        self.assertIn('Afternoons are better', self.appt.internal_notes[-1]['text'])
        self.assertEqual(c.post(f'/api/v1/appointment-offers/{token}/confirm/').status_code, 409)
        detail = client_for(self.desk).get(f'/api/requests/{self.appt.id}/').json()
        self.assertEqual(detail['latest_offer']['status'], 'reschedule_requested')
        self.assertEqual(detail['latest_offer']['patient_note'], 'Afternoons are better')

    def test_new_time_replaces_old_link(self):
        self.send()
        old = self.token_from_mail()
        self.send(offered_time='2:00 PM')
        new = self.token_from_mail()
        res = APIClient().post(f'/api/v1/appointment-offers/{old}/confirm/')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()['state'], 'superseded')
        self.assertEqual(APIClient().post(f'/api/v1/appointment-offers/{new}/confirm/').status_code, 200)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, 'confirmed')

    def test_failed_send_keeps_previous_link(self):
        self.send()
        old = self.token_from_mail()
        with mock.patch('apps.emails.services.send_practice_email', return_value={'success': False, 'error': 'x'}):
            self.assertEqual(self.send(offered_time='3:00 PM').status_code, 400)
        self.assertEqual(AppointmentOffer.objects.count(), 1)
        self.assertEqual(APIClient().get(f'/api/v1/appointment-offers/{old}/').json()['state'], 'pending')

    def test_expired_closed_and_suspended_links(self):
        self.send()
        token = self.token_from_mail()
        AppointmentOffer.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(APIClient().get(f'/api/v1/appointment-offers/{token}/').json()['state'], 'expired')
        self.assertEqual(APIClient().post(f'/api/v1/appointment-offers/{token}/confirm/').status_code, 409)
        AppointmentOffer.objects.update(expires_at=timezone.now() + timedelta(days=1))
        Appointment.objects.filter(pk=self.appt.pk).update(status='cancelled')
        self.assertEqual(APIClient().post(f'/api/v1/appointment-offers/{token}/confirm/').json()['state'], 'closed')
        Appointment.objects.filter(pk=self.appt.pk).update(status='contacted')
        Practice.objects.filter(pk=self.a.pk).update(active=False)
        self.assertEqual(APIClient().get(f'/api/v1/appointment-offers/{token}/').status_code, 404)
        self.assertEqual(APIClient().post(f'/api/v1/appointment-offers/{token}/confirm/').status_code, 404)

    def test_tenant_isolation(self):
        self.assertEqual(self.send(client=client_for(self.desk_b)).status_code, 404)
        res = client_for(self.desk_b).post(f'/api/requests/{self.appt.id}/offer-preview/', {
            'offered_date': self.date.isoformat(), 'offered_time': '9:30 AM'}, format='json')
        self.assertEqual(res.status_code, 404)
        self.assertFalse(AppointmentOffer.objects.exists())

    def test_unsafe_branding_values_are_ignored(self):
        from apps.appointments.offers import branding
        PracticeSettings.objects.filter(practice=self.a).update(widget_primary_color='red;background:url(x)')
        Practice.objects.filter(pk=self.a.pk).update(logo_url='javascript:alert(1)')
        brand = branding(Practice.objects.get(pk=self.a.pk))
        self.assertEqual(brand['color'], '#1f4d3a')
        self.assertEqual(brand['logo_url'], '')

    @override_settings(EMAIL_CONFIGURED=True)
    def test_practice_is_notified_of_the_answer(self):
        self.send()
        token = self.token_from_mail()
        before = len(mail.outbox)
        with self.captureOnCommitCallbacks(execute=True):
            APIClient().post(f'/api/v1/appointment-offers/{token}/confirm/')
        self.assertEqual(len(mail.outbox), before + 1)
        self.assertEqual(mail.outbox[-1].to, ['front@alpha.test'])
        self.assertIn('confirmed', mail.outbox[-1].subject)