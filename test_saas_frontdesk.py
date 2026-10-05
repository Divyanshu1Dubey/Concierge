"""Tests for the Front Desk API (/fd/* routes)."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pytest
from fastapi.testclient import TestClient

from saas.database import connect, now_iso, row
from saas.public_api import frontdesk_app, admin_app
from saas.repositories import (
    create_api_key,
    create_lead,
    create_tenant,
    create_conversation,
    add_message,
    list_leads,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_db():
    with connect() as c:
        for stmt in [
            "DELETE FROM ai_drafts",
            "DELETE FROM frontdesk_tasks",
            "DELETE FROM frontdesk_notes",
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


def _slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_tenant(name="Test Tenant"):
    slug = _slug("fd")
    tenant = create_tenant(slug=slug, name=name)
    key = create_api_key(tenant.id, label="default", secret="secret123")
    return tenant, key.public_key


def _login_and_get_jwt(tenant_slug: str, email: str = "admin@test.com", password: str = "password123"):
    """Create a user, then log in via admin API to get JWT."""
    from saas.security import hash_password
    from saas.repositories import get_tenant_by_slug

    tenant = get_tenant_by_slug(tenant_slug)
    assert tenant, f"tenant {tenant_slug} not found"

    # Create user directly
    hashed = hash_password(password)
    now = now_iso()
    with connect() as c:
        c.execute(
            "INSERT INTO users (tenant_id, email, display_name, hashed_password, role, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'owner', ?, ?)",
            (tenant.id, email, "Admin", hashed, now, now),
        )

    client = TestClient(admin_app)
    r = client.post("/auth/login", json={
        "tenant_slug": tenant_slug,
        "email": email,
        "password": password,
    })
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["access_token"], tenant


def _make_lead(tenant_id, conv_id, name, email, phone=None, intent="appointment_request", service=None, urgency=None, preferred_date=None, preferred_time=None, page_url=None):
    """Helper to create a lead with the correct dict signature."""
    return create_lead(tenant_id, {
        "conversation_id": conv_id,
        "name": name,
        "email": email,
        "phone": phone,
        "intent": intent,
        "service": service,
        "urgency": urgency,
        "preferredDate": preferred_date,
        "preferredTime": preferred_time,
        "message": None,
        "conversationSummary": None,
        "source": "website_widget",
        "pageUrl": page_url,
        "status": "new",
    })


def _fd_client(api_key: str):
    """Create a TestClient."""
    return TestClient(frontdesk_app)


# ── Authentication Tests ──────────────────────────────────────────────────


class TestFDAuth:
    def test_no_auth_rejected(self):
        client = TestClient(frontdesk_app)
        r = client.get("/dashboard")
        assert r.status_code == 401

    def test_invalid_api_key_rejected(self):
        client = TestClient(frontdesk_app)
        r = client.get("/dashboard", headers={"X-API-Key": "invalid"})
        assert r.status_code == 401

    def test_api_key_accepted(self):
        _tenant, public_key = _make_tenant()
        client = TestClient(frontdesk_app)
        r = client.get("/dashboard", headers={"X-API-Key": public_key})
        assert r.status_code == 200

    def test_wrong_tenant_api_key(self):
        tenant_a, key_a = _make_tenant(name="Tenant A")
        tenant_b, key_b = _make_tenant(name="Tenant B")

        # Create a conversation for tenant B
        conv = create_conversation(tenant_b.id, visitor_id="v1", page_url="http://b.com")
        add_message(conv.id, "visitor", "Hello")

        client = TestClient(frontdesk_app)
        # Try to access tenant B's conversation with tenant A's key
        r = client.get(f"/conversations/{conv.id}", headers={"X-API-Key": key_a})
        assert r.status_code == 403


# ── Dashboard Tests ───────────────────────────────────────────────────────


class TestFDDashboard:
    def test_dashboard_returns_stats(self):
        _tenant, public_key = _make_tenant()

        client = TestClient(frontdesk_app)
        r = client.get("/dashboard", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        data = r.json()
        assert "total_conversations" in data
        assert "new_leads" in data
        assert "pending_drafts" in data
        assert "open_tasks" in data
        assert "insights" in data

    def test_dashboard_counts_match_data(self):
        tenant, public_key = _make_tenant()

        # Create a conversation + lead
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        add_message(conv.id, "visitor", "I need an appointment")
        create_lead(
            tenant.id,
            conversation_id=conv.id,
            name="Test Patient",
            email="test@test.com",
            phone="919-555-0100",
            intent="appointment_request",
            service="Cleaning",
        )

        client = TestClient(frontdesk_app)
        r = client.get("/dashboard", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        data = r.json()
        assert data["total_conversations"] == 1
        assert data["new_leads"] == 1

    def test_dashboard_tenant_scoped(self):
        tenant_a, key_a = _make_tenant(name="Tenant A")
        tenant_b, key_b = _make_tenant(name="Tenant B")

        # Create data only for tenant B
        conv_b = create_conversation(tenant_b.id, visitor_id="v_b", page_url="http://b.com")
        create_lead(tenant_b.id, conversation_id=conv_b.id, name="B Patient", email="b@test.com")

        client = TestClient(frontdesk_app)
        r = client.get("/dashboard", headers={"X-API-Key": key_a})
        assert r.status_code == 200
        data = r.json()
        assert data["total_conversations"] == 0
        assert data["new_leads"] == 0


# ── Conversation Tests ────────────────────────────────────────────────────


class TestFDConversations:
    def test_list_conversations(self):
        tenant, public_key = _make_tenant()
        conv1 = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        conv2 = create_conversation(tenant.id, visitor_id="v2", page_url="http://test.com/page2")

        client = TestClient(frontdesk_app)
        r = client.get("/conversations", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2

    def test_list_conversations_with_status_filter(self):
        tenant, public_key = _make_tenant()
        from saas.repositories import complete_conversation
        conv1 = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        conv2 = create_conversation(tenant.id, visitor_id="v2", page_url="http://test.com")
        complete_conversation(conv2.id)

        client = TestClient(frontdesk_app)
        r = client.get("/conversations?status=completed", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["status"] == "completed"

    def test_get_conversation_with_messages(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        add_message(conv.id, "visitor", "Hi, I need an appointment")
        add_message(conv.id, "concierge", "Sure, what's your name?")

        client = TestClient(frontdesk_app)
        r = client.get(f"/conversations/{conv.id}", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        data = r.json()
        assert data["visitor_id"] == "v1"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["body"] == "Hi, I need an appointment"
        assert data["messages"][1]["body"] == "Sure, what's your name?"

    def test_get_conversation_messages(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        add_message(conv.id, "visitor", "Hello")
        add_message(conv.id, "concierge", "Hi there!")

        client = TestClient(frontdesk_app)
        r = client.get(f"/conversations/{conv.id}/messages", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2

    def test_other_tenant_conversation_forbidden(self):
        tenant_a, key_a = _make_tenant(name="Tenant A")
        tenant_b, key_b = _make_tenant(name="Tenant B")
        conv_b = create_conversation(tenant_b.id, visitor_id="v1", page_url="http://b.com")

        client = TestClient(frontdesk_app)
        r = client.get(f"/conversations/{conv_b.id}", headers={"X-API-Key": key_a})
        assert r.status_code == 403

    def test_nonexistent_conversation_404(self):
        tenant, public_key = _make_tenant()
        client = TestClient(frontdesk_app)
        r = client.get("/conversations/99999", headers={"X-API-Key": public_key})
        assert r.status_code == 404


# ── Lead Tests ────────────────────────────────────────────────────────────


class TestFDLeads:
    def test_list_leads(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        create_lead(tenant.id, conversation_id=conv.id, name="Patient A", email="a@test.com", intent="appointment_request")
        create_lead(tenant.id, conversation_id=conv.id, name="Patient B", email="b@test.com", intent="emergency")

        client = TestClient(frontdesk_app)
        r = client.get("/leads", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2

    def test_list_leads_filtered_by_status(self):
        tenant, public_key = _make_tenant()
        from saas.repositories import update_lead
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead1 = create_lead(tenant.id, conversation_id=conv.id, name="A", email="a@test.com")
        lead2 = create_lead(tenant.id, conversation_id=conv.id, name="B", email="b@test.com")
        update_lead(lead2.id, status="contacted")

        client = TestClient(frontdesk_app)
        r = client.get("/leads?status=new", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "A"

    def test_get_lead_detail(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        add_message(conv.id, "visitor", "I need a cleaning")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="John Doe", email="john@test.com",
                          phone="919-555-0100", intent="appointment_request", service="Cleaning")

        client = TestClient(frontdesk_app)
        r = client.get(f"/leads/{lead.id}", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        data = r.json()
        assert data["lead"]["name"] == "John Doe"
        assert data["lead"]["email"] == "john@test.com"
        assert len(data["messages"]) == 1

    def test_update_lead_status(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="Patient", email="p@test.com")

        client = TestClient(frontdesk_app)
        r = client.patch(f"/leads/{lead.id}/status",
                        headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                        json={"status": "contacted"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # Verify in DB
        lead_data = list_leads(tenant.id)
        assert lead_data[0]["status"] == "contacted"

    def test_invalid_status_rejected(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="P", email="p@test.com")

        client = TestClient(frontdesk_app)
        r = client.patch(f"/leads/{lead.id}/status",
                        headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                        json={"status": "invalid_status"})
        assert r.status_code == 422

    def test_other_tenant_lead_forbidden(self):
        tenant_a, key_a = _make_tenant(name="Tenant A")
        tenant_b, key_b = _make_tenant(name="Tenant B")
        conv_b = create_conversation(tenant_b.id, visitor_id="v1", page_url="http://b.com")
        lead_b = create_lead(tenant_b.id, conversation_id=conv_b.id, name="B", email="b@test.com")

        client = TestClient(frontdesk_app)
        r = client.get(f"/leads/{lead_b.id}", headers={"X-API-Key": key_a})
        assert r.status_code == 404


# ── Notes Tests ───────────────────────────────────────────────────────────


class TestFDNotes:
    def test_create_and_list_notes(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="Patient", email="p@test.com")

        client = TestClient(frontdesk_app)

        # Create a note
        r = client.post("/notes",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"lead_id": lead.id, "note": "Called patient, left voicemail"})
        assert r.status_code == 201
        note = r.json()
        assert note["note"] == "Called patient, left voicemail"
        assert note["lead_id"] == lead.id

        # List notes
        r = client.get("/notes", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_list_notes_filtered_by_lead(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead1 = create_lead(tenant.id, conversation_id=conv.id, name="A", email="a@test.com")
        lead2 = create_lead(tenant.id, conversation_id=conv.id, name="B", email="b@test.com")

        client = TestClient(frontdesk_app)
        client.post("/notes", headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                   json={"lead_id": lead1.id, "note": "Note for A"})
        client.post("/notes", headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                   json={"lead_id": lead2.id, "note": "Note for B"})

        r = client.get(f"/notes?lead_id={lead1.id}", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["lead_id"] == lead1.id

    def test_empty_note_rejected(self):
        tenant, public_key = _make_tenant()
        client = TestClient(frontdesk_app)
        r = client.post("/notes", headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"note": "   "})
        assert r.status_code == 422


# ── Tasks Tests ───────────────────────────────────────────────────────────


class TestFDTasks:
    def test_create_and_list_tasks(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="Patient", email="p@test.com")

        client = TestClient(frontdesk_app)
        r = client.post("/tasks",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"title": "Call back patient", "lead_id": lead.id, "priority": "high"})
        assert r.status_code == 201
        task = r.json()
        assert task["title"] == "Call back patient"
        assert task["priority"] == "high"
        assert task["status"] == "open"

        # List tasks
        r = client.get("/tasks", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_create_task_with_due_date(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="P", email="p@test.com")

        client = TestClient(frontdesk_app)
        r = client.post("/tasks",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"title": "Follow up", "lead_id": lead.id, "due_at": "2025-12-31T17:00:00"})
        assert r.status_code == 201
        assert r.json()["due_at"] is not None

    def test_complete_task(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="P", email="p@test.com")

        client = TestClient(frontdesk_app)
        r = client.post("/tasks",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"title": "Call back", "lead_id": lead.id})
        assert r.status_code == 201
        task_id = r.json()["id"]

        # Complete it
        r = client.post(f"/tasks/{task_id}/complete", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

    def test_complete_other_tenant_task_forbidden(self):
        tenant_a, key_a = _make_tenant(name="Tenant A")
        tenant_b, key_b = _make_tenant(name="Tenant B")
        conv_b = create_conversation(tenant_b.id, visitor_id="v1", page_url="http://b.com")
        lead_b = create_lead(tenant_b.id, conversation_id=conv_b.id, name="B", email="b@test.com")

        client_b = TestClient(frontdesk_app)
        r = client_b.post("/tasks",
                         headers={"X-API-Key": key_b, "Content-Type": "application/json"},
                         json={"title": "Task B", "lead_id": lead_b.id})
        assert r.status_code == 201
        task_b_id = r.json()["id"]

        # Try to complete with tenant A
        client_a = TestClient(frontdesk_app)
        r = client_a.post(f"/tasks/{task_b_id}/complete", headers={"X-API-Key": key_a})
        assert r.status_code == 404

    def test_empty_title_rejected(self):
        tenant, public_key = _make_tenant()
        client = TestClient(frontdesk_app)
        r = client.post("/tasks", headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"title": "  "})
        assert r.status_code == 422


# ── AI Drafts Tests ───────────────────────────────────────────────────────


class TestFDDrafts:
    def test_create_and_list_drafts(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="Patient", email="p@test.com")

        client = TestClient(frontdesk_app)
        r = client.post("/drafts",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"lead_id": lead.id, "subject": "Welcome", "body": "Thank you for contacting us."})
        assert r.status_code == 201
        draft = r.json()
        assert draft["subject"] == "Welcome"
        assert draft["body"] == "Thank you for contacting us."
        assert draft["status"] == "pending"

    def test_list_drafts_filtered(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="P", email="p@test.com")

        client = TestClient(frontdesk_app)
        client.post("/drafts", headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                   json={"lead_id": lead.id, "subject": "Sent", "body": "test"})

        client2 = TestClient(frontdesk_app)
        # List all drafts
        r = client2.get("/drafts", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        assert len(r.json()) == 1


# ── Lead Reply Tests ──────────────────────────────────────────────────────


class TestFDLeadReply:
    def test_reply_to_lead_creates_note(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="Patient", email="p@test.com",
                          phone="919-555-0100")

        client = TestClient(frontdesk_app)
        r = client.post(f"/leads/{lead.id}/reply",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"body": "We have an opening at 2pm tomorrow"})
        assert r.status_code == 200

        # Check the note was created
        r2 = client.get("/notes", headers={"X-API-Key": public_key})
        notes = r2.json()
        assert len(notes) == 1
        assert "We have an opening at 2pm tomorrow" in notes[0]["note"]

    def test_reply_without_body_rejected(self):
        tenant, public_key = _make_tenant()
        conv = create_conversation(tenant.id, visitor_id="v1", page_url="http://test.com")
        lead = create_lead(tenant.id, conversation_id=conv.id, name="P", email="p@test.com")

        client = TestClient(frontdesk_app)
        r = client.post(f"/leads/{lead.id}/reply",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={})
        assert r.status_code == 422


# ── Tenant Scoping Tests ──────────────────────────────────────────────────


class TestFDTenantScoping:
    def test_tenant_a_cannot_see_tenant_b_leads(self):
        tenant_a, key_a = _make_tenant(name="Tenant A")
        tenant_b, key_b = _make_tenant(name="Tenant B")

        conv_b = create_conversation(tenant_b.id, visitor_id="v1", page_url="http://b.com")
        create_lead(tenant_b.id, conversation_id=conv_b.id, name="B Patient", email="b@test.com")

        client_a = TestClient(frontdesk_app)
        r = client_a.get("/leads", headers={"X-API-Key": key_a})
        assert r.status_code == 200
        assert len(r.json()) == 0

    def test_tenant_a_cannot_see_tenant_b_notes(self):
        tenant_a, key_a = _make_tenant(name="Tenant A")
        tenant_b, key_b = _make_tenant(name="Tenant B")

        conv_b = create_conversation(tenant_b.id, visitor_id="v1", page_url="http://b.com")
        lead_b = create_lead(tenant_b.id, conversation_id=conv_b.id, name="B", email="b@test.com")

        client_b = TestClient(frontdesk_app)
        client_b.post("/notes", headers={"X-API-Key": key_b, "Content-Type": "application/json"},
                     json={"lead_id": lead_b.id, "note": "Private note"})

        client_a = TestClient(frontdesk_app)
        r = client_a.get("/notes", headers={"X-API-Key": key_a})
        assert r.status_code == 200
        assert len(r.json()) == 0

    def test_tenant_a_cannot_see_tenant_b_tasks(self):
        tenant_a, key_a = _make_tenant(name="Tenant A")
        tenant_b, key_b = _make_tenant(name="Tenant B")

        conv_b = create_conversation(tenant_b.id, visitor_id="v1", page_url="http://b.com")
        lead_b = create_lead(tenant_b.id, conversation_id=conv_b.id, name="B", email="b@test.com")

        client_b = TestClient(frontdesk_app)
        client_b.post("/tasks", headers={"X-API-Key": key_b, "Content-Type": "application/json"},
                     json={"title": "B Task", "lead_id": lead_b.id})

        client_a = TestClient(frontdesk_app)
        r = client_a.get("/tasks", headers={"X-API-Key": key_a})
        assert r.status_code == 200
        assert len(r.json()) == 0


# ── JWT Auth Tests ────────────────────────────────────────────────────────


class TestFDJWTAuth:
    def test_jwt_login_works(self):
        slug = _slug("jwt")
        tenant = create_tenant(slug=slug, name="JWT Tenant")
        create_api_key(tenant.id, label="default", secret="secret123")

        token, tenant_obj = _login_and_get_jwt(slug)

        client = TestClient(frontdesk_app)
        r = client.get("/dashboard", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_invalid_jwt_rejected(self):
        client = TestClient(frontdesk_app)
        r = client.get("/dashboard", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401


# ── Widget Fetch (end-to-end) ─────────────────────────────────────────────


class TestFDLeadWorkflow:
    """Full workflow: conversation → lead → front desk manages it."""

    def test_full_workflow(self):
        tenant, public_key = _make_tenant(name="Raleigh Dental")

        # Step 1: Create conversation and lead (simulating widget flow)
        conv = create_conversation(tenant.id, visitor_id="visitor-1",
                                   page_url="https://raleighdental.com/appointment",
                                   referrer="https://google.com")
        add_message(conv.id, "visitor", "Hi, I'm Sarah and I need an emergency appointment tomorrow afternoon.")
        add_message(conv.id, "concierge", "I understand this is urgent. What's the best phone number to reach you?")
        add_message(conv.id, "visitor", "919-555-1234")
        add_message(conv.id, "concierge", "What email should we use?")
        add_message(conv.id, "visitor", "sarah@email.com")
        add_message(conv.id, "concierge", "Thank you Sarah, I've sent your request to our front desk.")

        lead = create_lead(
            tenant.id,
            conversation_id=conv.id,
            name="Sarah",
            email="sarah@email.com",
            phone="919-555-1234",
            intent="emergency",
            service="Emergency Appointment",
            urgency="high",
            preferred_date="tomorrow",
            preferred_time="afternoon",
            message="Emergency appointment needed",
            conversation_summary="Patient requested emergency appointment for tomorrow afternoon",
            source="website_widget",
            page_url="https://raleighdental.com/appointment",
        )

        # Step 2: Front desk sees the lead
        client = TestClient(frontdesk_app)
        r = client.get("/leads", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        leads = r.json()
        assert len(leads) == 1
        assert leads[0]["name"] == "Sarah"
        assert leads[0]["intent"] == "emergency"

        # Step 3: Front desk views lead detail with conversation
        r = client.get(f"/leads/{lead.id}", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        detail = r.json()
        assert detail["lead"]["email"] == "sarah@email.com"
        assert detail["lead"]["urgency"] == "high"
        assert len(detail["messages"]) == 6
        assert detail["conversation"]["page_url"] == "https://raleighdental.com/appointment"

        # Step 4: Front desk sees dashboard stats
        r = client.get("/dashboard", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        stats = r.json()
        assert stats["total_conversations"] == 1
        assert stats["new_leads"] == 1
        assert "emergency" in stats["top_intents"]

        # Step 5: Front desk updates lead status
        r = client.patch(f"/leads/{lead.id}/status",
                        headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                        json={"status": "contacted"})
        assert r.status_code == 200

        # Step 6: Front desk adds a note
        r = client.post("/notes",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"lead_id": lead.id, "note": "Called Sarah, confirmed 2pm slot"})
        assert r.status_code == 201

        # Step 7: Front desk creates a task
        r = client.post("/tasks",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"title": "Send confirmation email", "lead_id": lead.id, "priority": "high"})
        assert r.status_code == 201
        task_id = r.json()["id"]

        # Step 8: Front desk creates an AI draft
        r = client.post("/drafts",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"lead_id": lead.id, "subject": "Your Emergency Appointment", "body": "Hi Sarah, we have you confirmed for tomorrow at 2pm."})
        assert r.status_code == 201

        # Step 9: Complete the task
        r = client.post(f"/tasks/{task_id}/complete", headers={"X-API-Key": public_key})
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

        # Step 10: Reply to the lead
        r = client.post(f"/leads/{lead.id}/reply",
                       headers={"X-API-Key": public_key, "Content-Type": "application/json"},
                       json={"body": "Hi Sarah, we have you confirmed for tomorrow at 2pm. Please arrive 15 min early."})
        assert r.status_code == 200

        # Verify final state
        r = client.get("/dashboard", headers={"X-API-Key": public_key})
        stats = r.json()
        assert stats["contacted_leads"] == 1
        assert stats["completed_tasks"] == 1  # not in our current schema but good to check

    def test_multiple_tenants_isolated(self):
        """Each tenant only sees their own data."""
        tenant_a, key_a = _make_tenant(name="Dental A")
        tenant_b, key_b = _make_tenant(name="Clinic B")

        # Create data for both tenants
        conv_a = create_conversation(tenant_a.id, visitor_id="v_a", page_url="http://a.com")
        conv_b = create_conversation(tenant_b.id, visitor_id="v_b", page_url="http://b.com")
        lead_a = create_lead(tenant_a.id, conversation_id=conv_a.id, name="A", email="a@test.com")
        lead_b = create_lead(tenant_b.id, conversation_id=conv_b.id, name="B", email="b@test.com")

        client_a = TestClient(frontdesk_app)
        client_b = TestClient(frontdesk_app)

        # Lead A only sees A's data
        r = client_a.get("/leads", headers={"X-API-Key": key_a})
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "A"

        # Lead B only sees B's data
        r = client_b.get("/leads", headers={"X-API-Key": key_b})
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "B"

        # Stats are isolated
        r = client_a.get("/dashboard", headers={"X-API-Key": key_a})
        assert r.json()["new_leads"] == 1

        r = client_b.get("/dashboard", headers={"X-API-Key": key_b})
        assert r.json()["new_leads"] == 1
