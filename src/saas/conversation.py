"""Conversation state machine and widget-facing chat engine."""

from __future__ import annotations

import logging
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from saas.repositories import append_message, complete_conversation, create_conversation

logger = logging.getLogger(__name__)


class State(StrEnum):
    STARTED = "started"
    IDENTIFYING_INTENT = "identifying_intent"
    COLLECTING_INFORMATION = "collecting_information"
    QUALIFYING = "qualifying"
    CONFIRMING = "confirming"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    HANDOFF = "handoff"
    CLOSED = "closed"


class FieldDef(BaseModel):
    key: str
    label: str
    type: str = "text"
    required: bool = False
    ask: bool = True
    intent_only: list[str] | None = None


class ConversationContext(BaseModel):
    conversation_id: int
    tenant_id: int
    state: State = State.STARTED
    fields: dict[str, Any] = Field(default_factory=dict)
    turn_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


DEFAULT_GREETING = "Hi! How can we help today?"
DEFAULT_SERVICE_OPTIONS = ["Cleaning & checkup", "New patient visit", "Tooth pain or emergency",
                           "Cosmetic (whitening, veneers)", "Crowns, fillings or implants", "Something else"]
WELCOME_BY_INTENT = {
    "appointment_request": "Sure, I can help with that. What's your name?",
    "emergency": "I'm sorry you're in pain. Let's get you help fast. What's your name?",
    "question": "I can pass this to the front desk. What's your name?",
}


_INTAKE_KEYS = {"name", "email", "phone", "service", "intent", "preferred_date", "preferred_time", "insurance"}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_NAME_INTRO = re.compile(r"\b(?:my name is|name's|i am|i'm|im|this is)\s+([a-z][a-z'\-]+(?:\s+[a-z][a-z'\-]+)?)", re.I)
# Words that follow "I'm" / "I am" but are not names ("I'm in pain", "I am looking for ...").
_NOT_NAMES = {"in", "having", "looking", "a", "an", "not", "so", "very", "interested", "calling", "wondering", "new",
              "here", "trying", "just", "the", "sorry", "good", "fine", "ok", "okay", "still", "available", "free",
              "hoping", "needing", "experiencing", "currently", "also", "really", "on", "at", "with", "from",
              "scared", "worried", "nervous", "due", "going", "getting", "feeling", "bleeding", "swollen"}


_SERVICES = ["cleaning", "checkup", "check-up", "exam", "whitening", "crown", "filling", "implant", "root canal",
             "extraction", "veneers", "invisalign", "consult"]


def _rule_fields(body: str, asked: str | None) -> dict[str, Any]:
    text = body.strip()
    lowered = text.lower()
    out: dict[str, Any] = {}
    m = _EMAIL.search(text)
    if m:
        out["email"] = m.group(0)
    m = _PHONE.search(text)
    if m:
        out["phone"] = m.group(0).strip()
    m = _NAME_INTRO.search(text)
    if m and m.group(1).split()[0].lower() not in _NOT_NAMES:
        words = [w for w in m.group(1).split() if w.lower() not in _NOT_NAMES]
        out["name"] = " ".join(w[:1].upper() + w[1:] for w in words)
    elif asked == "name" and re.fullmatch(r"[A-Za-z][A-Za-z'\-]*(\s+[A-Za-z][A-Za-z'\-]*){0,2}", text):
        out["name"] = " ".join(w[:1].upper() + w[1:] for w in text.split())
    if any(k in lowered for k in ["emergency", "pain", "swelling", "urgent", "broken tooth", "bleeding"]):
        out["intent"] = "emergency"
    elif any(k in lowered for k in ["new patient", "first time", "never been"]):
        out["intent"] = "new_patient"
    elif any(k in lowered for k in ["cleaning", "checkup", "check-up", "exam", "appointment", "whitening", "crown",
                                    "filling", "implant", "consult"]):
        out["intent"] = "appointment_request"
    service = next((k for k in _SERVICES if k in lowered), None)
    if service:
        out["service"] = service
    if asked == "service" and "intent" not in out and not out.get("email"):
        out["service"] = text[:120]
    return out


