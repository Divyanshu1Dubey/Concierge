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
        {'label': '✅ Submit request', 'value': 'Yes, please submit my request'},
        {'label': '🕒 Change Time / Day', 'value': 'Change my visit time'},
        {'label': '👤 Change Name', 'value': 'Change my name'},
    ],
    'TIMES': [
        {'label': 'Morning (8am - 12pm)', 'value': 'Morning works best for me'},
        {'label': 'Afternoon (12pm - 5pm)', 'value': 'Afternoon works best for me'},
        {'label': 'First available', 'value': 'First available opening'},
    ]
}

NOT_NAME_WORDS = {
    'a', 'an', 'the', 'new', 'existing', 'returning', 'current', 'patient', 'looking', 'interested', 'having',
    'calling', 'trying', 'wondering', 'hoping', 'planning', 'going', 'getting', 'feeling', 'writing', 'reaching',
    'contacting', 'asking', 'booking', 'scheduling', 'just', 'not', 'so', 'very', 'really', 'still', 'also',
    'here', 'there', 'available', 'free', 'good', 'fine', 'great', 'ok', 'okay', 'sure', 'ready', 'sorry',
    'afraid', 'able', 'unable', 'sick', 'scared', 'nervous', 'worried', 'in', 'at', 'on', 'from', 'with', 'yes',
    'no', 'hi', 'hello', 'hey', 'thanks', 'thank', 'please', 'what', 'when', 'where', 'how', 'why', 'who',
    'which', 'can', 'could', 'would', 'will', 'do', 'does', 'is', 'are', 'was', 'need', 'want', 'like', 'help',
    'it', 'its', "it's", 'that', 'this', 'your', 'our', 'his', 'her', 'their', 'any', 'some', 'monday',
    'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'tomorrow', 'today', 'morning',
    'afternoon', 'evening', 'next', 'week', 'first', 'asap', 'anytime', 'currently', 'pregnant', 'busy',
    'back', 'done', 'sorry', 'glad', 'happy', 'curious', 'confused', 'late', 'early', 'out', 'over', 'about',
}
NAME_STOP_WORDS = {
    'and', 'but', 'or', 'so', 'to', 'for', 'with', 'in', 'at', 'on', 'from', 'i', 'im', "i'm", 'my', 'me',
    'would', 'like', 'want', 'need', 'please', 'thanks', 'thank', 'because', 'about', 'regarding', 'and',
    'here', 'calling', 'looking', 'who', 'id', "i'd", 'is', 'am',
}
DENTAL_WORDS = {
    'appointment', 'appointments', 'book', 'booking', 'cleaning', 'clean', 'checkup', 'exam', 'emergency',
    'pain', 'tooth', 'teeth', 'toothache', 'cancel', 'reschedule', 'visit', 'dentist', 'doctor', 'staff', 'desk',
    'front', 'question', 'insurance', 'crown', 'filling', 'implant', 'whitening', 'invisalign', 'braces',
    'hygiene', 'consult', 'consultation', 'office', 'hours', 'request',
}


def _clean_name_candidate(raw: str) -> str:
    """First 1-3 name-like words of a fragment; '' if it does not look like a person's name."""
    raw = re.split(r"[,.;!?\n]|\s-\s", raw or '', maxsplit=1)[0]
    tokens = []
    for tok in raw.strip().split():
        t = tok.strip("'\"()")
        tl = t.lower()
        if not tokens and (tl in NOT_NAME_WORDS or tl in DENTAL_WORDS):
            return ''
        if tl in NAME_STOP_WORDS or tl in NOT_NAME_WORDS or tl in DENTAL_WORDS:
            break
        if not re.match(r"^[A-Za-z][A-Za-z'-]*$", t):
            break
        tokens.append(t)
        if len(tokens) == 3:
            break
    return ' '.join(w if (not w.islower() and not w.isupper()) else w.capitalize() for w in tokens)


NAME_CHANGE_PATTERNS = [
    r"\b(?:change|update)\s+(?:my\s+)?name\s+to\s+(.+)",
    r"\bactually,?\s+(?:my name is|my name's|it's|its|i'm|im|i am)\s+(.+)",
    r"\b(?:please\s+)?call me\s+(?!at\b|on\b|back\b|tomorrow\b|today\b|later\b|anytime\b|whenever\b)(.+)",
]
EXPLICIT_NAME_PATTERNS = [
    r"\bmy name(?:'s| is)\s+(.+)",
    r"\bname\s*(?:is|:)\s*(.+)",
    r"^(?:hi|hello|hey)?[\s,!.]*(?:this is|it's|its)\s+(.+)",
    r"\b(?:i am|i'm|im)\s+(.+)",
]


