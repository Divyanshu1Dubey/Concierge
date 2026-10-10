"""
AI Chat engine - orchestrates AI interactions.
"""
import time
import logging
from django.conf import settings
from typing import Optional
from .providers import get_ai_provider
from .models import AIInteractionLog
from .safety import AISafety

logger = logging.getLogger(__name__)


DENTAL_SYSTEM_PROMPT = """You are HeyJarvis, a helpful AI dental concierge assistant.
You help patients with:
- Booking and rescheduling appointments
- Answering questions about dental services
- Emergency guidance
- Billing and insurance questions
- General practice information

Be friendly, professional, and concise. If a patient describes a dental emergency,
advise them to call the office immediately or go to the nearest emergency room.
Keep responses under 200 words unless more detail is needed.
"""


class AIEngine:
    """Main AI engine for HeyJarvis."""

    def __init__(self):
        self.provider = get_ai_provider()
        self.safety = AISafety()
        self._log_cache = []

    def chat(self, message: str, conversation_history: list = None, extra_instructions: str = '') -> dict:
        """Process a chat message and return an AI response."""
        start_time = time.time()
        interaction_type = 'chat'

        try:
            # Check for emergency keywords first
            emergency_keywords = ['bleeding', 'swelling', 'severe pain', 'knocked out', 'broken tooth', 'emergency']
            if any(kw in message.lower() for kw in emergency_keywords):
                result = {
                    'content': (
                        "This sounds like it may be a dental emergency. "
                        "Please call our office immediately or visit the nearest emergency room. "
                        "If this is after hours, please dial 911 for immediate assistance."
                    ),
                    'intent': 'emergency',
                    'confidence': 0.95,
                }
                self._log_interaction('emergency_detection', 0, 0, int(time.time() - start_time) * 1000)
                return result

            # Get AI response
            result = self.provider.chat(
                message=message,
                conversation_history=conversation_history,
                system_prompt=DENTAL_SYSTEM_PROMPT + (
                    f"\n\nPractice-specific guidance (follow it unless it conflicts with patient safety):\n{extra_instructions}"
                    if extra_instructions else ''
                ),
            )

            # Safety check on output
            safety_check = self.safety.check_message(result.get('content', ''))
            if not safety_check.get('safe'):
                result['content'] = "I'm not able to help with that. Please contact our office directly for assistance."
                result['intent'] = 'escalation'
                interaction_type = 'escalation'

            # Estimate token usage
            total_tokens = len(message.split()) + len(result.get('content', '').split()) * 1.3
            prompt_tokens = len(message.split())
            completion_tokens = len(result.get('content', '').split())

            self._log_interaction(
                interaction_type=interaction_type,
                prompt_tokens=int(prompt_tokens),
                completion_tokens=int(completion_tokens),
                latency_ms=int((time.time() - start_time) * 1000),
            )

            return result

        except Exception as e:
            logger.error(f"AI Engine error: {e}")
            self._log_interaction('error', 0, 0, int((time.time() - start_time) * 1000))
            return {
                'content': "I'm having trouble connecting right now. Please try again or call our office.",
                'intent': 'error',
                'confidence': 0.0,
            }

    def draft_email(self, context: dict, template: str = None) -> str:
        """Draft an email using AI."""
        start_time = time.time()
        try:
            content = self.provider.draft_email(context, template)
            total_tokens = len(str(context).split()) + len(content.split())
            self._log_interaction(
                'email_draft', total_tokens // 2, total_tokens // 2,
                int((time.time() - start_time) * 1000),
            )
            return content
        except Exception as e:
            logger.error(f"AI email draft error: {e}")
            return ""

    def classify_intent(self, message: str) -> dict:
        """Classify the intent of a message."""
        start_time = time.time()
        try:
            result = self.provider.classify_intent(message)
            self._log_interaction(
                'intent_classification',
                len(message.split()), 5,
                int((time.time() - start_time) * 1000),
            )
            return result
        except Exception as e:
            logger.error(f"AI intent classification error: {e}")
            return {'intent': 'general_inquiry', 'confidence': 0.5}

    def summarize_conversation(self, conversation_history: list) -> dict:
        """Summarize conversation and extract next best action."""
        start_time = time.time()
        try:
            result = self.provider.summarize_conversation(conversation_history)
            
            # Simple token estimate
            history_len = sum(len(str(m.get('content', '')).split()) for m in conversation_history)
            self._log_interaction(
                'summary', history_len, 50,
                int((time.time() - start_time) * 1000),
            )
            return result
        except Exception as e:
            logger.error(f"AI summarize conversation error: {e}")
            return {
                'summary': 'Summary unavailable.',
                'next_best_action': 'Review conversation manually.'
            }

    def _log_interaction(self, interaction_type, prompt_tokens, completion_tokens, latency_ms):
        """Log an AI interaction for cost tracking."""
        try:
            AIInteractionLog.objects.create(
                provider=self.provider.get_provider_name(),
                model=self.provider.get_model_name(),
                interaction_type=interaction_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=latency_ms,
            )
        except Exception:
            pass  # Don't fail the request if logging fails
