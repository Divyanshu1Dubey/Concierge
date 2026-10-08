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

    def sanitize_output(self, text: str) -> str:
        """Sanitize AI output before sending to user."""
        # Remove any potential instruction-like content
        for pattern in self.BLOCKED_PATTERNS:
            text = re.sub(pattern, '[redacted]', text, flags=re.IGNORECASE)
        return text
