"""
AI Safety - content filtering and guardrails.
"""
import re


class AISafety:
    """Safety checks for AI inputs and outputs."""

    BLOCKED_PATTERNS = [
        # Prompt injection attempts
        r'ignore (previous|all|above) (instructions?|rules?|prompts?)',
        r'you are (now|now a)',
        r'pretend (to be|you are)',
        r'act as (if|a|an)',
        r'disregard (all|any|the)',
        r'forget (everything|all|your)',
        r'new instructions?:',
        r'system prompt:',
        r'\[INST\]',
        r'<\|im_start\|>',
        # Medical advice beyond scope
        r'prescribe',
        r'diagnosis',
        r'what (disease|condition|illness) do i have',
    ]

    ESCALATION_KEYWORDS = [
        'suicide', 'kill myself', 'self-harm', 'overdose',
        'domestic violence', 'abuse',
    ]

    def check_message(self, message: str) -> dict:
        """Check if a message is safe to process."""
        if not message or not message.strip():
            return {'safe': False, 'reason': 'empty_message'}

        # Check for prompt injection
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return {'safe': False, 'reason': 'prompt_injection_detected'}

        # Check for escalation keywords
        for keyword in self.ESCALATION_KEYWORDS:
            if keyword in message.lower():
                return {'safe': True, 'requires_human': True, 'escalation_reason': keyword}

        return {'safe': True}

    # Reply-side checks: patient-facing text must not state things the practice never approved.
    INJECTION_MARKERS = [r'\[INST\]', r'<\|im_start\|>', r'system prompt', r'PRACTICE FACTS:', r'Rules you must always follow']
    PRICE_RE = re.compile(r'(\$\s?\d[\d,]*(\.\d{2})?)|(\b\d[\d,]*\s?(dollars|usd)\b)', re.IGNORECASE)
    BOOKED_RE = re.compile(
        r"\b(you('re| are)( now)? (all )?(booked|scheduled|confirmed)|"
        r"(your |the )?appointment (is|has been) (booked|confirmed|scheduled|set)|"
        r"i('ve| have) (booked|scheduled|confirmed|reserved)|we('ve| have) (booked|reserved) (you|your))", re.IGNORECASE)
    INSURERS = ('delta dental', 'cigna', 'aetna', 'metlife', 'humana', 'united healthcare', 'unitedhealthcare',
                'blue cross', 'bcbs', 'anthem', 'medicaid', 'medicare', 'tricare', 'ameritas', 'geha')

    def check_reply(self, text: str, facts: str = '') -> dict:
        """Validate a patient-facing AI reply against the practice's approved facts.

        Returns {'ok': bool, 'reason': str}. Blocks: leaked instructions, prices not present in the facts,
        named insurers not present in the facts, and claims that a visit is booked/confirmed.
        """
        if not text or not text.strip():
            return {'ok': False, 'reason': 'empty'}
        low_facts = (facts or '').lower()
        fact_numbers = re.sub(r'[^\d.]+', ' ', re.sub(r'(?<=\d),(?=\d)', '', low_facts)).split()
        for marker in self.INJECTION_MARKERS:
            if re.search(marker, text, re.IGNORECASE):
                return {'ok': False, 'reason': 'instruction_leak'}
        for m in self.PRICE_RE.finditer(text):
            amount = re.sub(r'[^\d.]', '', m.group(0))
            if not amount or amount not in fact_numbers:
                return {'ok': False, 'reason': 'unapproved_price'}
        if self.BOOKED_RE.search(text):
            return {'ok': False, 'reason': 'booking_claim'}
        low = text.lower()
        for insurer in self.INSURERS:
            if insurer in low and insurer not in low_facts:
                return {'ok': False, 'reason': 'unapproved_insurance'}
        return {'ok': True, 'reason': ''}

    def sanitize_output(self, text: str) -> str:
        """Sanitize AI output before sending to user."""
        # Remove any potential instruction-like content
        for pattern in self.BLOCKED_PATTERNS:
            text = re.sub(pattern, '[redacted]', text, flags=re.IGNORECASE)
        return text