class ConversationEngine:
    def __init__(self, tenant_config: dict[str, Any]) -> None:
        self.config = tenant_config

    def start(self, tenant_id: int, page_url: str | None, referrer: str | None, user_agent: str | None,
              visitor_id: str | None) -> dict:
        conv = create_conversation(tenant_id, page_url, referrer, user_agent, visitor_id)
        append_message(conv["id"], "assistant", self.config.get("greeting", DEFAULT_GREETING))
        return {"conversation_id": conv["id"], "state": State.STARTED.value, "reply": self.config.get("greeting", DEFAULT_GREETING)}

    def handle(self, context: ConversationContext, body: str) -> dict:
        context.turn_count += 1
        context.state = State.COLLECTING_INFORMATION
        append_message(context.conversation_id, "user", body)
        reply = self._reply_for(context, body)
        append_message(context.conversation_id, "assistant", reply)
        if context.state in (State.SUBMITTED, State.HANDOFF):
            complete_conversation(context.conversation_id, context.fields.get("_summary"))
        out = {"conversation_id": context.conversation_id, "state": context.state.value, "reply": reply,
                "fields": context.fields, "turn_count": context.turn_count}
        options = self.options_for(context.fields.get("_asked")) if context.state not in (State.SUBMITTED, State.HANDOFF) else []
        if options:
            out["options"] = options
        return out

    def _reply_for(self, context: ConversationContext, body: str) -> str:
        fields = self._extract_fields(body, context.fields)
        context.fields.update(fields)
        missing = self._missing_required(context.fields)
        if not missing:
            context.state = State.SUBMITTED
            return "Thanks, I have everything I need. Our front desk will follow up shortly."
        if context.turn_count >= self.config.get("max_turns", 8):
            context.state = State.HANDOFF
            return "Let me connect you with our front desk."
        next_field = missing[0]
        context.fields["_asked"] = next_field
        return self._ask_for(next_field)

    def options_for(self, field: str | None) -> list[str]:
        """Tap-to-answer choices shown under a question. Clinics can override via the 'service_options' setting."""
        if field != "service":
            return []
        custom = self.config.get("service_options")
        if isinstance(custom, list) and custom:
            return [str(o)[:60] for o in custom][:8]
        return list(DEFAULT_SERVICE_OPTIONS)

    def _ask_for(self, field: str) -> str:
        prompts = {
            "name": "Can I get your name?",
            "email": "What email should we use?",
            "phone": "What's the best phone number to reach you?",
            "service": "What are you looking to schedule?",
            "preferred_date": "What day works best?",
            "preferred_time": "What time of day do you prefer?",
            "message": "Anything else we should know?",
        }
        return prompts.get(field, f"Could you share your {field}?")

    def _extract_fields(self, body: str, existing: dict[str, Any]) -> dict[str, Any]:
        """Gemini reads the message first; the rules below fill anything it missed (or all of it when AI is off)."""
        asked = existing.get("_asked")
        out: dict[str, Any] = {}
        if self.config.get("ai_enabled", True):
            try:
                from saas.ai_engine import extract_intake
                out = {k: v for k, v in extract_intake(body, existing, asked).items() if k in _INTAKE_KEYS}
            except Exception:
                logger.exception("AI intake extraction failed; using rules")
        for key, value in _rule_fields(body, asked).items():
            out.setdefault(key, value)
        # A tapped choice is the patient's exact answer: store the label they picked.
        picked = next((o for o in self.options_for(asked) if o.lower() == body.strip().lower()), None)
        if picked:
            out["service"] = picked
        if out.get("email") and not _EMAIL.fullmatch(out["email"]):
            out.pop("email")
        return out

    def _missing_required(self, fields: dict[str, Any]) -> list[str]:
        configured = [f["key"] if isinstance(f, dict) else f.key for f in (self.config.get("fields") or [])
                      if (f.get("required") if isinstance(f, dict) else f.required)]
        if configured:
            required = configured
        else:
            # Ask what they need first (shown with tap-to-answer choices), then contact details.
            required = ([] if fields.get("intent") or fields.get("service") else ["service"]) + ["name", "email"]
        missing = [f for f in required if not fields.get(f)]
        return missing
