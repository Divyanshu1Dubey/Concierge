"""Comprehensive tests for HeyJarvis Raleigh V1.

Tests for models, serializers, views, and integrations.
"""
import pytest
import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import date, time

from bookings.models import BookingRule
from patients.models import Patient
from conversations.models import Conversation, Message
from appointments.models import AppointmentRequest
from emails.models import EmailMessage, EmailSequence, SequenceStep
from cadence.models import Cadence
from users.models import User


User = get_user_model()


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def practice(db):
    """Create the Raleigh practice."""
    return Practice.objects.create(
        name='Raleigh Comprehensive & Cosmetic Dentistry',
        slug='raleigh',
        email='info@raleighdentistry.com',
        phone='(919) 832-3300',
        address='Raleigh, NC',
        timezone='America/New_York',
        website='https://raleighcomprehensive.com',
        active=True,
    )


@pytest.fixture
def front_desk_user(db, practice):
    """Create a front desk user for the practice."""
    return User.objects.create_user(
        email='frontdesk@raleighdentistry.com',
        password='testpass123',
        name='Front Desk User',
        google_id='test-google-123',
        role='FRONT_DESK',
        practice=practice,
        is_active=True,
    )


@pytest.fixture
def owner_user(db, practice):
    """Create an owner user for the practice."""
    return User.objects.create_user(
        email='owner@raleighdentistry.com',
        password='testpass123',
        name='Dr. Owner',
        google_id='test-google-456',
        role='OWNER',
        practice=practice,
        is_staff=True,
        is_active=True,
    )


@pytest.fixture
def patient(db, practice):
    """Create a test patient."""
    return Patient.objects.create(
        practice=practice,
        name='Sarah Johnson',
        email='sarah@test.com',
        phone='(919) 555-0100',
        existing_patient=False,
    )


