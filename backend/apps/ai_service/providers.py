"""
AI provider clients.

Gemini, Groq and OpenAI are all called through their OpenAI-compatible Chat
Completions APIs; Anthropic uses its own SDK. Every call has a hard timeout and at
most one retry so a slow provider can never hold a web worker for long.
"""
import logging
from typing import List, Optional, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    pass


UNHEALTHY_SECONDS = 600


def _health_key(provider: str, model: str) -> str:
    return f'ai-unhealthy:{provider}:{model}'


def _is_unhealthy(provider: str, model: str) -> bool:
    from django.core.cache import cache
    try:
        return bool(cache.get(_health_key(provider, model)))
    except Exception:
        return False


def _mark_unhealthy(provider: str, model: str) -> None:
    # Circuit breaker: skip a failing/slow model for a while so patients are not kept waiting.
    from django.core.cache import cache
    try:
        cache.set(_health_key(provider, model), True, UNHEALTHY_SECONDS)
    except Exception:
        pass


class OpenAICompatibleProvider:
    """Any provider exposing an OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, name: str, api_key: str, base_url: str, models: List[str]):
        import openai
        self.name = name
        self.models = [m for m in models if m]
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=settings.AI_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def complete(self, messages: List[dict], max_tokens: int, temperature: float) -> Tuple[str, str, dict]:
        last_error: Optional[Exception] = None
        for model in self.models:
            if _is_unhealthy(self.name, model):
                continue
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                content = (response.choices[0].message.content or '').strip()
                if not content:
                    raise ProviderError('empty response')
                usage = getattr(response, 'usage', None)
                return content, model, {
                    'prompt_tokens': getattr(usage, 'prompt_tokens', 0) or 0,
                    'completion_tokens': getattr(usage, 'completion_tokens', 0) or 0,
                }
            except Exception as exc:  # try the next model / provider
                last_error = exc
                _mark_unhealthy(self.name, model)
                logger.warning("AI provider %s model %s failed: %s", self.name, model, type(exc).__name__)
        raise ProviderError(str(type(last_error).__name__ if last_error else 'no model configured'))


class AnthropicProvider:
    name = 'anthropic'

    def __init__(self):
        import anthropic
        self.models = [settings.ANTHROPIC_MODEL]
        self.client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            base_url=settings.ANTHROPIC_BASE_URL,
            timeout=settings.AI_TIMEOUT_SECONDS,
            max_retries=1,
        )

    def complete(self, messages: List[dict], max_tokens: int, temperature: float) -> Tuple[str, str, dict]:
        system = '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')
        convo = [m for m in messages if m['role'] != 'system']
        model = self.models[0]
        kwargs = dict(model=model, max_tokens=max_tokens, temperature=temperature, messages=convo)
        if system:
            kwargs['system'] = system
        response = self.client.messages.create(**kwargs)
        content = (response.content[0].text if response.content else '').strip()
        if not content:
            raise ProviderError('empty response')
        usage = getattr(response, 'usage', None)
        return content, model, {
            'prompt_tokens': getattr(usage, 'input_tokens', 0) or 0,
            'completion_tokens': getattr(usage, 'output_tokens', 0) or 0,
        }


def _build(name: str):
    if name == 'gemini' and settings.GEMINI_API_KEY:
        return OpenAICompatibleProvider('gemini', settings.GEMINI_API_KEY, settings.GEMINI_BASE_URL,
                                        [settings.GEMINI_MODEL, settings.GEMINI_FALLBACK_MODEL])
    if name == 'groq' and settings.GROQ_API_KEY:
        return OpenAICompatibleProvider('groq', settings.GROQ_API_KEY, settings.GROQ_BASE_URL, [settings.GROQ_MODEL])
    if name == 'openai' and settings.OPENAI_API_KEY:
        return OpenAICompatibleProvider('openai', settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL, [settings.OPENAI_MODEL])
    if name == 'anthropic' and settings.ANTHROPIC_API_KEY:
        return AnthropicProvider()
    return None


class ProviderChain:
    """Tries each configured provider in order until one answers."""

    def __init__(self, providers):
        self.providers = providers
        self.last_provider = None
        self.last_model = None

    def complete(self, messages: List[dict], max_tokens: int, temperature: float = 0.4) -> Tuple[str, dict]:
        for provider in self.providers:
            try:
                content, model, usage = provider.complete(messages, max_tokens, temperature)
                self.last_provider, self.last_model = provider.name, model
                return content, usage
            except Exception as exc:
                logger.warning("AI provider %s unavailable: %s", provider.name, type(exc).__name__)
        raise ProviderError('all AI providers failed')

    def get_provider_name(self) -> str:
        return self.last_provider or (self.providers[0].name if self.providers else 'none')

    def get_model_name(self) -> str:
        if self.last_model:
            return self.last_model
        return self.providers[0].models[0] if self.providers and self.providers[0].models else ''


def get_ai_provider() -> Optional[ProviderChain]:
    """Configured providers in priority order, or None when AI is disabled / unconfigured."""
    preferred = (settings.AI_PROVIDER or '').strip().lower()
    if preferred in ('none', 'off', 'disabled'):
        return None
    order = ['gemini', 'groq', 'openai', 'anthropic']
    if preferred in order:
        order.remove(preferred)
        order.insert(0, preferred)
    providers = []
    for name in order:
        try:
            p = _build(name)
        except Exception as exc:
            logger.warning("Could not initialise AI provider %s: %s", name, type(exc).__name__)
            p = None
        if p:
            providers.append(p)
    return ProviderChain(providers) if providers else None
