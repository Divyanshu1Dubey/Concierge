"""Reads a free-text patient message and works out what they want.

Chain: Gemini main -> Gemini fallback -> Groq -> keyword rules. Each model
call streams, and its reasoning summary is passed to `emit` as it arrives, so
the dashboards can show the AI thinking live. The result is only *what the
patient asked for*. Durations and columns come from rules.py, never the model.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Callable

from .models import PatientRequest, RequestType, Triage

log = logging.getLogger(__name__)

Emit = Callable[..., None]  # emit(kind, **data)


def _noop(kind: str, **data) -> None:
    pass


MODEL = os.environ.get("CONCIERGE_MODEL", "gemini-3.8-flash")
FALLBACK_MODEL = os.environ.get("CONCIERGE_FALLBACK_MODEL", "gemini-3.5-flash-lite")
GROQ_MODEL = os.environ.get("CONCIERGE_GROQ_MODEL", "openai/gpt-oss-120b")
LLM_TIMEOUT_S = int(os.environ.get("CONCIERGE_LLM_TIMEOUT", "12"))  # per model call

SYSTEM = """You triage messages sent to a dental office's front desk.
Read the patient's message and fill in the fields. Pick request_type:
- emergency: pain, swelling, broken/knocked-out tooth, bleeding, lost filling or crown causing trouble, anything urgent
- new_patient: someone who has not been seen at this office and wants a visit
- existing_patient: a returning patient booking a cleaning, treatment, or follow-up
- reschedule: wants to move an existing appointment
- cancel: wants to cancel an existing appointment
- question: anything else (billing, insurance, hours, financing) with no booking request
If it is unclear whether they are new, choose new_patient only when they say so or it is clearly a first visit; otherwise existing_patient.
Emergency wins over every other type.
Use null for anything the message does not state. Do not invent names, emails, phone numbers, or times."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "request_type": {"type": "string", "enum": [t.value for t in RequestType]},
        "patient_name": {"type": ["string", "null"]},
        "patient_email": {"type": ["string", "null"]},
        "patient_phone": {"type": ["string", "null"]},
        "preferred_times": {"type": ["string", "null"]},
        "reason": {"type": "string"},
        "asked_about_cost_or_financing": {"type": "boolean"},
    },
    "required": [
        "request_type", "patient_name", "patient_email", "patient_phone",
        "preferred_times", "reason", "asked_about_cost_or_financing",
    ],
    "additionalProperties": False,
}


def _llm_chain():
    """(provider, model, attempt) in fallback order. Groq only if GROQ_API_KEY is set."""
    for model in dict.fromkeys(m for m in (MODEL, FALLBACK_MODEL) if m):
        yield "gemini", model, lambda req, emit, model=model: _triage_llm(req, model, emit=emit)
    if os.environ.get("GROQ_API_KEY"):
        yield "groq", GROQ_MODEL, lambda req, emit: _triage_groq(req, emit=emit)


def triage(req: PatientRequest, *, use_llm: bool | None = None, emit: Emit = _noop) -> Triage:
    if use_llm is None:
        use_llm = os.environ.get("CONCIERGE_USE_LLM", "1") != "0"
    result = None
    if use_llm:
        for provider, model, attempt in _llm_chain():
            emit("attempt", provider=provider, model=model)
            started = time.perf_counter()
            try:
                result = attempt(req, emit)
            except Exception as e:  # never lose a request because a model call failed
                reason = str(e).split(".")[0][:160]
                log.warning("triage failed on %s:%s (%s)", provider, model, reason)
                emit("fail", provider=provider, model=model, reason=reason, ms=_ms(started))
                continue
            if result is not None:
                emit("success", provider=provider, model=model, ms=_ms(started))
                result = result.model_copy(update={"model": model})
                break
            emit("fail", provider=provider, model=model, reason="no usable answer", ms=_ms(started))
    if result is None:
        emit("attempt", provider="keywords", model="keyword rules")
        result = _triage_heuristic(req)
        emit("success", provider="keywords", model="keyword rules", ms=0)
    # Form fields the patient typed beat anything extracted from the message.
    return result.model_copy(update={
        "patient_name": req.name or result.patient_name,
        "patient_email": req.email or result.patient_email,
        "patient_phone": req.phone or result.patient_phone,
    })


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _user_prompt(req: PatientRequest) -> str:
    return f"<patient_message>\n{req.message}\n</patient_message>"


