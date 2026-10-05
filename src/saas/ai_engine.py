"""AI engine for front-desk assistance.

Provides:
- AI reply drafting (patient-facing)
- Conversation summarization
- Next-best-action recommendation
- Time instruction parsing
- Intent/urgency classification
- Knowledge retrieval

Uses the same LLM provider chain as src/concierge/triage.py:
  Gemini -> Groq -> keyword/rules fallback.

Never exposes API keys to the browser.
All patient-facing output is reviewed/sent by a human by default.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

log = logging.getLogger(__name__)

# ── LLM settings (same pattern as triage.py) ──────────────────────────────────

MODEL = os.environ.get("CONCIERGE_MODEL", "gemini-3.8-flash")
FALLBACK_MODEL = os.environ.get("CONCIERGE_FALLBACK_MODEL", "gemini-3.5-flash-lite")
GROQ_MODEL = os.environ.get("CONCIERGE_GROQ_MODEL", "openai/gpt-oss-120b")
LLM_TIMEOUT_S = int(os.environ.get("CONCIERGE_LLM_TIMEOUT", "12"))

# ── Prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_REPLY = """You are an AI assistant for a dental front desk. Your job is to DRAFT a patient-facing reply on behalf of the front desk.

RULES:
- Write in a warm, professional tone appropriate for a dental office.
- Never invent appointments, availability, prices, or clinical advice.
- If you don't know something, say the front desk will confirm.
- Keep replies concise (2-4 short paragraphs).
- Include the practice name at the end.
- Do NOT mention that you are an AI.
- Do NOT expose internal reasoning."""

_SCHEMA_REPLY = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "sms": {"type": "string", "maxLength": 160},
        "internal_note": {"type": "string"},
        "suggested_action": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "confidence_reason": {"type": "string"},
    },
    "required": ["subject", "body", "confidence"],
    "additionalProperties": False,
}

_SYSTEM_SUMMARY = """You are a dental front desk assistant. Summarize this conversation in 1-2 sentences. Focus on what the patient wants and what the next action should be."""

_SCHEMA_SUMMARY = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "intent": {"type": "string"},
        "urgency": {"type": "string", "enum": ["normal", "high", "urgent"]},
        "next_action": {"type": "string"},
        "patient_needs": {"type": "string"},
    },
    "required": ["summary"],
    "additionalProperties": False,
}

_SYSTEM_TIME = """You are a time parsing assistant for a dental office.

Given a natural language time instruction, extract structured time data.

Rules:
- "tomorrow" means the next calendar day from today
- "today" means today
- Return date as YYYY-MM-DD
- Return time_start as HH:MM (24h)
- Return time_end as HH:MM (24h) or null
- If only a start time is mentioned, set time_end to null
- If only a day is mentioned, set time_start and time_end to null
- Confidence: "high" if unambiguous, "medium" if likely correct, "low" if unclear
- If confidence is not "high", explain why in preference_type

