"""HeyJarvis Concierge State Machine Engine.

Handles:
STARTED -> IDENTIFYING_INTENT -> COLLECTING_INFORMATION -> QUALIFYING -> CONFIRMING -> SUBMITTING -> SUBMITTED
and HANDOFF, CLOSED.
Supports natural language extraction, deterministic fallback, business-hours awareness, and emergency triage.
"""
import re
import logging
from django.utils import timezone
from apps.appointments.models import Appointment, Service
from apps.conversations.models import Conversation

logger = logging.getLogger(__name__)

# Intent definitions
INTENT_NEW_PATIENT = 'new_patient'
INTENT_EMERGENCY = 'emergency'
INTENT_CLEANING = 'cleaning'
INTENT_RESCHEDULE = 'reschedule'
INTENT_CANCEL = 'cancel'
INTENT_QUESTION = 'question'
INTENT_HANDOFF = 'handoff'

INTENT_DISPLAY_NAMES = {
    INTENT_NEW_PATIENT: 'New Patient Exam',
    INTENT_EMERGENCY: 'Emergency Dental Care',
    INTENT_CLEANING: 'Routine Cleaning & Checkup',
    INTENT_RESCHEDULE: 'Reschedule Appointment',
    INTENT_CANCEL: 'Cancel Appointment',
    INTENT_QUESTION: 'General Inquiry',
    INTENT_HANDOFF: 'Staff Assistance',
}

QUICK_REPLIES_MAP = {
    'INITIAL': [
        {'label': 'New Patient', 'value': 'I am a new patient looking to book'},
        {'label': 'Routine Cleaning', 'value': 'I need a cleaning and checkup'},
        {'label': 'Dental Emergency', 'value': 'I have a dental emergency'},
        {'label': 'Reschedule / Cancel', 'value': 'I need to reschedule or cancel'},
        {'label': 'Ask a Question', 'value': 'I have a general question'},
        {'label': 'Talk to Staff', 'value': 'I would like to speak with the front desk'},
    ],
    'CONFIRMATION': [
        {'label': 'Yes, looks great!', 'value': 'Yes, please submit my request'},
        {'label': 'Change details', 'value': 'I need to change something'},
    ],
    'TIMES': [
        {'label': 'Morning (8am - 12pm)', 'value': 'Morning works best for me'},
        {'label': 'Afternoon (12pm - 5pm)', 'value': 'Afternoon works best for me'},
        {'label': 'First available', 'value': 'First available opening'},
    ]
}

def extract_entities(text: str) -> dict:
    """Extract patient name, phone, email, date, time, and intent from natural language."""
    extracted = {}
    lower = text.lower()

    # 1. Email extraction
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    if email_match:
        extracted['email'] = email_match.group(0)

    # 2. Phone extraction
    phone_match = re.search(r'(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})', text)
    if phone_match:
        extracted['phone'] = phone_match.group(0)

    # 3. Name extraction
    name_patterns = [
        r"(?:my name is|i'm|im|i am|this is|call me|it's|its)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})",
        r"(?:name:\s*)([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})",
    ]
    for pattern in name_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in {'ready', 'here', 'interested', 'looking', 'asking', 'wondering', 'good', 'fine', 'a patient', 'new patient'}:
                extracted['name'] = candidate.title()
                break

    # 4. Intent detection
    if any(w in lower for w in ['emergency', 'severe pain', 'bleeding', 'swelling', 'broken tooth', 'knocked out', 'agony', 'throbbing']):
        extracted['intent'] = INTENT_EMERGENCY
        extracted['urgency'] = 'URGENT'
    elif any(w in lower for w in ['cleaning', 'clean', 'hygiene', 'checkup', 'check up', 'routine']):
        extracted['intent'] = INTENT_CLEANING
    elif any(w in lower for w in ['reschedule', 'move appointment', 'change time', 'change date']):
        extracted['intent'] = INTENT_RESCHEDULE
    elif any(w in lower for w in ['cancel', 'cancellation', 'call off']):
        extracted['intent'] = INTENT_CANCEL
    elif any(w in lower for w in ['talk to someone', 'speak to staff', 'human', 'representative', 'operator', 'front desk']):
        extracted['intent'] = INTENT_HANDOFF
    elif any(w in lower for w in ['cost', 'price', 'insurance', 'hours', 'where', 'how much', 'do you accept']):
        extracted['intent'] = INTENT_QUESTION
    elif any(w in lower for w in [
        'book', 'booking', 'appointment', 'appoint', 'appiintment', 'schedule', 'see the dentist',
        'see doctor', 'consultation', 'new patient', 'first time', 'new to', 'switch to',
        'whitening', 'invisalign', 'implant', 'crown', 'filling', 'veneer', 'exam', 'visit'
    ]):
        extracted['intent'] = INTENT_NEW_PATIENT

    # 5. Preferred Date extraction
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'tomorrow', 'today', 'next week']
    for d in days:
        if d in lower:
            extracted['preferred_date'] = d.capitalize()
            break

    # 6. Preferred Time extraction
    if 'morning' in lower:
        extracted['preferred_time'] = 'Morning'
    elif 'afternoon' in lower:
        extracted['preferred_time'] = 'Afternoon'
    elif 'evening' in lower:
        extracted['preferred_time'] = 'Evening'
    else:
        time_match = re.search(r'(?:after\s+|around\s+|at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm))', lower)
        if time_match:
            extracted['preferred_time'] = time_match.group(0).strip()

    return extracted


