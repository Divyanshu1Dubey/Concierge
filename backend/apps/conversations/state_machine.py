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
        {'label': '✅ Confirm & Book', 'value': 'Yes, please submit my request'},
        {'label': '🕒 Change Time / Day', 'value': 'Change my visit time'},
        {'label': '👤 Change Name', 'value': 'Change my name'},
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

    # 3. Name change intent & name extraction
    name_change_patterns = [
        r"(?:change\s+(?:my\s+)?name\s+to|update\s+(?:my\s+)?name\s+to|actually\s+my\s+name\s+is|actually\s+i'm|actually\s+im)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})",
        r"(?:call\s+me|use\s+the\s+name)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})",
    ]
    for pattern in name_change_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in {'ready', 'here', 'interested', 'looking', 'asking', 'good', 'fine'}:
                extracted['name'] = candidate.title()
                extracted['is_name_change'] = True
                break

    if 'name' not in extracted:
        name_patterns = [
            r"(?:my name is|i'm|im|i am|this is)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})",
            r"(?:name:\s*)([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})",
        ]
        for pattern in name_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                if candidate.lower() not in {'ready', 'here', 'interested', 'looking', 'asking', 'wondering', 'good', 'fine', 'a patient', 'new patient'}:
                    extracted['name'] = candidate.title()
                    break

    if any(phrase in lower for phrase in ['change name', 'change my name', 'wrong name', 'update name', 'different name']):
        extracted['request_change_name'] = True

    # 4. Intent detection
    if any(w in lower for w in ['emergency', 'severe pain', 'bleeding', 'swelling', 'broken tooth', 'knocked out', 'agony', 'throbbing']):
        extracted['intent'] = INTENT_EMERGENCY
        extracted['urgency'] = 'URGENT'
    elif any(w in lower for w in ['cleaning', 'clean', 'hygiene', 'checkup', 'check up', 'routine']):
        extracted['intent'] = INTENT_CLEANING
    elif any(w in lower for w in ['reschedule', 'move appointment', 'change time', 'change date', 'change my visit time']):
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
    if any(w in lower for w in ['first available', 'asap', 'anytime', 'earliest', 'any slot', 'first opening']):
        extracted['preferred_time'] = 'First Available'
    elif 'morning' in lower:
        extracted['preferred_time'] = 'Morning'
    elif 'afternoon' in lower:
        extracted['preferred_time'] = 'Afternoon'
    elif 'evening' in lower:
        extracted['preferred_time'] = 'Evening'
    else:
        time_match = re.search(r'(?:after\s+|around\s+|at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm))', lower)
        if time_match:
            extracted['preferred_time'] = time_match.group(0).strip().upper()

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

    QUESTION_STARTERS = (
        'what', 'when', 'where', 'how', 'do you', 'does', 'is there', 'are you', 'are there',
        'can i', 'can you', 'which', 'who', 'should i', 'will', 'is it', 'is your',
    )

    def _is_info_question(self, user_text: str, extracted: dict, current_state: str) -> bool:
        """A question asked before any request details were collected (not an emergency or booking)."""
        if current_state not in (Conversation.STATE_STARTED, Conversation.STATE_IDENTIFYING_INTENT):
            return False
        if self.conversation.intent and self.conversation.intent not in ('general_chat', INTENT_QUESTION):
            return False
        if extracted.get('intent') not in (None, INTENT_QUESTION):
            return False
        if any(k in extracted for k in ('name', 'phone', 'email')):
            return False
        text = user_text.strip().lower()
        return text.endswith('?') or text.startswith(self.QUESTION_STARTERS)

    def _hours_text(self) -> str:
        rules = getattr(self.practice, 'booking_rules', None)
        hours = (rules.business_hours if rules else None) or {}
        parts = []
        for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'):
            cfg = hours.get(day)
            if isinstance(cfg, dict):
                parts.append(f"{day.title()}: " + ('Closed' if cfg.get('closed') else f"{cfg.get('open')}-{cfg.get('close')}"))
        return '; '.join(parts)

    def _answer_question(self, user_text: str) -> dict:
        """Answer an informational question without starting a request (AI if configured, else facts only)."""
        self.conversation.state = Conversation.STATE_IDENTIFYING_INTENT
        if self.conversation.intent == INTENT_QUESTION:
            self.conversation.intent = ''
        phone = self.practice.phone if self.practice else ''
        answer = None
        if self.ai_engine and getattr(self.ai_engine, 'available', False):
            res = self.ai_engine.chat(user_text, practice=self.practice)
            answer = res.get('content')
        if not answer:
            lower = user_text.lower()
            hours = self._hours_text()
            if hours and any(w in lower for w in ('hour', 'open', 'close', 'closed')):
                answer = f"Our office hours are: {hours}."
            else:
                answer = (
                    "That's a great question for our front desk team"
                    + (f" - you can reach them at {phone}" if phone else '')
                    + ". I can also take a request so they can follow up with you."
                )
        return self._finalize_step(
            answer + "\n\nIs there anything else I can help with, or would you like to request an appointment?",
            quick_replies=QUICK_REPLIES_MAP['INITIAL'],
        )

    def process_message(self, user_text: str) -> dict:
        """Process incoming visitor message and transition state."""
        extracted = extract_entities(user_text)
        lower = user_text.lower()
        current_state = self.conversation.state or Conversation.STATE_STARTED
        practice_name = self.practice.name if self.practice else "our office"
        booking_rules = getattr(self.practice, 'booking_rules', None)

        # Informational questions ("What are your hours?", "Is there parking?") are answered
        # directly instead of starting the appointment-request flow.
        if self._is_info_question(user_text, extracted, current_state):
            return self._answer_question(user_text)

        # "Do you have anything free tomorrow?" - be explicit that availability is not checked live.
        self.reply_prefix = ''
        if current_state in (Conversation.STATE_STARTED, Conversation.STATE_IDENTIFYING_INTENT) and (
            user_text.strip().endswith('?') and any(w in lower for w in ('available', 'availability', 'free', 'opening', 'slot', 'space'))
        ):
            self.reply_prefix = (
                "I can't see the live schedule, but I can pass your preferred time to our front desk "
                "and they will confirm what's available. "
            )
        is_open, after_hours_msg = is_office_open(self.practice)

        meta = self.conversation.metadata or {}

        # ── Check if user was previously prompted to enter a new name ──
        if meta.get('awaiting_name_change'):
            new_name = extracted.get('name')
            if not new_name:
                # Take raw cleaned input as name
                cleaned = re.sub(r"[^\w\s'-]", '', user_text).strip()
                if cleaned and len(cleaned.split()) <= 4:
                    new_name = cleaned.title()

            if new_name:
                self.conversation.patient_name = new_name
                meta.pop('awaiting_name_change', None)
                self.conversation.metadata = meta
                self.conversation.save(update_fields=['patient_name', 'metadata'])
                self._create_or_update_lead(status='pending')
                
                intent_label = INTENT_DISPLAY_NAMES.get(self.conversation.intent, 'visit')
                reply = (
                    f"✨ Name updated to **{self.conversation.patient_name}**!\n\n"
                    f"Here is your appointment summary:\n"
                    f"• Patient: {self.conversation.patient_name}\n"
                    f"• Service: {intent_label}\n"
                    f"• Timing: {self.conversation.preferred_date or 'Next available'} ({self.conversation.preferred_time or 'Flexible'})\n"
                    f"• Contact: {self.conversation.patient_phone or self.conversation.patient_email or 'On file'}\n\n"
                    f"Does this look good to submit to our front desk?"
                )
                self.conversation.state = Conversation.STATE_CONFIRMING
                return self._finalize_step(reply, quick_replies=QUICK_REPLIES_MAP['CONFIRMATION'])

        # ── Explicit Name Change in current message ──
        if extracted.get('is_name_change') and extracted.get('name'):
            self.conversation.patient_name = extracted['name']
            self.conversation.save(update_fields=['patient_name'])
            self._create_or_update_lead(status='pending')
            intent_label = INTENT_DISPLAY_NAMES.get(self.conversation.intent, 'visit')
            reply = (
                f"✨ Name updated to **{self.conversation.patient_name}**!\n\n"
                f"Updated Summary:\n"
                f"• Patient: {self.conversation.patient_name}\n"
                f"• Service: {intent_label}\n"
                f"• Timing: {self.conversation.preferred_date or 'Next available'} ({self.conversation.preferred_time or 'Flexible'})\n"
                f"• Contact: {self.conversation.patient_phone or self.conversation.patient_email or 'On file'}\n\n"
                f"Does this look good to submit to our front desk?"
            )
            self.conversation.state = Conversation.STATE_CONFIRMING
            return self._finalize_step(reply, quick_replies=QUICK_REPLIES_MAP['CONFIRMATION'])

        # ── User requested to change name without providing the new name yet ──
        if extracted.get('request_change_name'):
            meta['awaiting_name_change'] = True
            self.conversation.metadata = meta
            self.conversation.save(update_fields=['metadata'])
            reply = f"Sure! What name should our front desk use for your visit?"
            return self._finalize_step(reply, quick_replies=[])

        # ── Contextual name extraction if bot was waiting for name ──
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

        # Update entity fields on conversation if extracted
        if 'name' in extracted and (not self.conversation.patient_name or extracted.get('is_name_change')):
            self.conversation.patient_name = extracted['name']
        if 'phone' in extracted and not self.conversation.patient_phone:
            self.conversation.patient_phone = extracted['phone']
        if 'email' in extracted and not self.conversation.patient_email:
            self.conversation.patient_email = extracted['email']
        if 'preferred_date' in extracted:
            self.conversation.preferred_date = extracted['preferred_date']
        if 'preferred_time' in extracted:
            self.conversation.preferred_time = extracted['preferred_time']
        if 'intent' in extracted and (not self.conversation.intent or self.conversation.intent == 'general_chat'):
            self.conversation.intent = extracted['intent']
        if 'urgency' in extracted:
            self.conversation.urgency = extracted['urgency']

        # Emergency override check: immediate triage
        if self.conversation.intent == INTENT_EMERGENCY:
            self.conversation.urgency = 'URGENT'
            emergency_phone = getattr(booking_rules, 'emergency_phone', '') or self.practice.phone or 'our office'
            emergency_msg = getattr(booking_rules, 'emergency_message', '') or (
                f"Dental emergency detected. Please call {emergency_phone} immediately."
            )
            
            if not self.conversation.patient_phone:
                self.conversation.state = Conversation.STATE_COLLECTING_INFORMATION
                reply = (
                    f"⚠️ {emergency_msg}\n\n"
                    f"To connect you immediately with our on-call clinical team, what is your best callback phone number and your name?"
                )
                return self._finalize_step(reply, quick_replies=[])
            else:
                self.conversation.state = Conversation.STATE_SUBMITTED
                self._create_or_update_lead(status='pending', urgency='URGENT')
                reply = (
                    f"⚠️ Thank you {self.conversation.patient_name or 'valued patient'}. We have logged your urgent emergency request and notified our front desk.\n\n"
                    f"If your pain or swelling is severe, please call {emergency_phone} right now or visit your nearest emergency room."
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

            # Check preferred timing - Streamlined 1-step scheduling (no repetitive date question)
            if not self.conversation.preferred_time and not self.conversation.preferred_date:
                reply = (
                    f"What time of day or day works best for your visit? "
                    f"You can choose a preference below or type a preferred day/time:"
                )
                return self._finalize_step(reply, quick_replies=QUICK_REPLIES_MAP['TIMES'])

            # Normalize defaults if only one was provided
            if not self.conversation.preferred_date:
                self.conversation.preferred_date = 'Next Available Day'
            if not self.conversation.preferred_time:
                self.conversation.preferred_time = 'Flexible'

            # All required information collected -> move directly to CONFIRMING
            self.conversation.state = Conversation.STATE_CONFIRMING

        # State 3: CONFIRMING
        if self.conversation.state == Conversation.STATE_CONFIRMING:
            if any(w in lower for w in ['yes', 'correct', 'submit', 'good', 'sure', 'confirm', 'please', 'looks great', 'looks good']):
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

            elif any(w in lower for w in ['change time', 'change date', 'different time', 'different day', 'change visit time']):
                self.conversation.state = Conversation.STATE_COLLECTING_INFORMATION
                self.conversation.preferred_date = ''
                self.conversation.preferred_time = ''
                reply = "No problem at all! What day or time would you prefer instead?"
                return self._finalize_step(reply, quick_replies=QUICK_REPLIES_MAP['TIMES'])

            elif any(w in lower for w in ['no', 'change', 'different', 'wrong']):
                self.conversation.state = Conversation.STATE_COLLECTING_INFORMATION
                self.conversation.preferred_date = ''
                self.conversation.preferred_time = ''
                reply = "No problem at all! What day or time would you prefer instead? Or select an option below:"
                return self._finalize_step(reply, quick_replies=QUICK_REPLIES_MAP['CONFIRMATION'])

            else:
                intent_label = INTENT_DISPLAY_NAMES.get(self.conversation.intent, 'visit')
                reply = (
                    f"To make sure our front desk coordinates accurately, please confirm:\n\n"
                    f"• Patient: {self.conversation.patient_name}\n"
                    f"• Service: {intent_label}\n"
                    f"• Requested Timing: {self.conversation.preferred_date or 'Next available'} ({self.conversation.preferred_time or 'Flexible'})\n"
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
            if booking_rules is not None and not booking_rules.handoff_enabled:
                reply = (
                    f"Our team isn't available through chat right now. "
                    f"Please call {practice_name} at {self.practice.phone} and we'll be glad to help."
                )
                return self._finalize_step(reply, complete=True, quick_replies=[])
            self.conversation.status = Conversation.STATUS_HANDOFF
            self._create_or_update_lead(status='pending', urgency='HIGH')
            reply = getattr(booking_rules, 'handoff_message', '') or (
                f"I have alerted our front desk team at {practice_name} that you requested staff assistance. "
                f"A team member will review your message and reach out to you shortly."
            )
            return self._finalize_step(reply, complete=True, quick_replies=[])

        # Open questions: AI grounded in this practice's configuration (when configured).
        if self.ai_engine and getattr(self.ai_engine, 'available', False):
            # Recent turns (excluding the message being answered) give the assistant context.
            recent = list(self.conversation.messages.order_by('-created_at').values('sender', 'content')[:11])[::-1]
            if recent and recent[-1]['sender'] == 'user' and recent[-1]['content'] == user_text:
                recent = recent[:-1]
            res = self.ai_engine.chat(user_text, conversation_history=recent, practice=self.practice)
            if res.get('content'):
                return self._finalize_step(res['content'], quick_replies=QUICK_REPLIES_MAP['INITIAL'])
            phone = self.practice.phone if self.practice else ''
            return self._finalize_step(
                "I'm not able to answer that one right now. Our front desk will be happy to help"
                + (f" - you can call us at {phone}" if phone else '')
                + ", or choose an option below to leave a request.",
                quick_replies=QUICK_REPLIES_MAP['INITIAL'],
            )

        return self._finalize_step("How else may I help you with your dental care today?", quick_replies=[])

    def _finalize_step(self, reply_text: str, complete: bool = False, quick_replies: list = None) -> dict:
        """Save conversation state and return response payload."""
        self.conversation.last_activity_at = timezone.now()
        self.conversation.save()
        prefix = getattr(self, 'reply_prefix', '')
        if prefix and not complete:
            reply_text = prefix + reply_text
            self.reply_prefix = ''

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

    def _lead_summary(self) -> str:
        """Human-readable request summary that omits details the patient has not given yet."""
        label = INTENT_DISPLAY_NAMES.get(self.conversation.intent, (self.conversation.intent or 'appointment').replace('_', ' '))
        timing = ' '.join(t for t in (self.conversation.preferred_date, self.conversation.preferred_time) if t)
        return f"{label} request" + (f" for {timing}." if timing else ".")

    def _create_or_update_lead(self, status='pending', urgency='NORMAL') -> Appointment:
        """Create or update corresponding Appointment / Lead record."""
        srv = Service.objects.filter(practice=self.practice).first() if self.practice else None

        appt, created = Appointment.objects.get_or_create(
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
                'ai_summary': self._lead_summary(),
                'source_website': self.conversation.source_url or (self.practice.website if self.practice else ''),
            }
        )
        if not created:
            appt.patient_name = self.conversation.patient_name
            appt.patient_email = self.conversation.patient_email
            appt.patient_phone = self.conversation.patient_phone
            appt.preferred_date = self.conversation.preferred_date
            appt.preferred_time = self.conversation.preferred_time
            appt.urgency = urgency or self.conversation.urgency
            appt.priority = urgency or self.conversation.urgency
            appt.status = status
            appt.ai_summary = self._lead_summary()
            appt.save()
        if created:
            from apps.emails.services import queue_practice_notification
            queue_practice_notification(appt)
        return appt