def _triage_llm(req: PatientRequest, model: str = MODEL, *, emit: Emit = _noop) -> Triage | None:
    from google import genai
    from google.genai import types

    # One attempt per model: our own chain is the retry, so an overloaded
    # model hands off quickly instead of the SDK backing off for ~10s.
    client = genai.Client(http_options=types.HttpOptions(
        timeout=LLM_TIMEOUT_S * 1000, retry_options=types.HttpRetryOptions(attempts=1),
    ))  # reads GEMINI_API_KEY
    stream = client.models.generate_content_stream(
        model=model,
        contents=_user_prompt(req),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_json_schema=_SCHEMA,
            thinking_config=types.ThinkingConfig(include_thoughts=True, thinking_level=types.ThinkingLevel.LOW),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
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
    if finish not in (None, types.FinishReason.STOP) or not text:
        log.warning("Gemini %s stopped with %s", model, finish)
        return None
    return Triage.model_validate({**json.loads(text), "triaged_by": "gemini"})


def _triage_groq(req: PatientRequest, *, emit: Emit = _noop) -> Triage | None:
    from groq import Groq

    client = Groq(timeout=LLM_TIMEOUT_S, max_retries=0)  # reads GROQ_API_KEY
    stream = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": _user_prompt(req)}],
        response_format={"type": "json_schema", "json_schema": {"name": "triage", "strict": True, "schema": _SCHEMA}},
        include_reasoning=True,
        stream=True,
    )
    text, finish = "", None
    for chunk in stream:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        finish = choice.finish_reason or finish
        if choice.delta.reasoning:
            emit("thought", text=choice.delta.reasoning)
        if choice.delta.content:
            text += choice.delta.content
            emit("answer", text=choice.delta.content)
    if finish != "stop" or not text:
        log.warning("Groq triage stopped with %s", finish)
        return None
    return Triage.model_validate({**json.loads(text), "triaged_by": "groq"})


# --- Keyword fallback -------------------------------------------------------

_EMERGENCY = re.compile(
    r"\b(pain|hurts?|hurting|ache|aching|swell|swollen|swelling|bleed|bleeding|broke|broken|"
    r"cracked|chipped|knocked|abscess|infect|emergency|urgent|asap|throbbing|fell out)\b", re.I)
_CANCEL = re.compile(r"\bcancel", re.I)
_RESCHEDULE = re.compile(
    r"\breschedul|\b(move|push|change|bump|switch)\b.{0,25}\b(appointment|appt|cleaning|visit|checkup|exam)\b", re.I)
_NEW = re.compile(r"\b(new patient|first (visit|time|appointment)|never been|haven't been (there|seen)|just moved)\b", re.I)
_BOOK = re.compile(r"\b(book|schedule|appointment|appt|cleaning|check ?up|come in|visit|exam)\b", re.I)
_MONEY = re.compile(r"\b(cost|price|how much|financ\w*|payment plan|cherry|care ?credit|afford|insurance)\b", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_TIMES = re.compile(
    r"\b((mon|tues|wednes|thurs|fri|satur|sun)days?|weekdays?|weekends?|mornings?|afternoons?|evenings?|"
    r"today|tomorrow|next week)\b[^.!?\n]{0,30}", re.I)


def _triage_heuristic(req: PatientRequest) -> Triage:
    msg = req.message
    if _EMERGENCY.search(msg):
        kind = RequestType.EMERGENCY
    elif _CANCEL.search(msg):
        kind = RequestType.CANCEL
    elif _RESCHEDULE.search(msg):
        kind = RequestType.RESCHEDULE
    elif _NEW.search(msg):
        kind = RequestType.NEW_PATIENT
    elif _BOOK.search(msg):
        kind = RequestType.EXISTING_PATIENT
    else:
        kind = RequestType.QUESTION
    email = _EMAIL.search(msg)
    phone = _PHONE.search(msg)
    times = _TIMES.search(msg)
    first_line = msg.strip().splitlines()[0]
    return Triage(
        request_type=kind,
        patient_email=email.group(0) if email else None,
        patient_phone=phone.group(0) if phone else None,
        preferred_times=times.group(0).strip() if times else None,
        reason=first_line[:120],
        asked_about_cost_or_financing=bool(_MONEY.search(msg)),
        triaged_by="heuristic",
    )