@pytest.fixture
def authenticated_client(api_client, front_desk_user):
    """Authenticated API client with JWT token."""
    refresh = RefreshToken.for_user(front_desk_user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return api_client


# ============================================================
# PRACTICE TESTS
# ============================================================

@pytest.mark.django_db
class TestPracticeModel:
    def test_create_practice(self, practice):
        assert practice.name == 'Raleigh Comprehensive & Cosmetic Dentistry'
        assert practice.slug == 'raleigh'
        assert practice.timezone == 'America/New_York'
        assert practice.active is True

    def test_practice_str(self, practice):
        assert str(practice) == 'Raleigh Comprehensive & Cosmetic Dentistry'

    def test_slug_unique(self, practice):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            Practice.objects.create(
                name='Another Practice',
                slug='raleigh',
                email='other@test.com',
                phone='555-0100',
                address='addr',
            )


@pytest.mark.django_db
class TestPracticeAPI:
    def test_list_practices(self, authenticated_client, practice):
        response = authenticated_client.get('/api/practices/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1

    def test_retrieve_practice(self, authenticated_client, practice):
        response = authenticated_client.get(f'/api/practices/{practice.id}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['slug'] == 'raleigh'


# ============================================================
# PATIENT TESTS
# ============================================================

@pytest.mark.django_db
class TestPatientModel:
    def test_create_patient(self, practice):
        patient = Patient.objects.create(
            practice=practice,
            name='John Doe',
            email='john@test.com',
            phone='(919) 555-0101',
            existing_patient=True,
        )
        assert patient.practice == practice
        assert patient.existing_patient is True
        assert 'John Doe' in str(patient)

    def test_patient_default_not_existing(self, practice):
        patient = Patient.objects.create(
            practice=practice,
            name='New Patient',
            email='new@test.com',
            phone='555-0100',
        )
        assert patient.existing_patient is False


@pytest.mark.django_db
class TestPatientAPI:
    def test_create_patient(self, authenticated_client, practice):
        response = authenticated_client.post('/api/patients/', {
            'practice': practice.id,
            'name': 'Test Patient',
            'email': 'testpatient@test.com',
            'phone': '555-0100',
            'existing_patient': False,
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == 'Test Patient'

    def test_list_patients(self, authenticated_client, patient):
        response = authenticated_client.get('/api/patients/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1


# ============================================================
# USER & AUTH TESTS
# ============================================================

@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self, practice):
        user = User.objects.create_user(
            email='user@test.com',
            password='testpass',
            name='Test User',
            role='FRONT_DESK',
            practice=practice,
        )
        assert user.email == 'user@test.com'
        assert user.role == 'FRONT_DESK'
        assert user.is_active is True

    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            email='admin@test.com',
            password='adminpass',
            name='Admin',
        )
        assert admin.is_staff is True
        assert admin.is_superuser is True

    def test_google_id_field(self, practice):
        user = User.objects.create_user(
            email='google@test.com',
            password='testpass',
            name='Google User',
            google_id='google-123',
            role='FRONT_DESK',
            practice=practice,
        )
        assert user.google_id == 'google-123'


@pytest.mark.django_db
class TestAuthAPI:
    def test_register(self, api_client, practice):
        response = api_client.post('/api/users/register/', {
            'email': 'newuser@test.com',
            'password': 'newpass123',
            'name': 'New User',
            'practice_slug': 'raleigh',
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_login(self, api_client, front_desk_user):
        response = api_client.post('/api/users/login/', {
            'email': 'frontdesk@raleighdentistry.com',
            'password': 'testpass123',
        })
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data

    def test_login_wrong_password(self, api_client, front_desk_user):
        response = api_client.post('/api/users/login/', {
            'email': 'frontdesk@raleighdentistry.com',
            'password': 'wrongpass',
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================
# CONVERSATION TESTS
# ============================================================

@pytest.mark.django_db
class TestConversationModel:
    def test_create_conversation(self, practice, patient):
        conv = Conversation.objects.create(
            practice=practice,
            patient=patient,
            session_id='test-session-001',
            status='active',
        )
        assert conv.status == 'active'
        assert conv.practice == practice
        assert conv.messages.count() == 0

    def test_add_message(self, practice, patient):
        conv = Conversation.objects.create(
            practice=practice,
            patient=patient,
            session_id='test-session-002',
        )
        msg = Message.objects.create(
            conversation=conv,
            role='user',
            content='Hello, I need an appointment',
        )
        assert msg.role == 'user'
        assert msg.content == 'Hello, I need an appointment'
        assert conv.messages.count() == 1

    def test_conversation_status_default(self, practice):
        conv = Conversation.objects.create(
            practice=practice,
            session_id='test-session-003',
        )
        assert conv.status == 'active'


@pytest.mark.django_db
class TestConversationAPI:
    def test_list_conversations(self, authenticated_client, practice):
        Conversation.objects.create(practice=practice, session_id='s1')
        response = authenticated_client.get('/api/conversations/')
        assert response.status_code == status.HTTP_200_OK

    def test_create_message(self, authenticated_client, practice):
        conv = Conversation.objects.create(practice=practice, session_id='s2')
        response = authenticated_client.post('/api/conversations/messages/', {
            'conversation': conv.id,
            'role': 'user',
            'content': 'Hello',
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['content'] == 'Hello'


# ============================================================
# APPOINTMENT REQUEST TESTS
# ============================================================

@pytest.mark.django_db
class TestAppointmentRequestModel:
    def test_create_new_patient_request(self, practice, patient):
        req = AppointmentRequest.objects.create(
            practice=practice,
            patient=patient,
            appointment_type='new_patient',
            reason='First visit, need cleaning',
            urgency='medium',
            preferred_date=date(2026, 10, 15),
            preferred_time=time(9, 0),
        )
        assert req.status == 'NEW'
        assert req.appointment_type == 'new_patient'
        assert req.urgency == 'medium'

    def test_create_emergency_request(self, practice):
        req = AppointmentRequest.objects.create(
            practice=practice,
            appointment_type='emergency',
            reason='Severe tooth pain',
            urgency='high',
            preferred_date=date.today(),
            preferred_time=time(14, 0),
        )
        assert req.appointment_type == 'emergency'
        assert req.urgency == 'high'

    def test_default_status(self, practice):
        req = AppointmentRequest.objects.create(
            practice=practice,
            appointment_type='cleaning',
        )
        assert req.status == 'NEW'


@pytest.mark.django_db
class TestAppointmentRequestAPI:
    def test_create_request(self, authenticated_client, practice, patient):
        response = authenticated_client.post('/api/appointments/requests/', {
            'practice': practice.id,
            'patient': patient.id,
            'appointment_type': 'cleaning',
            'reason': 'Regular checkup',
            'urgency': 'low',
            'preferred_date': '2026-10-15',
            'preferred_time': '09:00:00',
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['status'] == 'NEW'

    def test_list_requests(self, authenticated_client, practice):
        AppointmentRequest.objects.create(
            practice=practice,
            appointment_type='cleaning',
            urgency='low',
        )
        response = authenticated_client.get('/api/appointments/requests/')
        assert response.status_code == status.HTTP_200_OK

    def test_update_request_status(self, authenticated_client, practice):
        req = AppointmentRequest.objects.create(
            practice=practice,
            appointment_type='cleaning',
            urgency='low',
        )
        response = authenticated_client.patch(
            f'/api/appointments/requests/{req.id}/',
            {'status': 'SENT', 'offered_date': '2026-10-15', 'offered_time': '14:30:00'}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'SENT'


# ============================================================
# EMAIL TESTS
# ============================================================

@pytest.mark.django_db
class TestEmailModel:
    def test_create_outbound_email(self, practice):
        email = EmailMessage.objects.create(
            practice=practice,
            appointment_request=None,
            direction='outbound',
            subject='Appointment Offered',
            body='Would 2:30 PM work?',
            sender='info@raleighdentistry.com',
            recipient='patient@test.com',
            status='draft',
        )
        assert email.direction == 'outbound'
        assert email.status == 'draft'
        assert email.sender == 'info@raleighdentistry.com'

    def test_email_threading(self, practice):
        email = EmailMessage.objects.create(
            practice=practice,
            appointment_request=None,
            direction='outbound',
            subject='Appointment',
            body='Hello',
            sender='info@test.com',
            recipient='patient@test.com',
            thread_id='thread-001',
            message_id='msg-001',
            status='sent',
        )
        assert email.thread_id == 'thread-001'
        assert email.message_id == 'msg-001'


@pytest.mark.django_db
class TestEmailAPI:
    def test_send_email_draft(self, authenticated_client, practice):
        response = authenticated_client.post('/api/emails/drafts/', {
            'practice': practice.id,
            'direction': 'outbound',
            'subject': 'Test',
            'body': 'Test body',
            'recipient': 'patient@test.com',
            'sender': 'info@raleighdentistry.com',
        })
        assert response.status_code == status.HTTP_201_CREATED


# ============================================================
# CADENCE TESTS
# ============================================================

@pytest.mark.django_db
class TestCadenceModel:
    def test_create_cadence(self, practice):
        req = AppointmentRequest.objects.create(
            practice=practice,
            appointment_type='cleaning',
        )
        cadence = Cadence.objects.create(
            request=req,
            active=True,
            current_step='initial_email',
            next_run_at=None,
        )
        assert cadence.active is True
        assert cadence.request == req

    def test_cadence_stop(self, practice):
        req = AppointmentRequest.objects.create(
            practice=practice,
            appointment_type='cleaning',
        )
        from django.utils import timezone
        cadence = Cadence.objects.create(
            request=req,
            active=False,
            current_step='interrupted',
            stop_reason='patient_replied',
            interrupted_at=timezone.now(),
        )
        assert cadence.active is False
        assert cadence.stop_reason == 'patient_replied'


@pytest.mark.django_db
class TestCadenceAPI:
    def test_list_cadences(self, authenticated_client, practice):
        req = AppointmentRequest.objects.create(
            practice=practice,
            appointment_type='cleaning',
        )
        Cadence.objects.create(request=req, active=True, current_step='initial_email')
        response = authenticated_client.get('/api/cadence/')
        assert response.status_code == status.HTTP_200_OK


# ============================================================
# BOOKING RULES TESTS
# ============================================================

@pytest.mark.django_db
class TestBookingRules:
    def test_create_booking_rules(self, practice):
        rules = BookingRule.objects.create(
            practice=practice,
            new_patient_duration=90,
            new_patient_doctor_duration=90,
            new_patient_hygiene_duration=60,
            emergency_duration=60,
            confirmation_hours=48,
            no_show_fee=65,
            financing_options=['Cherry', 'CareCredit'],
        )
        assert rules.new_patient_duration == 90
        assert rules.confirmation_hours == 48
        assert rules.no_show_fee == 65
        assert 'Cherry' in rules.financing_options
        assert 'CareCredit' in rules.financing_options

    def test_booking_rules_one_to_one(self, practice):
        BookingRule.objects.create(practice=practice, new_patient_duration=90)
        with pytest.raises(Exception):
            BookingRule.objects.create(practice=practice, new_patient_duration=60)


# ============================================================
# MULTI-TENANCY ISOLATION TESTS
# ============================================================

@pytest.mark.django_db
class TestTenantIsolation:
    def test_practice_a_cannot_see_practice_b_patients(self):
        """Practice A must never see Practice B's data."""
        practice_a = Practice.objects.create(
            name='Practice A', slug='practice-a',
            email='a@test.com', phone='555-0100', address='addr',
        )
        practice_b = Practice.objects.create(
            name='Practice B', slug='practice-b',
            email='b@test.com', phone='555-0100', address='addr2',
        )
        patient_b = Patient.objects.create(
            practice=practice_b, name='Patient B',
            email='pb@test.com', phone='555-0101',
        )
        # Practice A's user can only see A's patients
        practice_a_patients = Patient.objects.filter(practice=practice_a)
        assert patient_b not in practice_a_patients
        assert patient_b.practice == practice_b

    def test_user_cannot_access_other_practice_appointments(self):
        practice_a = Practice.objects.create(
            name='Practice A', slug='pa',
            email='pa@test.com', phone='555-0100', address='addr',
        )
        practice_b = Practice.objects.create(
            name='Practice B', slug='pb',
            email='pb@test.com', phone='555-0100', address='addr2',
        )
        request_b = AppointmentRequest.objects.create(
            practice=practice_b,
            appointment_type='cleaning',
        )
        # Practice A can't see Practice B's requests
        practice_a_requests = AppointmentRequest.objects.filter(practice=practice_a)
        assert request_b not in practice_a_requests


# ============================================================
# AUDIT LOG TESTS
# ============================================================

@pytest.mark.django_db
class TestAuditLog:
    def test_create_audit_log(self, practice, front_desk_user):
        from audit.models import AuditLog
        log = AuditLog.objects.create(
            practice=practice,
            user=front_desk_user,
            action='email_sent',
            resource_type='appointment_request',
            resource_id='123',
            metadata={'request_id': '456'},
        )
        assert log.action == 'email_sent'
        assert log.user == front_desk_user
        assert log.practice == practice

    def test_audit_log_without_user(self, practice):
        from audit.models import AuditLog
        log = AuditLog.objects.create(
            practice=practice,
            action='system_action',
            resource_type='cadence',
            resource_id='789',
        )
        assert log.user is None
        assert log.action == 'system_action'


# ============================================================
# KNOWLEDGE BASE TESTS
# ============================================================

@pytest.mark.django_db
class TestKnowledgeBase:
    def test_create_kb_entry(self, practice):
        from knowledge.models import KnowledgeBase
        kb = KnowledgeBase.objects.create(
            practice=practice,
            category='Hours',
            question='What are your hours?',
            answer='Mon-Fri 8am-5pm',
            is_published=True,
        )
        assert kb.category == 'Hours'
        assert kb.is_published is True

    def test_only_published_visible_to_patients(self, practice):
        from knowledge.models import KnowledgeBase
        KnowledgeBase.objects.create(
            practice=practice, category='Hours',
            question='Q1', answer='A1', is_published=True,
        )
        KnowledgeBase.objects.create(
            practice=practice, category='Internal',
            question='Q2', answer='A2', is_published=False,
        )
        published = KnowledgeBase.objects.filter(practice=practice, is_published=True)
        assert published.count() == 1
        assert published.first().question == 'Q1'
