"""Widget conversation journeys: names, mid-chat questions, confirmations, handoff, cancel, emergencies."""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.appointments.models import Appointment
from apps.conversations.models import Conversation
from apps.conversations.state_machine import contextual_name, extract_entities
from apps.practices.models import BookingRules, Practice


@override_settings(AI_PROVIDER='none')
class WidgetJourneyTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='Alpha Dental', slug='alpha', email='a@x.test', phone='(919) 555-0100', address='1 Main St')
        BookingRules.objects.get_or_create(practice=self.p)
        self.n = 0

    def chat(self, *turns):
        self.n += 1
        sid = f'journey-{self.n}'
        c = APIClient()
        c.post('/api/v1/widget/conversation/', {'client_key': self.p.api_key, 'session_id': sid}, format='json')
        out = []
        for t in turns:
            r = c.post('/api/v1/widget/message/', {'client_key': self.p.api_key, 'session_id': sid, 'message': t}, format='json')
            self.assertEqual(r.status_code, 200, r.content)
            out.append(r.json())
        return out, Conversation.objects.get(session_id=sid)

    def labels(self, reply):
        return [q['label'] for q in reply.get('quick_replies', [])]

    def test_new_patient_chip_does_not_become_a_name(self):
        out, conv = self.chat('I am a new patient looking to book', 'Sarah Lee', 'sarah@example.test', 'Tuesday morning', 'Yes, please submit my request')
        self.assertIn('What is your full name?', out[0]['message'])
        self.assertEqual(conv.patient_name, 'Sarah Lee')
        self.assertTrue(out[-1]['conversation_complete'])
        self.assertIn('not booked until they confirm', out[-1]['message'])
        appt = Appointment.objects.get(practice=self.p)
        self.assertEqual((appt.patient_name, appt.preferred_date, appt.preferred_time), ('Sarah Lee', 'Tuesday', 'Morning'))

    def test_question_mid_intake_is_answered_and_flow_resumes(self):
        out, conv = self.chat('I need a cleaning and checkup', 'What are your office hours?', 'Sarah Lee')
        self.assertIn('Now, to finish your request: What is your full name?', out[1]['message'])
        self.assertEqual(conv.patient_name, 'Sarah Lee')
        self.assertIn('phone number or email', out[2]['message'])

    def test_please_change_time_does_not_submit(self):
        out, conv = self.chat('I need a cleaning and checkup', 'Ana Ruiz', 'ana@example.test', 'Monday', 'Can you please change the time?')
        self.assertFalse(out[-1]['conversation_complete'])
        self.assertEqual(conv.state, Conversation.STATE_COLLECTING_INFORMATION)
        self.assertFalse(Appointment.objects.filter(practice=self.p, status='pending', patient_name='Ana Ruiz', preferred_date='Monday').exists()
                         and conv.state == Conversation.STATE_SUBMITTED)
        self.assertIn('Morning (8am - 12pm)', self.labels(out[-1]))

    def test_afternoon_is_not_read_as_no(self):
        out, conv = self.chat("I'm looking to book a cleaning", "it's John Park", '919-555-0142', 'Afternoon works best for me', 'yes')
        self.assertEqual(conv.patient_name, 'John Park')
        self.assertIn('Please confirm your request', out[3]['message'])
        self.assertTrue(out[-1]['conversation_complete'])

    def test_call_me_at_number_is_not_a_name(self):
        out, conv = self.chat("Hi, my name is Priya Shah, I'd like a cleaning tomorrow morning, call me at 919-555-0101")
        self.assertEqual(conv.patient_name, 'Priya Shah')
        self.assertEqual(conv.patient_phone, '919-555-0101')
        self.assertEqual(conv.state, Conversation.STATE_CONFIRMING)

    def test_general_question_chip_invites_the_question(self):
        out, conv = self.chat('I have a general question', 'Do you have parking')
        self.assertIn('What would you like to know?', out[0]['message'])
        self.assertNotIn('Hello and welcome', out[1]['message'])

    def test_talk_to_staff_reaches_handoff_without_asking_for_a_time(self):
        out, conv = self.chat('I would like to speak with the front desk', 'Mia Chen', 'mia@example.test')
        self.assertTrue(out[-1]['conversation_complete'])
        self.assertEqual(conv.state, Conversation.STATE_HANDOFF)
        self.assertFalse(any('time of day' in o['message'] for o in out))
        self.assertTrue(Appointment.objects.filter(practice=self.p, patient_name='Mia Chen').exists())

    def test_cancel_switch_and_no_time_question(self):
        out, conv = self.chat('I need to reschedule or cancel', 'I want to cancel', 'Tom Hale', 'tom@example.test', 'yes')
        self.assertEqual(conv.intent, 'cancel')
        self.assertEqual(conv.patient_name, 'Tom Hale')
        self.assertNotIn('🕒 Change Time / Day', self.labels(out[3]))
        self.assertIn('cancellation request', out[-1]['message'])

    def test_tooth_pain_gets_urgent_triage(self):
        out, conv = self.chat('My tooth hurts really bad', '919 555 0177 Lily')
        self.assertEqual(conv.intent, 'emergency')
        self.assertEqual(conv.patient_name, 'Lily')
        self.assertTrue(out[-1]['conversation_complete'])

    def test_unclear_first_message_gets_helpful_prompt(self):
        out, conv = self.chat('hi', 'I need help with my teeth')
        self.assertIn('Hello and welcome', out[0]['message'])
        self.assertIn('request a visit, or is something hurting', out[1]['message'])

    def test_confirm_button_does_not_say_book(self):
        out, _ = self.chat('I need a cleaning and checkup', 'Ana Ruiz', 'ana@example.test', 'Monday')
        self.assertIn('✅ Submit request', self.labels(out[-1]))


class NameExtractionTests(TestCase):
    def test_non_names_are_rejected(self):
        for text in ['I am a new patient looking to book', "I'm looking to book a cleaning", "I'm having pain",
                     'I am interested in whitening', 'call me at 919-555-0101', 'I am not sure']:
            self.assertNotIn('name', extract_entities(text), text)

    def test_real_names_are_found(self):
        self.assertEqual(extract_entities('my name is priya shah')['name'], 'Priya Shah')
        self.assertEqual(extract_entities("I'm John and I need a cleaning")['name'], 'John')
        self.assertEqual(extract_entities('actually my name is Sam Ortiz')['name'], 'Sam Ortiz')
        self.assertEqual(contextual_name("it's John Park", {}), 'John Park')
        self.assertEqual(contextual_name('I want to cancel', {}), '')