def contextual_name(text: str, extracted: dict) -> str:
    """Name from a reply to 'What is your full name?' (e.g. "it's John Park", "919-555-0177 Lily")."""
    t = text
    for k in ('email', 'phone'):
        if extracted.get(k):
            t = t.replace(extracted[k], ' ')
    t = re.sub(r"^\s*(?:hi|hello|hey|sure|yes|yeah|ok|okay)?[\s,!.]*"
               r"(?:it's|its|it is|this is|my name is|my name's|name's|name is|i'm|im|i am)?\s*", '', t, flags=re.I)
    cand = _clean_name_candidate(t)
    return cand if cand and len(cand.split()) <= 4 else ''


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

    # 3. Name change intent & name extraction (only words that look like a name)
    for pattern in NAME_CHANGE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            candidate = _clean_name_candidate(m.group(1))
            if candidate:
                extracted['name'] = candidate
                extracted['is_name_change'] = True
                break

    if 'name' not in extracted:
        for pattern in EXPLICIT_NAME_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                candidate = _clean_name_candidate(m.group(1))
                if candidate:
                    extracted['name'] = candidate
                    break

    if any(phrase in lower for phrase in ['change name', 'change my name', 'wrong name', 'update name', 'different name']):
        extracted['request_change_name'] = True

    def has(*phrases):
        return any(re.search(r'\b' + re.escape(ph) + r'\b', lower) for ph in phrases)

    # 4. Intent detection (whole words, so "afternoon" is not "no" and "clean" is not "unclean")
    if has('emergency', 'severe pain', 'bleeding', 'swelling', 'swollen', 'broken tooth', 'knocked out', 'agony',
           'throbbing', 'toothache', 'tooth ache', 'tooth hurts', 'teeth hurt', 'tooth pain', 'hurts', 'in pain',
           'pain', 'abscess', 'chipped', 'cracked', 'broke', 'broken', 'lost a filling', 'filling fell out',
           'crown fell off'):
        extracted['intent'] = INTENT_EMERGENCY
        extracted['urgency'] = 'URGENT'
    elif has('cleaning', 'clean', 'hygiene', 'checkup', 'check up', 'check-up', 'routine'):
        extracted['intent'] = INTENT_CLEANING
    elif has('reschedule', 'move appointment', 'move my appointment', 'change my appointment'):
        extracted['intent'] = INTENT_RESCHEDULE
    elif has('cancel', 'cancellation', 'call off'):
        extracted['intent'] = INTENT_CANCEL
    elif has('talk to someone', 'speak to staff', 'speak with', 'talk to', 'speak to', 'human', 'real person',
             'representative', 'operator', 'front desk', 'receptionist'):
        extracted['intent'] = INTENT_HANDOFF
    elif has('cost', 'price', 'insurance', 'hours', 'where', 'how much', 'do you accept', 'parking', 'location'):
        extracted['intent'] = INTENT_QUESTION
    elif has('book', 'booking', 'appointment', 'appoint', 'appiintment', 'schedule', 'see the dentist',
             'see doctor', 'consultation', 'new patient', 'first time', 'new to', 'switch to', 'whitening',
             'invisalign', 'implant', 'implants', 'crown', 'filling', 'veneer', 'veneers', 'exam', 'visit'):
        extracted['intent'] = INTENT_NEW_PATIENT
    if 'intent' not in extracted and re.search(r'\b(?:a |general |quick )?question\b', lower):
        extracted['wants_question'] = True

    # 5. Preferred Date extraction
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'tomorrow', 'today', 'next week']
    for d in days:
        if re.search(r'\b' + d + r'\b', lower):
            extracted['preferred_date'] = d.capitalize()
            break

    # 6. Preferred Time extraction
    if has('first available', 'asap', 'anytime', 'any time', 'earliest', 'any slot', 'first opening'):
        extracted['preferred_time'] = 'First Available'
    elif has('morning', 'mornings'):
        extracted['preferred_time'] = 'Morning'
    elif has('afternoon', 'afternoons'):
        extracted['preferred_time'] = 'Afternoon'
    elif has('evening', 'evenings'):
        extracted['preferred_time'] = 'Evening'
    else:
        time_match = re.search(r'(?:after\s+|around\s+|at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm))', lower)
        if time_match:
            extracted['preferred_time'] = time_match.group(0).strip().upper()

    return extracted