Examples:
"tomorrow morning" -> date=tomorrow, time_start=null, time_end=null, preference_type=morning, confidence=medium
"tomorrow at 2pm" -> date=tomorrow, time_start=14:00, time_end=null, preference_type=exact, confidence=high
"Wednesday at 10:30" -> date=next Wednesday, time_start=10:30, time_end=null, preference_type=exact, confidence=medium
"after 3pm" -> date=today, time_start=15:00, time_end=null, preference_type=after, confidence=medium
"anytime Thursday" -> date=next Thursday, time_start=null, time_end=null, preference_type=anytime, confidence=medium
"not sure, anytime" -> date=null, time_start=null, time_end=null, preference_type=unknown, confidence=low"""

_SCHEMA_TIME = {
    "type": "object",
    "properties": {
        "date": {"type": ["string", "null"], "description": "YYYY-MM-DD or null"},
        "time_start": {"type": ["string", "null"], "description": "HH:MM 24h or null"},
        "time_end": {"type": ["string", "null"], "description": "HH:MM 24h or null"},
        "preference_type": {"type": "string", "enum": ["exact", "morning", "afternoon", "after", "before", "anytime", "unknown"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "confidence_reason": {"type": "string"},
    },
    "required": ["preference_type", "confidence"],
    "additionalProperties": False,
}

_SYSTEM_CLASSIFY = """Classify this dental front desk message. Return structured classification."""

_SCHEMA_CLASSIFY = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["appointment_request", "emergency", "new_patient", "existing_patient", "reschedule", "cancel", "billing", "insurance", "financing", "question", "other"]},
        "urgency": {"type": "string", "enum": ["normal", "high", "urgent"]},
        "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative", "frustrated"]},
        "extracted_fields": {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "email": {"type": ["string", "null"]},
                "phone": {"type": ["string", "null"]},
                "preferred_date": {"type": ["string", "null"]},
                "preferred_time": {"type": ["string", "null"]},
                "service": {"type": ["string", "null"]},
                "insurance": {"type": ["string", "null"]},
                "financing": {"type": ["string", "null"]},
                "message": {"type": "string"},
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["intent", "urgency", "priority", "sentiment"],
    "additionalProperties": False,
}


# ── LLM provider abstraction ──────────────────────────────────────────────────

def _provider_chain():
    """Yield (provider_name, callable) in fallback order."""
    for model in dict.fromkeys(m for m in (MODEL, FALLBACK_MODEL) if m):
        yield "gemini", lambda req, emit, m=model: _call_gemini(req, m, emit=emit)
    if os.environ.get("GROQ_API_KEY"):
        yield "groq", lambda req, emit: _call_groq(req, emit=emit)


def _noop(kind: str, **data) -> None:
    """Default no-op stream callback."""


def _call_gemini(prompt: str, model: str, *, emit: Any = None, system: str = "", schema: dict | None = None) -> dict | None:
    if emit is None:
        emit = _noop
    from google import genai
    from google.genai import types

    cfg_kwargs: dict[str, Any] = {
        "system_instruction": system or _SYSTEM_REPLY,
        "thinking_config": types.ThinkingConfig(include_thoughts=True, thinking_level=types.ThinkingLevel.LOW),
        "automatic_function_calling_config": types.AutomaticFunctionCallingConfig(disable=True),
    }
    if schema:
        cfg_kwargs.update({
            "response_mime_type": "application/json",
            "response_json_schema": schema,
        })

    client = genai.Client(http_options=types.HttpOptions(
        timeout=LLM_TIMEOUT_S * 1000, retry_options=types.HttpRetryOptions(attempts=1),
    ))
    stream = client.models.generate_content_stream(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(**cfg_kwargs),
    )
    text, finish = "", None
    for chunk in stream:
        for cand in chunk.candidates or []:
            finish = cand.finish_reason or finish
            for part in (cand.content.parts if cand.content else None) or []:
                if not part.text:
                    continue
                if part.thought:
                    emit("thought", text=part.text)
                else:
                    text += part.text
                    emit("answer", text=part.text)
    if finish not in (None, types.FinishReason.STOP) or not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _call_groq(prompt: str, *, emit: Any = None, system: str = "", schema: dict | None = None) -> dict | None:
    if emit is None:
        emit = _noop
    from groq import Groq

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, Any] = {"model": GROQ_MODEL, "messages": messages, "timeout": LLM_TIMEOUT_S, "max_retries": 0, "stream": True}
    if schema:
        kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "response", "strict": True, "schema": schema}}

    client = Groq(**kwargs)
    text, finish = "", None
    for chunk in client.chat.completions.create(**kwargs):
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        finish = choice.finish_reason or finish
        if getattr(choice.delta, "reasoning", None):
            emit("thought", text=choice.delta.reasoning)
        if choice.delta.content:
            text += choice.delta.content
            emit("answer", text=choice.delta.content)
    if finish != "stop" or not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _noop(kind: str, **data) -> None:
    pass


def _llm(prompt: str, *, system: str = "", schema: dict | None = None) -> tuple[dict | None, str]:
    """Run the LLM chain. Returns (result, provider_name)."""
    use_llm = os.environ.get("CONCIERGE_USE_LLM", "1") != "0"
    if not use_llm:
        return None, "disabled"
    last_error = ""
    for provider, call in _provider_chain():
        try:
            result = call(prompt, emit=_noop, system=system, schema=schema)
            if result is not None:
                return result, provider
        except Exception as e:
            last_error = f"{provider}: {str(e)[:120]}"
            log.warning("LLM %s failed: %s", provider, str(e)[:120])
    return None, f"failed ({last_error})"


# ── Public AI functions ───────────────────────────────────────────────────────

def draft_reply(conversation_text: str, patient_context: dict[str, Any],
                practice_context: dict[str, Any], instruction: str = "") -> dict[str, Any]:
    """Generate an AI reply draft for the front desk."""
    patient_block = "\n".join(f"- {k}: {v or 'not provided'}" for k, v in patient_context.items())
    practice_block = "\n".join(f"- {k}: {v or 'not set'}" for k, v in practice_context.items()) if practice_context else "- Practice info available in settings"

    user_prompt = f"""{instruction or 'Draft a professional reply to this patient.'}

PATIENT CONTEXT:
{patient_block}

PRACTICE CONTEXT:
{practice_block}

CONVERSATION:
{conversation_text}

