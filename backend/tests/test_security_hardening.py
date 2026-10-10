"""Regression tests for authorization, tenant isolation and workflow fixes."""
import csv
import io

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment
from apps.conversations.models import Conversation, Message
from apps.emails.models import Email, EmailThread
from apps.practices.models import AuditLog, BookingRules, Practice, PracticeSettings
from apps.users.models import User

STRONG = 'Tr1cky-Molar-Passphrase!'


def make_user(email, role, practice=None, **extra):
    return User.objects.create_user(
        username=email, email=email, password=STRONG, role=role, practice=practice, **extra
    )


class TenantFixture(TestCase):
    def setUp(self):
        self.a = Practice.objects.create(name='Alpha Dental', slug='alpha', email='a@alpha.test', phone='1', address='x')
        self.b = Practice.objects.create(name='Beta Dental', slug='beta', email='b@beta.test', phone='2', address='y')
        self.agency = make_user('agency@platform.test', 'AGENCY_ADMIN', practice=self.a)
        self.admin_a = make_user('doc@alpha.test', 'PRACTICE_ADMIN', practice=self.a)
        self.desk_a = make_user('desk@alpha.test', 'FRONT_DESK', practice=self.a)
        self.admin_b = make_user('doc@beta.test', 'PRACTICE_ADMIN', practice=self.b)
        self.conv_a = Conversation.objects.create(practice=self.a, patient_name='Pat A', patient_email='pa@example.com')
        self.conv_b = Conversation.objects.create(practice=self.b, patient_name='Pat B', patient_email='pb@example.com')
        self.appt_a = Appointment.objects.create(practice=self.a, patient_name='Pat A', intent='cleaning')
        self.appt_b = Appointment.objects.create(practice=self.b, patient_name='Pat B', intent='cleaning')

    def client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        return client