def office_open_at(practice, when=None):
    """True/False if the office is open at `when` in the practice's own timezone; None when hours are not set."""
    from zoneinfo import ZoneInfo
    rules = getattr(practice, 'booking_rules', None)
    hours = getattr(rules, 'business_hours', None) or {}
    if not hours:
        return None
    try:
        tz = ZoneInfo(getattr(practice, 'timezone', '') or 'UTC')
    except Exception:
        tz = ZoneInfo('UTC')
    local = (when or timezone.now()).astimezone(tz)
    day_config = hours.get(local.strftime('%A').lower())
    if not isinstance(day_config, dict) or day_config.get('closed', False):
        return False
    current = local.strftime('%H:%M')
    return day_config.get('open', '08:00') <= current <= day_config.get('close', '17:00')


def is_office_open(practice) -> tuple[bool, str]:
    """Check if the practice is currently open according to business hours (practice timezone)."""
    try:
        is_open = office_open_at(practice)
        if is_open is None or is_open:
            return True, ""
        rules = getattr(practice, 'booking_rules', None)
        return False, (getattr(rules, 'after_hours_message', '') or "Our office is currently closed.")
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
        """A question the patient asks (before or during a request) that is not an emergency or booking detail."""
        early = current_state in (Conversation.STATE_STARTED, Conversation.STATE_IDENTIFYING_INTENT)
        mid = current_state in (Conversation.STATE_COLLECTING_INFORMATION, Conversation.STATE_CONFIRMING)
        if not (early or mid):
            return False
        if extracted.get('intent') == INTENT_EMERGENCY:
            return False
        if any(k in extracted for k in ('name', 'phone', 'email', 'request_change_name')):
            return False
        if mid and any(k in extracted for k in ('preferred_date', 'preferred_time')):
            return False
        if early:
            if self.conversation.intent and self.conversation.intent not in ('general_chat', INTENT_QUESTION):
                return False
            if extracted.get('intent') not in (None, INTENT_QUESTION):
                return False
        text = user_text.strip().lower()
        if mid and re.search(r'\b(change|different|another|reschedul)\b', text):
            return False  # "can you change the time?" is part of the request, not an info question
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

    def _needs_timing(self) -> bool:
        return self.conversation.intent not in (INTENT_CANCEL, INTENT_HANDOFF)

    def _summary_text(self) -> str:
        c = self.conversation
        lines = [
            f"• Patient: {c.patient_name}",
            f"• Request: {INTENT_DISPLAY_NAMES.get(c.intent, 'Visit')}",
        ]
        if self._needs_timing():
            lines.append(f"• Preferred timing: {c.preferred_date or 'Next available'} ({c.preferred_time or 'Flexible'})")
        lines.append(f"• Contact: {c.patient_phone or c.patient_email}")
        return '\n'.join(lines)

    def _confirm_chips(self):
        chips = QUICK_REPLIES_MAP['CONFIRMATION']
        return chips if self._needs_timing() else [c for c in chips if 'time' not in c['value'].lower()]

    def _resume_prompt(self):
        """The question the request flow is currently waiting on (text, quick replies)."""
        c = self.conversation
        if c.state == Conversation.STATE_COLLECTING_INFORMATION:
            if not c.patient_name:
                return "What is your full name?", []
            if not c.patient_phone and not c.patient_email:
                return "What is the best phone number or email for our front desk to reach you?", []
            if self._needs_timing() and not c.preferred_time and not c.preferred_date:
                return "What time of day or day works best for your visit?", QUICK_REPLIES_MAP['TIMES']
        if c.state == Conversation.STATE_CONFIRMING:
            return "Shall I send this request to our front desk?\n\n" + self._summary_text(), self._confirm_chips()
        return "Is there anything else I can help with, or would you like to request an appointment?", QUICK_REPLIES_MAP['INITIAL']

    def _answer_question(self, user_text: str, resume: bool = False) -> dict:
        """Answer an informational question (AI if configured, else practice facts only)."""
        if not resume:
            self.conversation.state = Conversation.STATE_IDENTIFYING_INTENT
            if self.conversation.intent == INTENT_QUESTION:
                self.conversation.intent = ''
        from apps.practices.knowledge import looks_like_deferral, match_entry, record_unanswered
        phone = self.practice.phone if self.practice else ''
        answer = None
        unanswered = False
        if self.ai_engine and getattr(self.ai_engine, 'available', False):
            res = self.ai_engine.chat(user_text, practice=self.practice)
            answer = res.get('content')
            if answer and looks_like_deferral(answer):
                unanswered = True
        if not answer:
            lower = user_text.lower()
            hours = self._hours_text()
            entry = match_entry(self.practice, user_text) if self.practice else None
            if entry:
                answer = entry.content.strip()
            elif hours and any(w in lower for w in ('hour', 'open', 'close', 'closed')):
                answer = f"Our office hours are: {hours}."
            else:
                unanswered = True
                answer = (
                    "That's a great question for our front desk team"
                    + (f" - you can reach them at {phone}" if phone else '')
                    + ". I can also take a request so they can follow up with you."
                )
        if unanswered and self.practice:
            record_unanswered(self.practice, user_text)
        prompt, chips = self._resume_prompt()
        lead = "\n\nNow, to finish your request: " if resume else "\n\n"
        return self._finalize_step(answer + lead + prompt, quick_replies=chips)

    def process_message(self, user_text: str) -> dict:
        """Process incoming visitor message and transition state."""
        extracted = extract_entities(user_text)
        lower = user_text.lower()
        current_state = self.conversation.state or Conversation.STATE_STARTED
        practice_name = self.practice.name if self.practice else "our office"
        booking_rules = getattr(self.practice, 'booking_rules', None)
        meta = self.conversation.metadata or {}
        early = current_state in (Conversation.STATE_STARTED, Conversation.STATE_IDENTIFYING_INTENT)

        # "I have a general question" -> invite the question; the next message is answered.
        if early and extracted.get('wants_question') and not extracted.get('intent'):
            meta['awaiting_question'] = True
            self.conversation.metadata = meta
            self.conversation.state = Conversation.STATE_IDENTIFYING_INTENT
            return self._finalize_step(
                "Of course! What would you like to know? I can help with our hours, location, services, "
                "insurance questions, or requesting a visit.",
                quick_replies=[],
            )
        if early and meta.pop('awaiting_question', None):
            self.conversation.metadata = meta
            if extracted.get('intent') in (None, INTENT_QUESTION):
                return self._answer_question(user_text)

        # Informational questions are answered directly (and the request flow resumes afterwards).
        if self._is_info_question(user_text, extracted, current_state):
            return self._answer_question(user_text, resume=not early)

        # "Do you have anything free tomorrow?" - be explicit that availability is not checked live.
        self.reply_prefix = ''
        if early and user_text.strip().endswith('?') and re.search(r'\b(available|availability|free|opening|openings|slot|slots|space)\b', lower):
            self.reply_prefix = (
                "I can't see the live schedule, but I can pass your preferred time to our front desk "
                "and they will confirm what's available. "
            )
        is_open, after_hours_msg = is_office_open(self.practice)

        # ── Patient was asked for a new name ──
        if meta.get('awaiting_name_change'):
            new_name = extracted.get('name') or contextual_name(user_text, extracted)
            if new_name:
                self.conversation.patient_name = new_name
                meta.pop('awaiting_name_change', None)
                self.conversation.metadata = meta
                self.conversation.state = Conversation.STATE_CONFIRMING
                self._create_or_update_lead(status='pending')
                return self._finalize_step(
                    f"Thanks, I've updated your name to **{new_name}**.\n\n" + self._summary_text()
                    + "\n\nShall I send this request to our front desk?",
                    quick_replies=self._confirm_chips(),
                )
            return self._finalize_step("Sorry, I didn't catch that. What name should our front desk use?", quick_replies=[])

        # ── Explicit name change ("actually my name is ...", "call me Sam") ──
        if extracted.get('is_name_change') and extracted.get('name') and self.conversation.patient_name:
            self.conversation.patient_name = extracted['name']
            if current_state == Conversation.STATE_CONFIRMING:
                self._create_or_update_lead(status='pending')
                return self._finalize_step(
                    f"Thanks, I've updated your name to **{self.conversation.patient_name}**.\n\n" + self._summary_text()
                    + "\n\nShall I send this request to our front desk?",
                    quick_replies=self._confirm_chips(),
                )

        # ── Patient wants to change the name but has not given it yet ──
        if extracted.get('request_change_name') and not extracted.get('name'):
            meta['awaiting_name_change'] = True
            self.conversation.metadata = meta
            return self._finalize_step("Sure! What name should our front desk use for your visit?", quick_replies=[])

        # ── Reply to "What is your full name?" ──
        if current_state == Conversation.STATE_COLLECTING_INFORMATION and not self.conversation.patient_name and 'name' not in extracted:
            name = contextual_name(user_text, extracted)
            if name:
                extracted['name'] = name

        # Update entity fields on conversation if extracted
        if 'name' in extracted and (not self.conversation.patient_name or extracted.get('is_name_change')):
            self.conversation.patient_name = extracted['name']
        if 'phone' in extracted:
            self.conversation.patient_phone = extracted['phone']
        if 'email' in extracted:
            self.conversation.patient_email = extracted['email']
        if 'preferred_date' in extracted:
            self.conversation.preferred_date = extracted['preferred_date']
        if 'preferred_time' in extracted:
            self.conversation.preferred_time = extracted['preferred_time']
        new_intent = extracted.get('intent')
        cur_intent = self.conversation.intent
        if new_intent and (
            not cur_intent or cur_intent == 'general_chat'
            or new_intent in (INTENT_EMERGENCY, INTENT_HANDOFF)
            or (cur_intent in (INTENT_RESCHEDULE, INTENT_CANCEL) and new_intent in (INTENT_RESCHEDULE, INTENT_CANCEL))
        ):
            if not (new_intent == INTENT_QUESTION and cur_intent):
                self.conversation.intent = new_intent
        if 'urgency' in extracted:
            self.conversation.urgency = extracted['urgency']

        # Emergency override: immediate triage
        if self.conversation.intent == INTENT_EMERGENCY:
            self.conversation.urgency = 'URGENT'
            emergency_phone = getattr(booking_rules, 'emergency_phone', '') or self.practice.phone or 'our office'
            emergency_msg = getattr(booking_rules, 'emergency_message', '') or (
                f"If this is a dental emergency, please call {emergency_phone} right away."
            )
            if not self.conversation.patient_phone:
                self.conversation.state = Conversation.STATE_COLLECTING_INFORMATION
                reply = (
                    f"⚠️ {emergency_msg}\n\n"
                    f"So our team can reach you quickly, what is your best callback phone number and your name?"
                )
                return self._finalize_step(reply, quick_replies=[])
            self.conversation.state = Conversation.STATE_SUBMITTED
            self._create_or_update_lead(status='pending', urgency='URGENT')
            reply = (
                f"⚠️ Thank you{(' ' + self.conversation.patient_name) if self.conversation.patient_name else ''}. "
                f"We've sent your urgent request to our front desk and they will call you at {self.conversation.patient_phone}.\n\n"
                f"If your pain or swelling is severe, please call {emergency_phone} right now or visit your nearest emergency room."
            )
            return self._finalize_step(reply, complete=True, quick_replies=[])

        # State 1: STARTED -> IDENTIFYING_INTENT
        if early:
            if not self.conversation.intent or self.conversation.intent == 'general_chat':
                self.conversation.state = Conversation.STATE_IDENTIFYING_INTENT
                greeting_only = re.match(r"^\s*(hi|hello|hey|hiya|howdy|good (morning|afternoon|evening))[\s!.,]*$", lower)
                if greeting_only or current_state == Conversation.STATE_STARTED:
                    reply = f"Hello and welcome to {practice_name}! How can I help you today?"
                else:
                    reply = (
                        "I can help with that. Would you like to request a visit, or is something hurting right now? "
                        "Tap an option below or tell me a little more."
                    )
                return self._finalize_step(reply, quick_replies=QUICK_REPLIES_MAP['INITIAL'])
            self.conversation.state = Conversation.STATE_COLLECTING_INFORMATION

        entered_confirming = False
        # State 2: COLLECTING_INFORMATION
        if self.conversation.state == Conversation.STATE_COLLECTING_INFORMATION:
            intent_label = INTENT_DISPLAY_NAMES.get(self.conversation.intent, 'visit')
            if not self.conversation.patient_name:
                if self.conversation.intent == INTENT_HANDOFF:
                    reply = "I'll ask a member of our team to get in touch. What is your full name?"
                elif self.conversation.intent == INTENT_CANCEL:
                    reply = "I can pass your cancellation to our front desk. What is your full name?"
                else:
                    reply = f"I would be glad to help with your {intent_label}. What is your full name?"
                return self._finalize_step(reply)

            if not self.conversation.patient_phone and not self.conversation.patient_email:
                reply = f"Nice to meet you, {self.conversation.patient_name}! What is the best phone number or email for our front desk to reach you?"
                return self._finalize_step(reply)

            if self.conversation.intent == INTENT_HANDOFF:
                self.conversation.state = Conversation.STATE_HANDOFF
            elif self._needs_timing() and not self.conversation.preferred_time and not self.conversation.preferred_date:
                return self._finalize_step(
                    "What time of day or day works best for your visit? Choose an option below or type a day and time.",
                    quick_replies=QUICK_REPLIES_MAP['TIMES'],
                )
            else:
                if self._needs_timing():
                    self.conversation.preferred_date = self.conversation.preferred_date or 'Next Available Day'
                    self.conversation.preferred_time = self.conversation.preferred_time or 'Flexible'
                self.conversation.state = Conversation.STATE_CONFIRMING
                entered_confirming = True

        # State 3: CONFIRMING
        if self.conversation.state == Conversation.STATE_CONFIRMING:
            if entered_confirming:
                return self._finalize_step(
                    "Please confirm your request:\n\n" + self._summary_text() + "\n\nShall I send this to our front desk?",
                    quick_replies=self._confirm_chips(),
                )
            wants_new_time = re.search(r"\b(change|different|another|other|new|move)\b[^.?!]*\b(time|times|day|date|slot)\b", lower)
            says_no = re.search(r"\b(no|nope|nah|wrong|incorrect|change|edit|fix)\b|\bnot (right|correct)\b", lower)
            says_yes = re.search(r"\b(yes|yep|yeah|yup|correct|confirm|confirmed|submit|sure|ok|okay|perfect|go ahead)\b"
                                 r"|\blooks (good|great|right|fine)\b|\bsounds good\b|\bthat'?s (right|correct)\b", lower)
            if wants_new_time:
                self.conversation.state = Conversation.STATE_COLLECTING_INFORMATION
                self.conversation.preferred_date = ''
                self.conversation.preferred_time = ''
                return self._finalize_step("No problem! What day or time would you prefer instead?", quick_replies=QUICK_REPLIES_MAP['TIMES'])
            if says_no:
                return self._finalize_step(
                    "No problem. What would you like to change? You can change the time or your name, or just type the correction.",
                    quick_replies=self._confirm_chips()[1:],
                )
            if says_yes:
                self.conversation.state = Conversation.STATE_SUBMITTED
                self._create_or_update_lead(status='pending')
                noun = {INTENT_CANCEL: 'cancellation request', INTENT_RESCHEDULE: 'reschedule request'}.get(
                    self.conversation.intent, 'appointment request')
                after_hours_note = f"\n\nNote: {after_hours_msg}" if not is_open else ""
                reply = (
                    f"✨ Thank you! Your {noun} has been submitted to {practice_name}.\n\n"
                    + self._summary_text()
                    + f"\n\nOur front desk will contact you at {self.conversation.patient_phone or self.conversation.patient_email}"
                    + (" to confirm a time. Your visit is not booked until they confirm it with you." if self._needs_timing() else ".")
                    + after_hours_note
                )
                return self._finalize_step(reply, complete=True, quick_replies=[])
            return self._finalize_step(
                "Shall I send this request to our front desk?\n\n" + self._summary_text(),
                quick_replies=self._confirm_chips(),
            )

        # State: SUBMITTED
        if self.conversation.state == Conversation.STATE_SUBMITTED:
            reply = (
                f"Your request has already been sent to the {practice_name} front desk. "
                f"If you need us urgently, please call {self.practice.phone}."
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
                f"I've let our front desk team at {practice_name} know you'd like to speak with someone. "
                f"A team member will contact you at {self.conversation.patient_phone or self.conversation.patient_email} shortly."
            )
            return self._finalize_step(reply, complete=True, quick_replies=[])

        # Open questions: AI grounded in this practice's configuration (when configured).
        if self.ai_engine and getattr(self.ai_engine, 'available', False):
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

        return self._finalize_step("How else may I help you with your dental care today?", quick_replies=QUICK_REPLIES_MAP['INITIAL'])

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
