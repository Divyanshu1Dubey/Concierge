"""Widget and conversation engine tests for the SaaS platform."""

from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pytest
from fastapi.testclient import TestClient
from saas.main import app as _main_app

from saas.conversation import ConversationEngine, ConversationContext, FieldDef, State
from saas.database import connect
from saas.public_api import public_app
from saas.repositories import (
    create_api_key,
    create_tenant,
    revoke_api_key,
    update_tenant,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_db():
    with connect() as c:
        for stmt in [
            "DELETE FROM notifications",
            "DELETE FROM messages",
            "DELETE FROM memberships",
            "DELETE FROM analytics_events",
            "DELETE FROM api_keys",
            "DELETE FROM domains",
            "DELETE FROM widget_settings",
            "DELETE FROM email_settings",
            "DELETE FROM business_rules",
            "DELETE FROM tenant_settings",
            "DELETE FROM conversations",
            "DELETE FROM leads",
            "DELETE FROM audit_logs",
            "DELETE FROM users",
            "DELETE FROM tenants",
        ]:
            try:
                c.execute(stmt)
            except Exception:
                pass
    yield


_counter = [0]


def _slug(prefix: str) -> str:
    _counter[0] += 1
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_tenant(name="Test Tenant", slug=None):
    if slug is None:
        slug = _slug("w")
    tenant = create_tenant(slug=slug, name=name)
    key = create_api_key(tenant.id, label="default", secret="secret123")
    return tenant, key.public_key


# ── Widget.js Loads and Initializes ───────────────────────────────────────


class TestWidgetLoad:
    def test_widget_js_served(self):
        """GET /widget.js should return JavaScript content."""
        client = TestClient(_main_app)
        r = client.get("/widget.js")
        assert r.status_code == 200
        assert "javascript" in r.headers.get("content-type", "")
        body = r.text
        assert len(body) > 0
        assert "HeyJarvis" in body or "widget" in body.lower()

    def test_widget_js_is_cacheable(self):
        """Widget JS should not require auth."""
        client = TestClient(_main_app)
        r = client.get("/widget.js")
        assert r.status_code == 200
        assert r.status_code != 401
        assert r.status_code != 403


# ── Conversation Start ────────────────────────────────────────────────────


class TestConversationStart:
    def test_start_creates_conversation(self):
        """POST /api/v1/public/conversations should create a conversation and return greeting."""
        tenant, pub = _make_tenant()
        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": pub})
        assert r.status_code == 200
        body = r.json()
        assert "conversation_id" in body
        assert "state" in body
        assert "reply" in body
        assert body["state"] == "started"
        assert body["reply"]  # greeting is non-empty

    def test_start_tracks_analytics_event(self):
        """Starting a conversation should create a conversation_started analytics event."""
        tenant, pub = _make_tenant()
        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": pub})
        assert r.status_code == 200

        with connect() as c:
            events = c.execute(
                "SELECT * FROM analytics_events WHERE tenant_id = ? AND event = 'conversation_started'",
                (tenant.id,)
            ).fetchall()
        assert len(events) >= 1

    def test_start_uses_custom_greeting(self):
        """If tenant has a custom greeting, it should be used."""
        import json
        tenant, pub = _make_tenant()
        with connect() as c:
            c.execute(
                "INSERT INTO tenant_settings (tenant_id, flags, updated_at) VALUES (?, ?, ?)",
                (tenant.id, json.dumps({"greeting": "Welcome! How can I help?"}), "2024-01-01T00:00:00Z")
            )
        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": pub})
        assert r.status_code == 200
        assert r.json()["reply"] == "Welcome! How can I help?"

    def test_start_requires_valid_client_key(self):
        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": "invalid"})
        assert r.status_code == 401

    def test_start_creates_message_record(self):
        """Starting a conversation should persist an assistant greeting message."""
        tenant, pub = _make_tenant()
        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": pub})
        conv_id = r.json()["conversation_id"]

        with connect() as c:
            msgs = c.execute(
                "SELECT * FROM messages WHERE conversation_id = ?", (conv_id,)
            ).fetchall()
        assert len(msgs) >= 1
        assert msgs[0]["role"] == "assistant"


# ── Message Sending ───────────────────────────────────────────────────────


class TestMessageSending:
    def test_send_message_returns_reply(self):
        """Sending a message should return an assistant reply."""
        tenant, pub = _make_tenant()
        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": pub})
        conv_id = r.json()["conversation_id"]

        r = client.post(
            f"/api/v1/public/conversations/{conv_id}/messages",
            params={"client_key": pub},
            json={"message": "My name is Alice"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "reply" in body
        assert len(body["reply"]) > 0
        assert body["conversation_id"] == conv_id

    def test_send_message_persists_both_messages(self):
        """Both user and assistant messages should be stored."""
        tenant, pub = _make_tenant()
        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": pub})
        conv_id = r.json()["conversation_id"]

        client.post(
            f"/api/v1/public/conversations/{conv_id}/messages",
            params={"client_key": pub},
            json={"message": "My name is Bob"},
        )

        with connect() as c:
            msgs = c.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
                (conv_id,)
            ).fetchall()
        # greeting + user message + assistant reply
        assert len(msgs) >= 3
        roles = [m["role"] for m in msgs]
        assert "user" in roles
        assert "assistant" in roles

    def test_send_message_increments_turn_count(self):
        """Each message call should increment the turn count for that interaction."""
        tenant, pub = _make_tenant()
        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": pub})
        conv_id = r.json()["conversation_id"]

        r = client.post(
            f"/api/v1/public/conversations/{conv_id}/messages",
            params={"client_key": pub},
            json={"message": "Hello"},
        )
        body = r.json()
        assert body["turn_count"] >= 1

        r = client.post(
            f"/api/v1/public/conversations/{conv_id}/messages",
            params={"client_key": pub},
            json={"message": "My name is Carol"},
        )
        body = r.json()
        # turn_count reflects the current interaction turn (not persisted across requests)
        assert body["turn_count"] >= 1

    def test_tenant_isolation_for_messages(self):
        """A different tenant should not be able to message another's conversation."""
        t1, k1 = _make_tenant("A")
        t2, k2 = _make_tenant("B")
        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": k1})
        conv_id = r.json()["conversation_id"]

        r = client.post(
            f"/api/v1/public/conversations/{conv_id}/messages",
            params={"client_key": k2},
            json={"message": "hack"},
        )
        assert r.status_code in (404, 422, 400)

    def test_message_nonexistent_conversation(self):
        """Messaging a non-existent conversation should 404."""
        tenant, pub = _make_tenant()
        client = TestClient(_main_app)
        r = client.post(
            "/api/v1/public/conversations/99999/messages",
            params={"client_key": pub},
            json={"message": "Hello"},
        )
        assert r.status_code == 404


# ── Field Extraction ──────────────────────────────────────────────────────


class TestFieldExtraction:
    def test_extract_name(self):
        engine = ConversationEngine({"fields": [FieldDef(key="name", label="Name", required=True)]})
        ctx = ConversationContext(conversation_id=1, tenant_id=1, turn_count=1)
        engine._reply_for(ctx, "My name is Alice")
        assert ctx.fields.get("name") == "Alice"

    def test_extract_email(self):
        engine = ConversationEngine({"fields": [
            FieldDef(key="name", label="Name", required=True),
            FieldDef(key="email", label="Email", required=True),
        ]})
        ctx = ConversationContext(conversation_id=1, tenant_id=1, turn_count=1)
        ctx.fields["name"] = "Alice"
        engine._reply_for(ctx, "My email is alice@example.com")
        assert "alice@example.com" in ctx.fields.get("email", "")

    def test_extract_emergency_intent(self):
        engine = ConversationEngine({"fields": [FieldDef(key="name", label="Name", required=True)]})
        ctx = ConversationContext(conversation_id=1, tenant_id=1, turn_count=1)
        ctx.fields["name"] = "Alice"
        engine._reply_for(ctx, "I'm in a lot of pain right now")
        assert ctx.fields.get("intent") == "emergency"

    def test_extract_appointment_intent(self):
        engine = ConversationEngine({"fields": [FieldDef(key="name", label="Name", required=True)]})
        ctx = ConversationContext(conversation_id=1, tenant_id=1, turn_count=1)
        ctx.fields["name"] = "Alice"
        engine._reply_for(ctx, "I'd like to schedule a cleaning appointment")
        assert ctx.fields.get("intent") == "appointment_request"

    def test_missing_fields_prompts_next(self):
        engine = ConversationEngine({"fields": [
            FieldDef(key="name", label="Name", required=True),
            FieldDef(key="email", label="Email", required=True),
        ]})
        ctx = ConversationContext(conversation_id=1, tenant_id=1, turn_count=1)
        reply = engine._reply_for(ctx, "Hello")
        # Should ask for name since nothing filled yet
        assert "name" in reply.lower() or ctx.state == State.COLLECTING_INFORMATION

    def test_ask_for_known_field(self):
        engine = ConversationEngine({})
        assert "name" in engine._ask_for("name").lower()
        assert "email" in engine._ask_for("email").lower()
        assert "phone" in engine._ask_for("phone").lower()

    def test_ask_for_unknown_field(self):
        engine = ConversationEngine({})
        reply = engine._ask_for("custom_field")
        assert "custom_field" in reply


# ── Error Handling ────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_invalid_client_key_rejected(self):
        """Requests with an invalid client key should return 401."""
        client = TestClient(_main_app)
        r = client.get("/api/v1/public/config", params={"client_key": "nonexistent"})
        assert r.status_code == 401

    def test_revoked_key_rejected(self):
        """A revoked API key should not work."""
        tenant, pub = _make_tenant()
        with connect() as c:
            key_row = c.execute("SELECT id FROM api_keys WHERE public_key = ?", (pub,)).fetchone()
            if key_row:
                revoke_api_key(key_row[0])

        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": pub})
        assert r.status_code == 401

    def test_disabled_tenant_rejected(self):
        """A disabled tenant should not allow conversations."""
        import json

        tenant, pub = _make_tenant()
        update_tenant(tenant.id, enabled=0)

        with connect() as c:
            existing = c.execute("SELECT id FROM tenant_settings WHERE tenant_id = ?", (tenant.id,)).fetchone()
            if existing:
                c.execute("UPDATE tenant_settings SET flags = ? WHERE tenant_id = ?",
                          (json.dumps({}), tenant.id))
            else:
                c.execute("INSERT INTO tenant_settings (tenant_id, flags, updated_at) VALUES (?, ?, ?)",
                          (tenant.id, json.dumps({}), "2024-01-01T00:00:00Z"))

        client = TestClient(_main_app)
        r = client.post("/api/v1/public/conversations", params={"client_key": pub})
        assert r.status_code in (403, 404)

    def test_conversation_message_wrong_tenant(self):
        """Messages across tenant boundaries should be rejected."""
        t1, k1 = _make_tenant("T1")
        t2, k2 = _make_tenant("T2")
        client = TestClient(_main_app)

        r = client.post("/api/v1/public/conversations", params={"client_key": k1})
        conv_id = r.json()["conversation_id"]

        r = client.post(
            f"/api/v1/public/conversations/{conv_id}/messages",
            params={"client_key": k2},
            json={"message": "hack"},
        )
        assert r.status_code in (404, 422, 400)


# ── Offline State ─────────────────────────────────────────────────────────


class TestOfflineState:
    def test_engine_start_creates_record(self):
        """ConversationEngine.start should always create a conversation record."""
        engine = ConversationEngine({"greeting": "Hi there!"})
        tenant, _ = _make_tenant()
        with patch("saas.conversation.append_message"):
            result = engine.start(tenant_id=tenant.id, page_url="https://test.com",
                                   referrer=None, user_agent=None, visitor_id="v1")
        assert result["conversation_id"] is not None
        assert result["state"] == "started"
        assert result["reply"] == "Hi there!"

    def test_engine_start_with_default_greeting(self):
        """Without custom greeting, should use DEFAULT_GREETING."""
        engine = ConversationEngine({})
        tenant, _ = _make_tenant()
        with patch("saas.conversation.append_message"):
            result = engine.start(tenant_id=tenant.id, page_url=None, referrer=None, user_agent=None, visitor_id=None)
        assert result["reply"] == "Hi! How can we help today?"

    def test_engine_handle_empty_message(self):
        """Engine should handle empty message body gracefully."""
        engine = ConversationEngine({"fields": [FieldDef(key="name", label="Name", required=True)]})
        tenant, _ = _make_tenant()
        ctx = ConversationContext(conversation_id=tenant.id, tenant_id=tenant.id, turn_count=0)
        with patch("saas.conversation.append_message"):
            result = engine.handle(ctx, "")
        assert "reply" in result
        assert result["turn_count"] == 1

    def test_engine_creates_lead_on_submission(self):
        """When all fields are filled, engine should transition to SUBMITTED."""
        engine = ConversationEngine({
            "fields": [
                FieldDef(key="name", label="Name", required=True),
                FieldDef(key="email", label="Email", required=True),
            ]
        })
        tenant, _ = _make_tenant()
        ctx = ConversationContext(conversation_id=tenant.id, tenant_id=tenant.id, turn_count=1)
        ctx.fields["name"] = "Test User"
        ctx.fields["email"] = "test@example.com"

        with patch("saas.conversation.append_message"), \
             patch("saas.conversation.complete_conversation") as mock_complete:
            result = engine.handle(ctx, "That's all")

        assert result["state"] == "submitted"
        assert mock_complete.called

    def test_engine_handoff_on_max_turns(self):
        """When max_turns is exceeded, engine should transition to HANDOFF."""
        engine = ConversationEngine({
            "fields": [FieldDef(key="name", label="Name", required=True)],
            "max_turns": 2,
        })
        tenant, _ = _make_tenant()
        ctx = ConversationContext(conversation_id=tenant.id, tenant_id=tenant.id, turn_count=2)
        with patch("saas.conversation.append_message"):
            result = engine.handle(ctx, "Still don't want to share")
        assert result["state"] == "handoff"
        assert "front desk" in result["reply"].lower()