def is_office_open(practice) -> tuple[bool, str]:
    """Check if the practice is currently open according to business hours."""
    try:
        rules = getattr(practice, 'booking_rules', None)
        if not rules or not rules.business_hours:
            return True, ""
        
        hours = rules.business_hours
        now = timezone.localtime(timezone.now())
        weekday = now.strftime('%A').lower() # 'monday'
        
        day_config = hours.get(weekday)
        if not day_config or day_config.get('closed', False):
            return False, rules.after_hours_message or "Our office is currently closed."
            
        open_time_str = day_config.get('open', '08:00')
        close_time_str = day_config.get('close', '17:00')
        current_time_str = now.strftime('%H:%M')
        
        if not (open_time_str <= current_time_str <= close_time_str):
            return False, rules.after_hours_message or "Our office is currently closed."
            
        return True, ""
    except Exception as e:
        logger.warning(f"Error checking business hours: {e}")
        return True, ""


class ConciergeStateMachine:
    """State Machine coordinating conversation flow, entity extraction, and lead submission."""

    def __init__(self, conversation, practice, ai_engine=None):
        self.conversation = conversation
        self.practice = practice
        self.ai_engine = ai_engine

    def process_message(self, user_text: str) -> dict:
        """Process incoming visitor message and transition state."""
        extracted = extract_entities(user_text)

        current_state = self.conversation.state or Conversation.STATE_STARTED

        # Contextual name extraction:
        # If the bot was awaiting the patient's name in COLLECTING_INFORMATION,
        # extract standalone names (e.g., 'div', 'John Doe', 'Sarah') directly from the response
        if current_state == Conversation.STATE_COLLECTING_INFORMATION and not self.conversation.patient_name:
            if 'name' not in extracted:
                cleaned_text = user_text
                if 'email' in extracted:
                    cleaned_text = cleaned_text.replace(extracted['email'], '')
                if 'phone' in extracted:
                    cleaned_text = cleaned_text.replace(extracted['phone'], '')
                cleaned_text = re.sub(r"[^\w\s'-]", ' ', cleaned_text).strip()
                
                non_name_tokens = {
                    'hi', 'hello', 'hey', 'yes', 'no', 'ok', 'okay', 'sure', 'thanks', 'thank',
                    'appointment', 'book', 'booking', 'cleaning', 'cancel', 'reschedule',
                    'emergency', 'help', 'morning', 'afternoon', 'monday', 'tuesday', 'wednesday',
                    'thursday', 'friday', 'saturday', 'sunday', 'tomorrow', 'today', 'my', 'name',
                    'is', 'im', 'i', 'am', 'this', 'need', 'want', 'please', 'exam', 'slot'
                }
                tokens = [t for t in cleaned_text.split() if t.lower() not in non_name_tokens]
                if 1 <= len(tokens) <= 4:
                    if all(re.match(r"^[A-Za-z][A-Za-z'-]*$", t) for t in tokens):
                        extracted['name'] = ' '.join(t.capitalize() for t in tokens)

        # Update entity fields on conversation if extracted and not previously set
        if 'name' in extracted and not self.conversation.patient_name:
            self.conversation.patient_name = extracted['name']
        if 'phone' in extracted and not self.conversation.patient_phone:
            self.conversation.patient_phone = extracted['phone']
        if 'email' in extracted and not self.conversation.patient_email:
            self.conversation.patient_email = extracted['email']
        if 'preferred_date' in extracted and not self.conversation.preferred_date:
            self.conversation.preferred_date = extracted['preferred_date']
        if 'preferred_time' in extracted and not self.conversation.preferred_time:
            self.conversation.preferred_time = extracted['preferred_time']
        if 'intent' in extracted and (not self.conversation.intent or self.conversation.intent == 'general_chat'):
            self.conversation.intent = extracted['intent']
        if 'urgency' in extracted:
            self.conversation.urgency = extracted['urgency']

        practice_name = self.practice.name if self.practice else "our office"
        booking_rules = getattr(self.practice, 'booking_rules', None)
        is_open, after_hours_msg = is_office_open(self.practice)

        # Emergency override check: immediate triage
        if self.conversation.intent == INTENT_EMERGENCY:
            self.conversation.urgency = 'URGENT'
            emergency_msg = getattr(booking_rules, 'emergency_message', '') or (
                f"Dental emergency detected. Please call {self.practice.phone or 'our office'} immediately."
            )
            
            if not self.conversation.patient_phone:
                self.conversation.state = Conversation.STATE_COLLECTING_INFORMATION
                reply = (
                    f"⚠️ {emergency_msg}\n\n"
                    f"To connect you immediately with our on-call clinical team, what is your best callback phone number and your name?"
                )
                return self._finalize_step(reply, quick_replies=[])
            else:
                # We have emergency phone; submit lead immediately
                self.conversation.state = Conversation.STATE_SUBMITTED
                self._create_or_update_lead(status='pending', urgency='URGENT')
                reply = (
                    f"⚠️ Thank you {self.conversation.patient_name or 'valued patient'}. We have logged your urgent emergency request and notified our front desk.\n\n"
                    f"If your pain or swelling is severe, please call {self.practice.phone} right now or visit your nearest emergency room."
                )
                return self._finalize_step(reply, complete=True, quick_replies=[])

        # State 1: STARTED -> IDENTIFYING_INTENT
        if current_state in (Conversation.STATE_STARTED, Conversation.STATE_IDENTIFYING_INTENT):
            if not self.conversation.intent or self.conversation.intent == 'general_chat':
                self.conversation.state = Conversation.STATE_IDENTIFYING_INTENT
                reply = (
                    f"Hello and welcome to {practice_name}! I am your AI concierge. "
                    f"How can I help you today?"
                )
                return self._finalize_step(reply, quick_replies=QUICK_REPLIES_MAP['INITIAL'])
            else:
                self.conversation.state = Conversation.STATE_COLLECTING_INFORMATION

        # State 2: COLLECTING_INFORMATION
        if self.conversation.state == Conversation.STATE_COLLECTING_INFORMATION:
            intent_label = INTENT_DISPLAY_NAMES.get(self.conversation.intent, self.conversation.intent)

            if not self.conversation.patient_name:
                reply = f"I would be glad to help coordinate your {intent_label}. What is your full name?"
                return self._finalize_step(reply)

            if not self.conversation.patient_phone and not self.conversation.patient_email:
                reply = f"Nice to meet you, {self.conversation.patient_name}! What is the best phone number or email address for our front desk to reach you?"
                return self._finalize_step(reply)

            if not self.conversation.preferred_date:
                reply = f"Thanks, {self.conversation.patient_name}! What day works best for your visit (e.g., Thursday, next week, or specific day)?"
                return self._finalize_step(reply)

            if not self.conversation.preferred_time:
                reply = f"Great. Do you prefer morning, afternoon, or a specific time on {self.conversation.preferred_date}?"
                return self._finalize_step(reply, quick_replies=QUICK_REPLIES_MAP['TIMES'])

            # All required information collected -> move to CONFIRMING
            self.conversation.state = Conversation.STATE_CONFIRMING

        # State 3: CONFIRMING
        if self.conversation.state == Conversation.STATE_CONFIRMING:
            lower = user_text.lower()
            if any(w in lower for w in ['yes', 'correct', 'submit', 'good', 'sure', 'confirm', 'please', 'looks great']):
                self.conversation.state = Conversation.STATE_SUBMITTED
                appointment = self._create_or_update_lead(status='pending')
                
                after_hours_note = f"\n\nNote: {after_hours_msg}" if not is_open else ""
                reply = (
                    f"✨ Fantastic! Your appointment request has been submitted to {practice_name}.\n\n"
                    f"Request Summary:\n"
                    f"• Patient: {self.conversation.patient_name}\n"
                    f"• Service: {INTENT_DISPLAY_NAMES.get(self.conversation.intent, 'Appointment')}\n"
                    f"• Requested Timing: {self.conversation.preferred_date} ({self.conversation.preferred_time})\n\n"
                    f"Our front desk will review our schedule and contact you directly at "
                    f"{self.conversation.patient_phone or self.conversation.patient_email} to confirm your visit.{after_hours_note}"
                )
                return self._finalize_step(reply, complete=True, quick_replies=[])
            elif any(w in lower for w in ['no', 'change', 'different', 'wrong']):
                self.conversation.state = Conversation.STATE_COLLECTING_INFORMATION
                self.conversation.preferred_date = ''
                self.conversation.preferred_time = ''
                reply = "No problem at all! What day and time would you prefer instead?"
                return self._finalize_step(reply)
            else:
                intent_label = INTENT_DISPLAY_NAMES.get(self.conversation.intent, 'visit')
                reply = (
                    f"To make sure our front desk coordinates accurately, please confirm:\n\n"
                    f"• Name: {self.conversation.patient_name}\n"
                    f"• Service: {intent_label}\n"
                    f"• Preferred: {self.conversation.preferred_date} ({self.conversation.preferred_time})\n"
                    f"• Contact: {self.conversation.patient_phone or self.conversation.patient_email}\n\n"
                    f"Does this look good to submit to our front desk?"
                )
                return self._finalize_step(reply, quick_replies=QUICK_REPLIES_MAP['CONFIRMATION'])

        # State: SUBMITTED
        if self.conversation.state == Conversation.STATE_SUBMITTED:
            reply = (
                f"Your request is already received by the {practice_name} front desk! "
                f"If you need to reach us urgently, feel free to call our office at {self.practice.phone}."
            )
            return self._finalize_step(reply, complete=True, quick_replies=[])

        # State: HANDOFF
        if self.conversation.state == Conversation.STATE_HANDOFF:
            self.conversation.status = Conversation.STATUS_HANDOFF
            self._create_or_update_lead(status='pending', urgency='HIGH')
            reply = (
                f"I have alerted our front desk team at {practice_name} that you requested staff assistance. "
                f"A team member will review your message and reach out to you shortly."
            )
            return self._finalize_step(reply, complete=True, quick_replies=[])

        # Fallback AI response for general chit-chat if state machine did not handle
        if self.ai_engine:
            res = self.ai_engine.chat(user_text)
            return self._finalize_step(res.get('content', 'How else may I help you today?'), quick_replies=[])

        return self._finalize_step("How else may I help you with your dental care today?", quick_replies=[])

    def _finalize_step(self, reply_text: str, complete: bool = False, quick_replies: list = None) -> dict:
        """Save conversation state and return response payload."""
        self.conversation.last_activity_at = timezone.now()
        self.conversation.save()

        replies = quick_replies or []
        options = [r['label'] if isinstance(r, dict) else str(r) for r in replies]

        return {
            'message': reply_text,
            'response': reply_text,
            'welcome_message': reply_text,
            'state': self.conversation.state,
            'intent': self.conversation.intent,
            'conversation_id': str(self.conversation.id),
            'conversation_complete': complete,
            'quick_replies': replies,
            'quick_options': options,
            'requires_human': self.conversation.intent in (INTENT_EMERGENCY, INTENT_HANDOFF),
        }

    def _create_or_update_lead(self, status='pending', urgency='NORMAL') -> Appointment:
        """Create or update corresponding Appointment / Lead record."""
        srv = Service.objects.filter(practice=self.practice).first() if self.practice else None

        appt, _ = Appointment.objects.get_or_create(
            conversation=self.conversation,
            defaults={
                'practice': self.practice,
                'service': srv,
                'patient_name': self.conversation.patient_name,
                'patient_email': self.conversation.patient_email,
                'patient_phone': self.conversation.patient_phone,
                'intent': self.conversation.intent or 'appointment',
                'service_name': INTENT_DISPLAY_NAMES.get(self.conversation.intent, 'Appointment Request'),
                'preferred_date': self.conversation.preferred_date,
                'preferred_time': self.conversation.preferred_time,
                'urgency': urgency or self.conversation.urgency,
                'priority': urgency or self.conversation.urgency,
                'status': status,
                'ai_summary': f"Request for {self.conversation.intent} on {self.conversation.preferred_date} ({self.conversation.preferred_time}).",
                'source_website': self.conversation.source_url or (self.practice.website if self.practice else ''),
            }
        )
        return appt