class PrivilegeEscalationTests(TenantFixture):
    def test_self_profile_cannot_change_role_or_practice(self):
        c = self.client_for(self.desk_a)
        res = c.patch('/api/auth/me/', {'role': 'AGENCY_ADMIN', 'practice': self.b.id, 'first_name': 'Emma'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.desk_a.refresh_from_db()
        self.assertEqual(self.desk_a.role, 'FRONT_DESK')
        self.assertEqual(self.desk_a.practice_id, self.a.id)
        self.assertEqual(self.desk_a.first_name, 'Emma')

    def test_practice_admin_cannot_create_agency_admin_via_team(self):
        c = self.client_for(self.admin_a)
        res = c.post('/api/practices/team/', {'email': 'evil@alpha.test', 'role': 'AGENCY_ADMIN'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.filter(email='evil@alpha.test').exists())

    def test_team_invite_returns_usable_temporary_password(self):
        c = self.client_for(self.admin_a)
        res = c.post('/api/practices/team/', {'email': 'new@alpha.test', 'role': 'FRONT_DESK'}, format='json')
        self.assertEqual(res.status_code, 201)
        login = APIClient().post('/api/auth/login/', {'email': 'new@alpha.test', 'password': res.data['temporary_password']}, format='json')
        self.assertEqual(login.status_code, 200)

    def test_practice_admin_cannot_reset_agency_admin_password(self):
        c = self.client_for(self.admin_a)
        url = f'/api/practices/{self.a.id}/users/{self.agency.id}/action/'
        res = c.post(url, {'action': 'reset_password', 'password': 'Another-Strong-Pass-99'}, format='json')
        self.assertEqual(res.status_code, 403)
        self.agency.refresh_from_db()
        self.assertTrue(self.agency.check_password(STRONG))

    def test_practice_admin_cannot_change_agency_admin_role(self):
        res = self.client_for(self.admin_a).put(f'/api/practices/team/{self.agency.id}/', {'role': 'FRONT_DESK'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_front_desk_cannot_manage_team(self):
        res = self.client_for(self.desk_a).post('/api/practices/team/', {'email': 'x@alpha.test'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_practice_admin_cannot_change_tenant_status_or_subscription(self):
        res = self.client_for(self.admin_a).put('/api/practices/', {'active': False, 'subscription_status': 'free', 'name': 'Alpha Renamed'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.a.refresh_from_db()
        self.assertTrue(self.a.active)
        self.assertEqual(self.a.subscription_status, 'active')
        self.assertEqual(self.a.name, 'Alpha Renamed')

    def test_weak_password_rejected_for_new_staff(self):
        res = self.client_for(self.admin_a).post(
            f'/api/practices/{self.a.id}/users/', {'email': 'weak@alpha.test', 'password': '123'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_public_registration_disabled_by_default(self):
        res = APIClient().post('/api/auth/register/', {
            'email': 'x@y.test', 'password': STRONG, 'password_confirm': STRONG, 'role': 'PRACTICE_ADMIN'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_agency_onboarding_requires_admin_password(self):
        res = self.client_for(self.agency).post('/api/practices/all/', {
            'name': 'Gamma', 'email': 'g@gamma.test', 'admin_email': 'doc@gamma.test', 'admin_password': ''}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Practice.objects.filter(name='Gamma').exists())

    def test_non_agency_cannot_list_practices(self):
        self.assertEqual(self.client_for(self.admin_a).get('/api/practices/all/').status_code, 403)


class TenantIsolationTests(TenantFixture):
    def test_cannot_read_other_tenant_conversation_or_appointment(self):
        c = self.client_for(self.admin_a)
        self.assertEqual(c.get(f'/api/conversations/{self.conv_b.id}/').status_code, 404)
        self.assertEqual(c.get(f'/api/requests/{self.appt_b.id}/').status_code, 404)
        self.assertEqual(c.post(f'/api/requests/{self.appt_b.id}/status/', {'status': 'spam'}, format='json').status_code, 404)
        self.assertEqual(c.post(f'/api/conversations/{self.conv_b.id}/close/').status_code, 404)

    def test_header_spoofing_ignored_for_tenant_staff(self):
        c = self.client_for(self.admin_a)
        res = c.get(f'/api/requests/{self.appt_b.id}/', HTTP_X_PRACTICE_ID=str(self.b.id))
        self.assertEqual(res.status_code, 404)
        lst = c.get('/api/requests/', HTTP_X_PRACTICE_ID=str(self.b.id))
        self.assertEqual({r['id'] for r in lst.data}, {str(self.appt_a.id)})

    def test_cannot_move_records_to_other_tenant(self):
        c = self.client_for(self.admin_a)
        c.patch(f'/api/conversations/{self.conv_a.id}/', {'practice': self.b.id}, format='json')
        c.patch(f'/api/requests/{self.appt_a.id}/', {'practice': self.b.id}, format='json')
        self.conv_a.refresh_from_db()
        self.appt_a.refresh_from_db()
        self.assertEqual(self.conv_a.practice_id, self.a.id)
        self.assertEqual(self.appt_a.practice_id, self.a.id)

    def test_cannot_assign_staff_from_other_tenant(self):
        res = self.client_for(self.admin_a).patch(f'/api/requests/{self.appt_a.id}/', {'assigned_to': str(self.admin_b.id)}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_email_threads_are_tenant_scoped(self):
        t_b = EmailThread.objects.create(practice=self.b, patient_email='pb@example.com', subject='Beta secret')
        Email.objects.create(thread=t_b, direction='outgoing', from_email='b@beta.test', to_email='pb@example.com', subject='Beta secret', body='PHI')
        c = self.client_for(self.admin_a)
        self.assertEqual(c.get('/api/emails/threads/').data['count'], 0)
        self.assertEqual(c.get('/api/emails/').data['count'], 0)
        self.assertEqual(c.get(f'/api/emails/threads/{t_b.id}/').status_code, 404)

    def test_messages_scoped(self):
        Message.objects.create(conversation=self.conv_b, sender='user', content='secret')
        res = self.client_for(self.admin_a).get(f'/api/conversations/{self.conv_b.id}/messages/')
        self.assertEqual(res.data, [])

    def test_agency_admin_can_switch_workspace(self):
        c = self.client_for(self.agency)
        res = c.get(f'/api/requests/{self.appt_b.id}/', HTTP_X_PRACTICE_ID=str(self.b.id))
        self.assertEqual(res.status_code, 200)
        res = c.get('/api/practices/settings/', HTTP_X_PRACTICE_ID=str(self.b.id))
        self.assertEqual(res.status_code, 200)
        self.assertTrue(PracticeSettings.objects.filter(practice=self.b).exists())


class AuthFlowTests(TenantFixture):
    def test_login_refresh_logout_blacklists_refresh_token(self):
        api = APIClient()
        res = api.post('/api/auth/login/', {'email': 'DOC@alpha.test', 'password': STRONG}, format='json')
        self.assertEqual(res.status_code, 200)
        refresh = res.data['refresh']
        rotated = api.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(rotated.status_code, 200)
        new_refresh = rotated.data['refresh']
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {rotated.data['access']}")
        self.assertEqual(api.post('/api/auth/logout/', {'refresh': new_refresh}, format='json').status_code, 200)
        api.credentials()
        self.assertEqual(api.post('/api/auth/token/refresh/', {'refresh': new_refresh}, format='json').status_code, 401)

    def test_invalid_login_rejected_generically(self):
        res = APIClient().post('/api/auth/login/', {'email': 'doc@alpha.test', 'password': 'wrong'}, format='json')
        self.assertEqual(res.status_code, 400)
        res2 = APIClient().post('/api/auth/login/', {'email': 'nobody@alpha.test', 'password': 'wrong'}, format='json')
        self.assertEqual(res.data, res2.data)

    def test_login_works_with_stale_bearer_header(self):
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION='Bearer expired.or.garbage')
        self.assertEqual(api.post('/api/auth/login/', {'email': 'doc@alpha.test', 'password': STRONG}, format='json').status_code, 200)

    def test_login_rate_limited(self):
        from unittest import mock
        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle
        cache.clear()
        api = APIClient()
        with mock.patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'login': '3/min'}):
            codes = [api.post('/api/auth/login/', {'email': 'doc@alpha.test', 'password': 'bad'}, format='json').status_code for _ in range(5)]
        self.assertEqual(codes[:3], [400, 400, 400])
        self.assertEqual(codes[3:], [429, 429])
        cache.clear()

    def test_auth_config_hides_demo_accounts_when_disabled(self):
        res = APIClient().get('/api/auth/config/')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['demo_accounts_enabled'])
        self.assertEqual(res.data['demo_accounts'], [])

    def test_seed_without_demo_mode_creates_no_accounts(self):
        from apps.users.seed_data import seed_all_demo_data
        self.assertEqual(seed_all_demo_data(), [])
        self.assertFalse(User.objects.filter(email='admin@raleighdentistry.com').exists())

    @override_settings(DEMO_ACCOUNTS_ENABLED=True)
    def test_demo_accounts_have_no_superuser_rights(self):
        from apps.users.seed_data import seed_all_demo_data
        seed_all_demo_data()
        admin = User.objects.get(email='admin@raleighdentistry.com')
        self.assertFalse(admin.is_superuser)
        self.assertFalse(admin.is_staff)
        self.assertTrue(admin.is_agency_admin)

    def test_seed_endpoint_requires_agency(self):
        self.assertEqual(self.client_for(self.desk_a).post('/api/auth/seed/').status_code, 403)


class SettingsPersistenceTests(TenantFixture):
    def test_practice_admin_can_save_settings_and_booking_rules(self):
        c = self.client_for(self.admin_a)
        res = c.put('/api/practices/settings/', {'widget_title': 'Alpha Concierge', 'notify_on_question': False}, format='json')
        self.assertEqual(res.status_code, 200)
        res = c.put('/api/practices/booking-rules/', {'business_hours': {'monday': {'open': '08:00', 'close': '17:00', 'closed': False}}}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(c.get('/api/practices/settings/').data['widget_title'], 'Alpha Concierge')
        self.assertEqual(BookingRules.objects.get(practice=self.a).business_hours['monday']['open'], '08:00')

    def test_front_desk_cannot_save_settings(self):
        res = self.client_for(self.desk_a).put('/api/practices/settings/', {'widget_title': 'x'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_audit_log_redacts_secrets(self):
        self.client_for(self.admin_a).put('/api/practices/email-config/', {
            'provider_type': 'smtp', 'smtp_host': 'smtp.example.com', 'smtp_port': 587, 'smtp_password': 'hunter2-secret'}, format='json')
        self.assertFalse(any('hunter2' in str(l.details) for l in AuditLog.objects.all()))

    def test_integration_endpoint_works(self):
        res = self.client_for(self.admin_a).get(f'/api/practices/{self.a.id}/integration/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(self.a.api_key, res.data['embed_script'])

    def test_invalid_status_rejected(self):
        res = self.client_for(self.desk_a).post(f'/api/requests/{self.appt_a.id}/status/', {'status': 'hacked'}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.client_for(self.desk_a).post(f'/api/requests/{self.appt_a.id}/status/', {'assigned_to': 'not-a-uuid'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_csv_export_neutralises_formulas(self):
        Appointment.objects.create(practice=self.a, patient_name='=HYPERLINK("http://evil")', intent='question')
        res = self.client_for(self.admin_a).get('/api/practices/export/leads/')
        rows = list(csv.reader(io.StringIO(res.content.decode())))
        self.assertTrue(any(r[0].startswith("'=") for r in rows[1:]))

    def test_domain_validation(self):
        c = self.client_for(self.admin_a)
        self.assertEqual(c.post('/api/practices/domains/', {'hostname': 'https://www.alpha.test/path'}, format='json').status_code, 201)
        self.assertEqual(c.post('/api/practices/domains/', {'hostname': 'not a domain'}, format='json').status_code, 400)


class PublicWidgetTests(TenantFixture):
    def test_unknown_slug_does_not_fuzzy_match_other_practice(self):
        res = APIClient().post('/api/chat/chat/', {'message': 'hi', 'practice_slug': 'alpha-xyz'}, format='json')
        self.assertEqual(res.status_code, 404)

    def test_no_key_or_slug_rejected_outside_debug(self):
        res = APIClient().post('/api/chat/chat/', {'message': 'hi'}, format='json')
        self.assertEqual(res.status_code, 404)

    def test_widget_submit_creates_request_and_notifies_practice(self):
        res = APIClient().post('/api/v1/widget/submit/', {
            'client_key': self.a.api_key, 'patient_name': 'New Pat', 'patient_email': 'np@example.com',
            'preferred_date': 'Monday'}, format='json')
        self.assertEqual(res.status_code, 200)
        appt = Appointment.objects.get(patient_email='np@example.com')
        self.assertEqual(appt.practice_id, self.a.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['a@alpha.test'])

    def test_notification_respects_toggle(self):
        PracticeSettings.objects.filter(practice=self.a).update(notify_on_new_request=False)
        APIClient().post('/api/v1/widget/submit/', {'client_key': self.a.api_key, 'patient_email': 'q@example.com'}, format='json')
        self.assertEqual(len(mail.outbox), 0)

    def test_widget_submit_requires_contact(self):
        res = APIClient().post('/api/v1/widget/submit/', {'client_key': self.a.api_key, 'patient_name': 'Anon'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_hosted_config_includes_branding(self):
        res = APIClient().get('/api/concierge/alpha/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('primary_color', res.data)


class StaffReplyTests(TenantFixture):
    def test_staff_reply_saved_as_staff_and_emailed(self):
        res = self.client_for(self.desk_a).post(f'/api/conversations/{self.conv_a.id}/messages/', {'content': 'We can see you Tuesday.'}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['message']['sender'], 'staff')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['pa@example.com'])
        thread = EmailThread.objects.get(patient_email='pa@example.com')
        self.assertEqual(thread.practice_id, self.a.id)

    def test_staff_reply_other_tenant_404(self):
        res = self.client_for(self.desk_a).post(f'/api/conversations/{self.conv_b.id}/messages/', {'content': 'x'}, format='json')
        self.assertEqual(res.status_code, 404)

    def test_spa_concierge_route_is_frameable(self):
        res = self.client.get('/concierge/alpha')
        self.assertFalse(res.has_header('X-Frame-Options'))


class WorkflowAdditionsTests(TenantFixture):
    def test_tab_filter_matches_stats(self):
        Appointment.objects.create(practice=self.a, patient_name='E1', intent='emergency')
        Appointment.objects.create(practice=self.a, patient_name='E2', intent='question', urgency='URGENT')
        c = self.client_for(self.desk_a)
        stats = c.get('/api/requests/stats/').data
        listed = c.get('/api/requests/', {'tab': 'emergency'}).data
        self.assertEqual(stats['emergency'], 2)
        self.assertEqual(len(listed), 2)
        self.assertEqual(len(c.get('/api/requests/', {'tab': 'appointment'}).data), stats['appointment'])

    def test_business_rules_extra_fields_persist_and_validate(self):
        c = self.client_for(self.admin_a)
        res = c.put('/api/practices/booking-rules/', {
            'emergency_phone': '919-555-0199', 'handoff_enabled': False, 'custom_instructions': 'Mention free parking.',
            'cancellation_notice_hours': 48}, format='json')
        self.assertEqual(res.status_code, 200)
        rules = BookingRules.objects.get(practice=self.a)
        self.assertFalse(rules.handoff_enabled)
        self.assertEqual(rules.cancellation_notice_hours, 48)
        bad = c.put('/api/practices/booking-rules/', {'business_hours': {'monday': {'open': '18:00', 'close': '09:00'}}}, format='json')
        self.assertEqual(bad.status_code, 400)

    def test_handoff_disabled_does_not_create_lead(self):
        from apps.conversations.state_machine import ConciergeStateMachine
        BookingRules.objects.filter(practice=self.a).update(handoff_enabled=False)
        self.a.refresh_from_db()
        conv = Conversation.objects.create(practice=self.a, state=Conversation.STATE_HANDOFF)
        result = ConciergeStateMachine(conv, self.a).process_message('talk to a person')
        self.assertIn(self.a.phone, result['message'])
        self.assertFalse(Appointment.objects.filter(conversation=conv).exists())

    def test_notification_routed_by_intent(self):
        PracticeSettings.objects.filter(practice=self.a).update(notification_emails={
            'general': 'general@alpha.test', 'emergency': 'oncall@alpha.test'})
        APIClient().post('/api/v1/widget/submit/', {'client_key': self.a.api_key, 'patient_email': 'x@example.com'}, format='json')
        self.assertEqual(mail.outbox[-1].to, ['general@alpha.test'])
        from apps.emails.services import notify_practice_of_request
        practice = Practice.objects.get(pk=self.a.pk)
        appt = Appointment.objects.create(practice=practice, intent='emergency', patient_name='Ouch')
        self.assertTrue(notify_practice_of_request(appt))
        self.assertEqual(mail.outbox[-1].to, ['oncall@alpha.test'])

    def test_metrics_email_delivery_is_real(self):
        c = self.client_for(self.admin_a)
        self.assertIsNone(c.get('/api/practices/metrics/').data['email_delivery'])
        c.post(f'/api/conversations/{self.conv_a.id}/messages/', {'content': 'Hello'}, format='json')
        data = c.get('/api/practices/metrics/').data
        self.assertEqual(data['emails_sent'], 1)
        self.assertEqual(data['email_delivery'], 100.0)

    def test_invalid_notification_email_rejected(self):
        res = self.client_for(self.admin_a).put('/api/practices/settings/', {'notification_emails': {'general': 'not-an-email'}}, format='json')
        self.assertEqual(res.status_code, 400)
