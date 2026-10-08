"""
AI Provider implementations.
"""
from abc import ABC, abstractmethod
from django.conf import settings
from typing import Optional


class BaseAIProvider(ABC):
    """Abstract base for AI providers."""

    @abstractmethod
    def chat(self, message: str, conversation_history: list = None, system_prompt: str = None) -> dict:
        """Send a chat message and get a response."""
        pass

    @abstractmethod
    def classify_intent(self, message: str) -> dict:
        """Classify the intent of a message."""
        pass

    @abstractmethod
    def draft_email(self, context: dict, template: str = None) -> str:
        """Draft an email based on context."""
        pass

    @abstractmethod
    def summarize_conversation(self, conversation_history: list) -> dict:
        """Summarize conversation and determine next best action."""
        pass


    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        pass


class OpenAIProvider(BaseAIProvider):
    """OpenAI GPT provider."""

    def __init__(self):
        import openai
        self.client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
        self.model = settings.OPENAI_MODEL

    def chat(self, message: str, conversation_history: list = None, system_prompt: str = None) -> dict:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if conversation_history:
            for msg in conversation_history:
                role = "user" if msg['sender'] == 'user' else "assistant"
                messages.append({"role": role, "content": msg['content']})
        messages.append({"role": "user", "content": message})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=500,
        )

        content = response.choices[0].message.content
        intent = self.classify_intent(message)

        return {
            'content': content,
            'intent': intent.get('intent', 'general_chat'),
            'confidence': intent.get('confidence', 0.0),
            'provider': 'openai',
            'model': self.model,
        }

    def classify_intent(self, message: str) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Classify the intent of this dental patient message. Return JSON with 'intent' and 'confidence' (0-1). Intents: book_appointment, reschedule, cancel, emergency, general_inquiry, billing, complaint, other"},
                {"role": "user", "content": message},
            ],
            temperature=0.1,
            max_tokens=100,
        )
        import json
        try:
            return json.loads(response.choices[0].message.content)
        except Exception:
            return {'intent': 'general_inquiry', 'confidence': 0.5}

    def draft_email(self, context: dict, template: str = None) -> str:
        prompt = f"Draft a professional dental practice email based on this context: {context}"
        if template:
            prompt += f"\nUse this template style: {template}"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content

    def summarize_conversation(self, conversation_history: list) -> dict:
        history_text = "\n".join([f"{msg['sender']}: {msg['content']}" for msg in conversation_history])
        system_msg = (
            "You are an AI assistant for a dental front desk. Analyze the conversation.\n"
            "Return JSON with two keys:\n"
            "'summary': A 2-4 sentence summary of the patient's situation and request.\n"
            "'next_best_action': A 1-sentence recommendation for the front desk on what to do next."
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": history_text},
                ],
                temperature=0.2,
                max_tokens=300,
            )
            import json
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {
                'summary': 'Could not generate summary.',
                'next_best_action': 'Review conversation manually.'
            }

    def get_provider_name(self) -> str:
        return 'openai'

    def get_model_name(self) -> str:
        return self.model


class AnthropicProvider(BaseAIProvider):
    """Anthropic Claude provider."""

    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            base_url=settings.ANTHROPIC_BASE_URL,
        )
        self.model = settings.ANTHROPIC_MODEL

    def chat(self, message: str, conversation_history: list = None, system_prompt: str = None) -> dict:
        messages = []
        if conversation_history:
            for msg in conversation_history:
                role = "user" if msg['sender'] == 'user' else "assistant"
                messages.append({"role": role, "content": msg['content']})
        messages.append({"role": "user", "content": message})

        kwargs = {
            "model": self.model,
            "max_tokens": 500,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.client.messages.create(**kwargs)
        content = response.content[0].text

        return {
            'content': content,
            'intent': 'general_chat',
            'confidence': 0.8,
            'provider': 'anthropic',
            'model': self.model,
        }

    def classify_intent(self, message: str) -> dict:
        return {'intent': 'general_inquiry', 'confidence': 0.5}

    def draft_email(self, context: dict, template: str = None) -> str:
        prompt = f"Draft a professional dental practice email based on this context: {context}"
        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def summarize_conversation(self, conversation_history: list) -> dict:
        history_text = "\n".join([f"{msg['sender']}: {msg['content']}" for msg in conversation_history])
        system_msg = (
            "You are an AI assistant for a dental front desk. Analyze the conversation.\n"
            "Return JSON with two keys:\n"
            "'summary': A 2-4 sentence summary of the patient's situation and request.\n"
            "'next_best_action': A 1-sentence recommendation for the front desk on what to do next."
        )
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system=system_msg,
                messages=[{"role": "user", "content": history_text}],
            )
            import json
            return json.loads(response.content[0].text)
        except Exception:
            return {
                'summary': 'Could not generate summary.',
                'next_best_action': 'Review conversation manually.'
            }

    def get_provider_name(self) -> str:
        return 'anthropic'

    def get_model_name(self) -> str:
        return self.model


def get_ai_provider() -> BaseAIProvider:
    """Factory function to get the configured AI provider."""
    provider_name = getattr(settings, 'AI_PROVIDER', 'openai')
    providers = {
        'openai': OpenAIProvider,
        'anthropic': AnthropicProvider,
    }
    provider_class = providers.get(provider_name, OpenAIProvider)
    return provider_class()
