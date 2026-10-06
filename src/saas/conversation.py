"""Conversation state machine and widget-facing chat engine."""

from __future__ import annotations

import logging
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
WELCOME_BY_INTENT = {
    "appointment_request": "Sure, I can help with that. What's your name?",
    "emergency": "I'm sorry you're in pain. Let's get you help fast. What's your name?",
    "question": "I can pass this to the front desk. What's your name?",
}


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
        return {"conversation_id": context.conversation_id, "state": context.state.value, "reply": reply,
                "fields": context.fields, "turn_count": context.turn_count}

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
        return self._ask_for(next_field)

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
        lowered = body.lower()
        out: dict[str, Any] = {}
        if "my name is" in lowered:
            out["name"] = body.strip()
        elif lowered.startswith("i'm ") or lowered.startswith("i am "):
            out["name"] = body.strip()
        if "@" in body and "." in body.split("@")[-1] and "email" not in existing:
            import re
            m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", body)
            if m:
                out["email"] = m.group(0)
        if any(k in lowered for k in ["emergency", "pain", "swelling", "urgent"]):
            out["intent"] = "emergency"
        elif any(k in lowered for k in ["new patient", "first time", "never been"]):
            out["intent"] = "new_patient"
        elif any(k in lowered for k in ["cleaning", "checkup", "exam", "appointment"]):
            out["intent"] = "appointment_request"
        return out

    def _missing_required(self, fields: dict[str, Any]) -> list[str]:
        configured = [f.key for f in (self.config.get("fields") or []) if f.required]
        if configured:
            required = configured
        else:
            required = ["name", "email"]
        return [f for f in required if not fields.get(f)]