Generate a patient-facing reply, a short SMS version, and an internal note for the front desk."""

    result, provider = _llm(user_prompt, system=_SYSTEM_REPLY, schema=_SCHEMA_REPLY)
    if result is None:
        return {
            "subject": "Re: Your Request",
            "body": "Thank you for reaching out. Our front desk will get back to you shortly.",
            "sms": "Thank you for reaching out. We will respond shortly.",
            "internal_note": "LLM unavailable — manual reply needed.",
            "suggested_action": "Send manual reply",
            "confidence": "low",
            "confidence_reason": "AI unavailable, using fallback",
            "provider": provider,
        }
    result["provider"] = provider
    return result


def summarize_conversation(conversation_text: str) -> dict[str, Any]:
    """Generate a conversation summary and next action."""
    result, provider = _llm(
        f"Conversation:\n{conversation_text}\n\nSummarize this conversation.",
        system=_SYSTEM_SUMMARY,
        schema=_SCHEMA_SUMMARY,
    )
    if result is None:
        return {"summary": conversation_text[-200:], "next_action": "Review manually", "provider": provider}
    result["provider"] = provider
    return result


def parse_time_instruction(instruction: str) -> dict[str, Any]:
    """Parse natural language time instruction into structured data."""
    result, provider = _llm(
        f"Time instruction: {instruction}\n\nParse this into structured time data.",
        system=_SYSTEM_TIME,
        schema=_SCHEMA_TIME,
    )
    if result is None:
        return {
            "date": None, "time_start": None, "time_end": None,
            "preference_type": "unknown", "confidence": "low",
            "confidence_reason": "Could not parse time instruction",
            "provider": provider,
        }
    result["provider"] = provider
    return result


def classify_message(message: str, existing_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify a message: intent, urgency, extracted fields."""
    fields_block = ""
    if existing_fields:
        fields_block = "\nAlready known fields:\n" + "\n".join(f"- {k}: {v}" for k, v in existing_fields.items() if v)

    result, provider = _llm(
        f"Patient message: {message}{fields_block}\n\nClassify this message.",
        system=_SYSTEM_CLASSIFY,
        schema=_SCHEMA_CLASSIFY,
    )
    if result is None:
        return {
            "intent": "other", "urgency": "normal", "priority": "normal",
            "sentiment": "neutral", "summary": message[:100],
            "provider": provider,
        }
    result["provider"] = provider
    return result


def generate_follow_up(lead_context: dict[str, Any], hours_passed: int = 24) -> dict[str, Any]:
    """Generate a follow-up message for a lead that hasn't responded."""
    context_lines = [f"- {k}: {v or 'not provided'}" for k, v in lead_context.items()]
    user_prompt = f"""Generate a polite follow-up message. The patient has not responded for {hours_passed} hours.

Patient context:
{chr(10).join(context_lines)}

Generate a brief, friendly follow-up email and SMS."""

    return draft_reply(
        f"Follow-up needed after {hours_passed} hours of no response.",
        lead_context,
        {},
        instruction=user_prompt,
    )


def generate_confirmation(lead_context: dict[str, Any], appointment_time: str) -> dict[str, Any]:
    """Generate an appointment confirmation message."""
    instruction = f"""Generate an appointment confirmation for {appointment_time}.
Include the appointment time clearly.
Ask the patient to confirm or reschedule if needed.
Mention the cancellation policy briefly."""
    return draft_reply(
        f"Patient requested appointment at {appointment_time}. Need to confirm.",
        lead_context,
        {},
        instruction=instruction,
    )


def generate_reschedule(lead_context: dict[str, Any], new_time: str, reason: str = "") -> dict[str, Any]:
    """Generate a rescheduling message."""
    reason_line = f" Reason: {reason}" if reason else ""
    instruction = f"""Generate a polite rescheduling message. New time: {new_time}.{reason_line}
Apologize for any inconvenience. Offer to reschedule again if needed."""
    return draft_reply(
        f"Need to reschedule patient to {new_time}.{reason_line}",
        lead_context,
        {},
        instruction=instruction,
    )


def next_best_action(conversation_text: str, lead_data: dict[str, Any], conversation_state: str) -> dict[str, Any]:
    """Determine the recommended next action for a conversation."""
    prompt = f"""Given this conversation state and lead data, recommend the single best next action.

Conversation state: {conversation_state}
Lead data: {json.dumps(lead_data, default=str)}

Conversation:
{conversation_text[-1000:]}

Return: action, reason, priority (normal/high/urgent), suggested_message"""

    result, provider = _llm(prompt, system=_SYSTEM_SUMMARY, schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "One of: send_reply, request_time, confirm_appointment, reschedule, follow_up, mark_urgent, add_note, escalate, close"},
            "reason": {"type": "string"},
            "priority": {"type": "string", "enum": ["normal", "high", "urgent"]},
            "suggested_message": {"type": "string"},
        },
        "required": ["action", "reason"],
        "additionalProperties": False,
    })
    if result is None:
        return {"action": "review_manually", "reason": "AI unavailable", "priority": "normal", "provider": provider}
    result["provider"] = provider
    return result
