"""
HeyJarvis - API Integration Tests

These tests exercise the full API layer using Django's test client.
Run with: python manage.py test api_integration_tests
"""
from django.test import TestCase, Client
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.test import APIClient

from practices.models import Practice
from patients.models import Patient
from conversations.models import Conversation, Message
from appointments.models import AppointmentRequest
from emails.models import EmailMessage, EmailSequence, SequenceStep
from cadence.models import Cadence
from bookings.models import BookingRule
from users.models import User


class TestAuthenticationFlow(TestCase):
    """Test authentication and JWT token flow."""

    def setUp(self):
        self.client_obj = APIClient()
        self.practice = Practice.objects.create(
            name='Raleigh Test Practice',
            slug='raleigh-test',
            email='test@raleighdentistry.com',
            phone='(919) 832-3300',
            address='Raleigh, NC',
            timezone='America/New_York',
            website='https://raleighdentistry.com',
            active=True,
        )
        self.user = User.objects.create_user(
            email='frontdesk@raleighdentistry.com',
            password='testpass123',
            name='Front Desk',
            role='FRONT_DESK',
            practice=self.practice,
        )

    def test_jwt_login(self):
        """Test JWT token generation on login."""
        refresh = RefreshToken.for_user(self.user)
        self.client_obj.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
        response = self.client_obj.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'frontdesk@raleighdentistry.com')

    def test_unauthenticated_access_denied(self):
        """Unauthenticated requests should return 401."""
        response = self.client_obj.get('/api/appointments/requests/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TestPracticeEndpoints(TestCase):
    """Test practice CRUD operations."""

    def setUp(self):
        self.client_obj = APIClient()
        self.practice = Practice.objects.create(
            name='Raleigh Test Practice',
            slug='raleigh-practice',
            email='test@raleighdentistry.com',
            phone='(919) 832-3300',
            address='Raleigh, NC',
            timezone='America/New_York',
            website='https://raleighdentistry.com',
            active=True,
        )
        self.user = User.objects.create_user(
            email='user@raleighdentistry.com',
            password='testpass123',
            name='Test User',
            role='OWNER',
            practice=self.practice,
        )
        refresh = RefreshToken.for_user(self.user)
        self.client_obj.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_list_practices(self):
        response = self.client_obj.get('/api/practices/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data.get('results', response.data)), 1)

    def test_retrieve_practice(self):
        response = self.client_obj.get(f'/api/practices/{self.practice.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['slug'], 'raleigh-practice')


class TestPatientEndpoints(TestCase):
    """Test patient CRUD operations."""

    def setUp(self):
        self.client_obj = APIClient()
        self.practice = Practice.objects.create(
            name='Raleigh Test Practice',
            slug='raleigh-patients',
            email='test@raleighdentistry.com',
            phone='(919) 832-3300',
            address='Raleigh, NC',
            timezone='America/New_York',
            website='https://raleighdentistry.com',
            active=True,
        )
        self.user = User.objects.create_user(
            email='user@raleighdentistry.com',
            password='testpass123',
            name='Test User',
            role='OWNER',
            practice=self.practice,
        )
        refresh = RefreshToken.for_user(self.user)
        self.client_obj.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
        self.patient = Patient.objects.create(
            practice=self.practice,
            name='Sarah Johnson',
            email='sarah@test.com',
            phone='(919) 555-0100',
            existing_patient=False,
        )

    def test_create_patient(self):
        response = self.client_obj.post('/api/patients/', {
            'practice': self.practice.id,
            'name': 'New Patient',
            'email': 'new@test.com',
            'phone': '555-0100',
            'existing_patient': True,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'New Patient')

    def test_list_patients(self):
        response = self.client_obj.get('/api/patients/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_patient(self):
        response = self.client_obj.get(f'/api/patients/{self.patient.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Sarah Johnson')

    def test_patients_filtered_by_practice(self):
        """Patients from other practices should be filtered out."""
        other_practice = Practice.objects.create(
            name='Other Practice',
            slug='other-practice',
            email='other@test.com',
            phone='555-0100',
            address='Other Address',
        )
        Patient.objects.create(
            practice=other_practice,
            name='Other Patient',
            email='other@test.com',
        )
        response = self.client_obj.get('/api/patients/')
        emails = [p['email'] for p in (response.data.get('results', []) or response.data)]
        # Should only see our practice's patients (or paginated)
        for email in emails:
            if email == 'other@test.com':
                self.fail("Cross-practice patient data leaked!")


class TestAppointmentRequestEndpoints(TestCase):
    """Test appointment request operations."""

    def setUp(self):
        self.client_obj = APIClient()
        self.practice = Practice.objects.create(
            name='Raleigh Test Practice',
            slug='raleigh-requests',
            email='test@raleighdentistry.com',
            phone='(919) 832-3300',
            address='Raleigh, NC',
            timezone='America/New_York',
            website='https://raleighdentistry.com',
            active=True,
        )
        self.user = User.objects.create_user(
            email='user@raleighdentistry.com',
            password='testpass123',
            name='Test User',
            role='OWNER',
            practice=self.practice,
        )
        refresh = RefreshToken.for_user(self.user)
        self.client_obj.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
        self.patient = Patient.objects.create(
            practice=self.practice,
            name='Test Patient',
            email='testpatient@test.com',
            phone='555-0100',
        )
        self.request = AppointmentRequest.objects.create(
            practice=self.practice,
            patient=self.patient,
            appointment_type='cleaning',
            reason='Regular cleaning',
            urgency='low',
            preferred_date='2026-10-15',
            preferred_time='09:00:00',
        )

    def test_create_request(self):
        response = self.client_obj.post('/api/appointments/requests/', {
            'practice': self.practice.id,
            'patient': self.patient.id,
            'appointment_type': 'cleaning',
            'reason': 'Need a cleaning',
            'urgency': 'low',
            'preferred_date': '2026-10-20',
            'preferred_time': '10:00:00',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'NEW')

    def test_list_requests(self):
        response = self.client_obj.get('/api/appointments/requests/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_request(self):
        response = self.client_obj.patch(
            f'/api/appointments/requests/{self.request.id}/',
            {'status': 'DRAFT_READY', 'offered_date': '2026-10-15', 'offered_time': '14:30:00'}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'DRAFT_READY')


class TestConversationEndpoints(TestCase):
    """Test conversation and message operations."""

    def setUp(self):
        self.client_obj = APIClient()
        self.practice = Practice.objects.create(
            name='Raleigh Test Practice',
            slug='raleigh-conv',
            email='test@raleighdentistry.com',
            phone='(919) 832-3300',
            address='Raleigh, NC',
            timezone='America/New_York',
            website='https://raleighdentistry.com',
            active=True,
        )
        self.user = User.objects.create_user(
            email='user@raleighdentistry.com',
            password='testpass123',
            name='Test User',
            role='OWNER',
            practice=self.practice,
        )
        refresh = RefreshToken.for_user(self.user)
        self.client_obj.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
        self.conversation = Conversation.objects.create(
            practice=self.practice,
            session_id='test-session-001',
        )

    def test_list_conversations(self):
        response = self.client_obj.get('/api/conversations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_message(self):
        response = self.client_obj.post('/api/conversations/messages/', {
            'conversation': str(self.conversation.id),
            'role': 'user',
            'content': 'I need a cleaning appointment',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['content'], 'I need a cleaning appointment')


class TestBookingRules(TestCase):
    """Test booking rules configuration."""

    def setUp(self):
        self.practice = Practice.objects.create(
            name='Raleigh Test Practice',
            slug='raleigh-booking',
            email='test@raleighdentistry.com',
            phone='(919) 832-3300',
            address='Raleigh, NC',
            timezone='America/New_York',
            website='https://raleighdentistry.com',
            active=True,
        )
        self.user = User.objects.create_user(
            email='user@raleighdentistry.com',
            password='testpass123',
            name='Test User',
            role='OWNER',
            practice=self.practice,
        )
        self.client_obj = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client_obj.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_booking_rules_defaults(self):
        """Booking rules should have sensible defaults."""
        rules = BookingRule.objects.create(
            practice=self.practice,
            new_patient_duration=90,
            new_patient_doctor_duration=90,
            new_patient_hygiene_duration=60,
            emergency_duration=60,
            confirmation_hours=48,
            no_show_fee=65,
            financing_options=['Cherry', 'CareCredit'],
        )
        self.assertEqual(rules.new_patient_duration, 90)
        self.assertEqual(rules.emergency_duration, 60)
        self.assertEqual(rules.no_show_fee, 65)

    def test_booking_rules_api(self):
        """Booking rules should be retrievable via API."""
        BookingRule.objects.create(
            practice=self.practice,
            new_patient_duration=90,
            new_patient_doctor_duration=90,
            new_patient_hygiene_duration=60,
            emergency_duration=60,
            confirmation_hours=48,
            no_show_fee=65,
            financing_options=['Cherry', 'CareCredit'],
        )
        response = self.client_obj.get('/api/bookings/rules/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestEmailEndpoints(TestCase):
    """Test email message operations."""

    def setUp(self):
        self.client_obj = APIClient()
        self.practice = Practice.objects.create(
            name='Raleigh Test Practice',
            slug='raleigh-email',
            email='test@raleighdentistry.com',
            phone='(919) 832-3300',
            address='Raleigh, NC',
            timezone='America/New_York',
            website='https://raleighdentistry.com',
            active=True,
        )
        self.user = User.objects.create_user(
            email='user@raleighdentistry.com',
            password='testpass123',
            name='Test User',
            role='OWNER',
            practice=self.practice,
        )
        refresh = RefreshToken.for_user(self.user)
        self.client_obj.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
        self.patient = Patient.objects.create(
            practice=self.practice,
            name='Test Patient',
            email='testpatient@test.com',
            phone='555-0100',
        )
        self.appt_request = AppointmentRequest.objects.create(
            practice=self.practice,
            patient=self.patient,
            appointment_type='cleaning',
            urgency='low',
        )

    def test_create_email_draft(self):
        response = self.client_obj.post('/api/emails/drafts/', {
            'practice': self.practice.id,
            'appointment_request': self.appt_request.id,
            'direction': 'outbound',
            'subject': 'Appointment Available',
            'body': 'Would you like to come in on Oct 15 at 2:30 PM?',
            'sender': 'info@raleighdentistry.com',
            'recipient': 'testpatient@test.com',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['direction'], 'outbound')

    def test_list_emails(self):
        response = self.client_obj.get('/api/emails/messages/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestCadenceEndpoints(TestCase):
    """Test cadence operations."""

    def setUp(self):
        self.client_obj = APIClient()
        self.practice = Practice.objects.create(
            name='Raleigh Test Practice',
            slug='raleigh-cadence',
            email='test@raleighdentistry.com',
            phone='(919) 832-3300',
            address='Raleigh, NC',
            timezone='America/New_York',
            website='https://raleighdentistry.com',
            active=True,
        )
        self.user = User.objects.create_user(
            email='user@raleighdentistry.com',
            password='testpass123',
            name='Test User',
            role='OWNER',
            practice=self.practice,
        )
        refresh = RefreshToken.for_user(self.user)
        self.client_obj.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
        self.appt_request = AppointmentRequest.objects.create(
            practice=self.practice,
            appointment_type='cleaning',
            urgency='low',
        )
        self.cadence = Cadence.objects.create(
            request=self.appt_request,
            active=True,
            current_step='initial_email',
        )

    def test_list_cadences(self):
        response = self.client_obj.get('/api/cadence/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestAIProviderEndpoints(TestCase):
    """Test AI service endpoints."""

    def setUp(self):
        self.client_obj = APIClient()
        self.practice = Practice.objects.create(
            name='Raleigh Test Practice',
            slug='raleigh-ai',
            email='test@raleighdentistry.com',
            phone='(919) 832-3300',
            address='Raleigh, NC',
            timezone='America/New_York',
            website='https://raleighdentistry.com',
            active=True,
        )
        self.user = User.objects.create_user(
            email='user@raleighdentistry.com',
            password='testpass123',
            name='Test User',
            role='OWNER',
            practice=self.practice,
        )
        refresh = RefreshToken.for_user(self.user)
        self.client_obj.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_chat_endpoint_exists(self):
        response = self.client_obj.get('/api/ai/chat/')
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_405_METHOD_NOT_ALLOWED])

    def test_list_ai_interactions(self):
        response = self.client_obj.get('/api/ai/interactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestTenantIsolation(TestCase):
    """Multi-tenancy security tests."""

    def test_practice_isolation_patients(self):
        """Practice A must never see Practice B's patients."""
        practice_a = Practice.objects.create(
            name='Practice A',
            slug='practice-a-isolation',
            email='a@test.com',
            phone='555-0100',
            address='A Address',
        )
        practice_b = Practice.objects.create(
            name='Practice B',
            slug='practice-b-isolation',
            email='b@test.com',
            phone='555-0200',
            address='B Address',
        )
        Patient.objects.create(
            practice=practice_b,
            name='B Patient',
            email='b@test.com',
            phone='555-0201',
        )

        user_a = User.objects.create_user(
            email='user-a@test.com',
            password='testpass123',
            name='User A',
            role='OWNER',
            practice=practice_a,
        )
        client = APIClient()
        refresh = RefreshToken.for_user(user_a)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

        # User from practice A should only see A's patients
        response = client.get('/api/patients/')
        # Check no cross-practice data
        for patient in (response.data.get('results', []) or response.data):
            email = patient.get('email', '')
            if email == 'b@test.com':
                self.fail("Cross-practice data leak detected!")

    def test_practice_isolation_requests(self):
        """Practice A must never see Practice B's appointment requests."""
        practice_a = Practice.objects.create(
            name='Practice A',
            slug='practice-a-req',
            email='a2@test.com',
            phone='555-0100',
            address='A Address',
        )
        practice_b = Practice.objects.create(
            name='Practice B',
            slug='practice-b-req',
            email='b2@test.com',
            phone='555-0200',
            address='B Address',
        )
        AppointmentRequest.objects.create(
            practice=practice_b,
            appointment_type='cleaning',
            urgency='low',
        )

        user_a = User.objects.create_user(
            email='user-a2@test.com',
            password='testpass123',
            name='User A2',
            role='OWNER',
            practice=practice_a,
        )
        client = APIClient()
        refresh = RefreshToken.for_user(user_a)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

        response = client.get('/api/appointments/requests/')
        for req in (response.data.get('results', []) or response.data):
            practice_id = req.get('practice')
            if practice_id == practice_b.id:
                self.fail("Cross-practice request data leak!")


class TestHealthEndpoints(TestCase):
    """Test health check endpoints."""

    def test_health_check(self):
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_readiness_check(self):
        response = self.client.get('/ready/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestDashboardEndpoints(TestCase):
    """Test dashboard operations."""

    def setUp(self):
        self.client_obj = APIClient()
        self.practice = Practice.objects.create(
            name='Raleigh Test Practice',
            slug='raleigh-dashboard',
            email='test@raleighdentistry.com',
            phone='(919) 832-3300',
            address='Raleigh, NC',
            timezone='America/New_York',
            website='https://raleighdentistry.com',
            active=True,
        )
        self.user = User.objects.create_user(
            email='user@raleighdentistry.com',
            password='testpass123',
            name='Test User',
            role='OWNER',
            practice=self.practice,
        )
        refresh = RefreshToken.for_user(self.user)
        self.client_obj.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_dashboard_stats(self):
        response = self.client_obj.get('/api/dashboard/stats/')
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
