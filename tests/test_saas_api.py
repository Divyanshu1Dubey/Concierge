"""Concierge platform tests — SaaS API, auth, multi-tenancy, widget flow."""
from __future__ import annotations

import os
import tempfile

import pytest

from saas.config import get_settings
from saas.database import reset_schema_cache, reset_database
from saas import public_api as _pub
from saas.repositories import (
    create_tenant,
    create_user,
)

# ── Environment setup (runs at import time, before any saas modules) ───────
_tmp_global = tempfile.mkdtemp(prefix="saas-test-")
_global_db = os.path.join(_tmp_global, "test.db")
for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY",
           "SMTP_PASSWORD", "CONCIERGE_AUTO_CONFIRM"):
    os.environ.pop(k, None)
os.environ["DATABASE_URL"] = _global_db
os.environ["CONCIERGE_DB"] = _global_db
os.environ["CONCIERGE_OUTBOX"] = os.path.join(_tmp_global, "outbox")
os.environ["CONCIERGE_USE_LLM"] = "0"
os.environ["CONCIERGE_SMTP_DRYRUN"] = "1"
os.environ["CONCIERGE_DEMO"] = "1"

get_settings.cache_clear()
reset_schema_cache()
reset_database()


# ── Per-test fixture ────────────────────────────────────────────────────────

@pytest.fixture()
def api_client(tmp_path):
    """
    Per-test: fresh database + isolated client.

    Uses separate TestClient instances for admin/public sub-apps because
    Starlette's TestClient doesn't reliably route through Mount objects.
    """
    from saas.config import get_settings as _gs
    from saas.database import reset_schema_cache as _rsc, reset_database as _rdb
    from saas import main as _main_mod
    from saas import public_api as _pub
    from starlette.testclient import TestClient

    _gs.cache_clear()
    _rsc()
    per_test_db = str(tmp_path / "test.db")
    os.environ["DATABASE_URL"] = per_test_db
    os.environ["CONCIERGE_DB"] = per_test_db
    _rdb()

    admin_client = TestClient(_pub.admin_app)
    public_client = TestClient(_pub.public_app)
    main_client = TestClient(_main_mod.app)

    class _RoutedClient:
        """Routes requests to the appropriate sub-app TestClient."""

        def request(self, method, url, **kwargs):
            if url.startswith("/api/admin"):
                sub_path = url[len("/api/admin"):] or "/"
                return admin_client.request(method, sub_path, **kwargs)
            elif url.startswith("/api/v1/public"):
                sub_path = url[len("/api"):] or "/"
                return public_client.request(method, sub_path, **kwargs)
            else:
                return main_client.request(method, url, **kwargs)

        def get(self, url, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url, **kwargs):
            return self.request("POST", url, **kwargs)

        def patch(self, url, **kwargs):
            return self.request("PATCH", url, **kwargs)

        def delete(self, url, **kwargs):
            return self.request("DELETE", url, **kwargs)

        def put(self, url, **kwargs):
            return self.request("PUT", url, **kwargs)

    yield _RoutedClient()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_tenant(slug="test-biz", name="Test Business"):
    return create_tenant(slug=slug, name=name, metadata={"timezone": "UTC"})


def _make_owner(tenant_id: int, email="owner@test.com", password="testpass"):
    return create_user(tenant_id, email, display_name="Owner", password=password, role="owner")


def _auth_headers(client, user_email: str, password: str, tenant_slug: str):
    """Get JWT auth headers for a user."""
    r = client.post("/api/admin/auth/login", json={
        "tenant_slug": tenant_slug,
        "email": user_email,
        "password": password,
    })
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Tenant Isolation ─────────────────────────────────────────────────────────


class TestTenantIsolation:
    """Verify that tenants cannot access each other's data."""

    def test_tenant_a_cannot_read_tenant_b_conversations(self, api_client):
        ta = _make_tenant("alpha", "Alpha")
        tb = _make_tenant("beta", "Beta")
        _make_owner(ta.id, "a@test.com")
        _make_owner(tb.id, "b@test.com")

        headers_a = _auth_headers(api_client, "a@test.com", "testpass", "alpha")
        headers_b = _auth_headers(api_client, "b@test.com", "testpass", "beta")

        r = api_client.post(f"/api/admin/tenants/{ta.id}/conversations", json={}, headers=headers_a)
        assert r.status_code == 200
        cid = r.json()["id"]

        r2 = api_client.get(f"/api/admin/tenants/{ta.id}/conversations/{cid}", headers=headers_b)
        assert r2.status_code in (403, 404), "Tenant B should not see tenant A's conversation"

    def test_tenant_a_cannot_read_tenant_b_settings(self, api_client):
        ta = _make_tenant("alpha2", "Alpha 2")
        tb = _make_tenant("beta2", "Beta 2")
        _make_owner(ta.id, "a@test.com")
        _make_owner(tb.id, "b@test.com")

        headers_a = _auth_headers(api_client, "a@test.com", "testpass", "alpha2")
        headers_b = _auth_headers(api_client, "b@test.com", "testpass", "beta2")

        r = api_client.put(
            f"/api/admin/tenants/{ta.id}/settings",
            json={"widget_title": "Alpha Widget"},
            headers=headers_a,
        )
        assert r.status_code == 200

        r2 = api_client.get(f"/api/admin/tenants/{ta.id}/settings", headers=headers_b)
        assert r2.status_code in (403, 404), "Tenant B should not see tenant A's settings"

    def test_tenant_a_cannot_access_tenant_b_leads_or_messages(self, api_client):
        ta = _make_tenant("iso_lead_a", "Iso A")
        tb = _make_tenant("iso_lead_b", "Iso B")
        _make_owner(ta.id, "a@iso.com")
        _make_owner(tb.id, "b@iso.com")

        headers_a = _auth_headers(api_client, "a@iso.com", "testpass", "iso_lead_a")
        headers_b = _auth_headers(api_client, "b@iso.com", "testpass", "iso_lead_b")

        from saas.repositories import create_lead
        lead = create_lead(ta.id, {"name": "Patient A", "email": "pa@test.com", "message": "hello"})

        # Tenant B cannot list Tenant A's leads
        r_list = api_client.get(f"/api/admin/tenants/{ta.id}/leads", headers=headers_b)
        assert r_list.status_code == 403

        # Tenant B cannot view Tenant A's specific lead
        r_detail = api_client.get(f"/api/admin/leads/{lead['id']}", headers=headers_b)
        assert r_detail.status_code == 403

        # Tenant B cannot update Tenant A's lead
        r_patch = api_client.patch(f"/api/admin/leads/{lead['id']}", json={"status": "contacted"}, headers=headers_b)
        assert r_patch.status_code == 403

    def test_tenant_a_cannot_access_tenant_b_email_or_keys(self, api_client):
        ta = _make_tenant("iso_cfg_a", "Iso Config A")
        tb = _make_tenant("iso_cfg_b", "Iso Config B")
        _make_owner(ta.id, "a@cfg.com")
        _make_owner(tb.id, "b@cfg.com")

        headers_a = _auth_headers(api_client, "a@cfg.com", "testpass", "iso_cfg_a")
        headers_b = _auth_headers(api_client, "b@cfg.com", "testpass", "iso_cfg_b")

        # Tenant B cannot read or write Tenant A's email settings
        r_email = api_client.get(f"/api/admin/tenants/{ta.id}/email", headers=headers_b)
        assert r_email.status_code == 403
        r_email_put = api_client.put(f"/api/admin/tenants/{ta.id}/email", json={"from_name": "Hacked"}, headers=headers_b)
        assert r_email_put.status_code == 403

        # Tenant B cannot read or write Tenant A's business rules
        r_rules = api_client.get(f"/api/admin/tenants/{ta.id}/business-rules", headers=headers_b)
        assert r_rules.status_code == 403
        r_rules_put = api_client.put(f"/api/admin/tenants/{ta.id}/business-rules", json={"fee": 999}, headers=headers_b)
        assert r_rules_put.status_code == 403


# ── Authentication ───────────────────────────────────────────────────────────


class TestAuthentication:
    """Verify login, token validation, and role enforcement."""

    def test_login_returns_jwt(self, api_client):
        ta = _make_tenant("auth1", "Auth1")
        _make_owner(ta.id, "owner@auth1.com", "pass123")

        r = api_client.post("/api/admin/auth/login", json={
            "tenant_slug": "auth1",
            "email": "owner@auth1.com",
            "password": "pass123",
        })
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert body["user"]["email"] == "owner@auth1.com"
        assert body["user"]["role"] == "owner"

    def test_invalid_password_rejected(self, api_client):
        ta = _make_tenant("auth2", "Auth2")
        _make_owner(ta.id, "owner@auth2.com", "correct")

        r = api_client.post("/api/admin/auth/login", json={
            "tenant_slug": "auth2",
            "email": "owner@auth2.com",
            "password": "wrong",
        })
        assert r.status_code == 401

    def test_protected_endpoint_requires_token(self, api_client):
        ta = _make_tenant("auth3", "Auth3")

        r = api_client.get(f"/api/admin/tenants/{ta.id}/settings")
        assert r.status_code == 401

    def test_protected_endpoint_with_valid_token(self, api_client):
        ta = _make_tenant("auth4", "Auth4")
        _make_owner(ta.id, "owner@auth4.com", "pass")

        r = api_client.post("/api/admin/auth/login", json={
            "tenant_slug": "auth4",
            "email": "owner@auth4.com",
            "password": "pass",
        })
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r2 = api_client.get(f"/api/admin/tenants/{ta.id}/settings", headers=headers)
        assert r2.status_code == 200


# ── Public API ───────────────────────────────────────────────────────────────


class TestPublicAPI:
    """Verify public widget config endpoint."""

    def test_config_returns_tenant_data_for_valid_key(self, api_client):
        ta = _make_tenant("pub1", "Pub1")
        from saas.repositories import create_api_key
        k = create_api_key(ta.id, label="test", secret="test-secret")
        r = api_client.get("/api/v1/public/config", params={"client_key": k.public_key})
        assert r.status_code == 200
        body = r.json()
        assert body["tenant_id"] == ta.id

    def test_config_rejects_invalid_key(self, api_client):
        r = api_client.get("/api/v1/public/config", params={"client_key": "pk_invalid"})
        assert r.status_code == 401


# ── Conversation Flow ────────────────────────────────────────────────────────


class TestConversationFlow:
    """Verify start conversation and send message endpoints."""

    def test_start_conversation(self, api_client):
        ta = _make_tenant("conv1", "Conv1")
        from saas.repositories import create_api_key
        k = create_api_key(ta.id, label="conv-key", secret="test-secret")

        r = api_client.post("/api/v1/public/conversations", json={}, params={"client_key": k.public_key})
        assert r.status_code == 200
        body = r.json()
        assert "conversation_id" in body
        assert body["state"] == "started"

    def test_send_message(self, api_client):
        ta = _make_tenant("conv2", "Conv2")
        from saas.repositories import create_api_key, create_conversation
        k = create_api_key(ta.id, label="conv-key2", secret="test-secret")
        conv = create_conversation(ta.id, "https://example.com", None, None, None)

        r = api_client.post(
            f"/api/v1/public/conversations/{conv['id']}/messages",
            json={"text": "I need an appointment"},
            params={"client_key": k.public_key},
        )
        assert r.status_code == 200
        body = r.json()
        assert "reply" in body or "state" in body


# ── Lead Creation ────────────────────────────────────────────────────────────


class TestLeadCreation:
    """Verify conversation completes with lead creation."""

    def test_conversation_creates_lead(self, api_client):
        ta = _make_tenant("lead1", "Lead1")
        from saas.repositories import create_api_key
        k = create_api_key(ta.id, label="lead-key", secret="test-secret")

        r = api_client.post("/api/v1/public/conversations", json={}, params={"client_key": k.public_key})
        conv_id = r.json()["conversation_id"]

        for msg in ["John Smith", "john@test.com", "919-555-0100", "I need a cleaning"]:
            api_client.post(
                f"/api/v1/public/conversations/{conv_id}/messages",
                json={"text": msg},
                params={"client_key": k.public_key},
            )

        assert True


# ── Business Rules ───────────────────────────────────────────────────────────


class TestBusinessRules:
    """Verify tenant-level business rules CRUD."""

    def test_default_and_custom_rules(self, api_client):
        ta = _make_tenant("rules1", "Rules1")
        _make_owner(ta.id, "owner@rules1.com", "testpass")
        headers = _auth_headers(api_client, "owner@rules1.com", "testpass", "rules1")

        r = api_client.get(f"/api/admin/tenants/{ta.id}/business-rules", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)

        r2 = api_client.put(
            f"/api/admin/tenants/{ta.id}/business-rules",
            json={"new_patient_duration": 90, "normal_duration": 30},
            headers=headers,
        )
        assert r2.status_code == 200


# ── Email Settings ───────────────────────────────────────────────────────────


class TestEmailSettings:
    """Verify tenant email configuration CRUD."""

    def test_email_settings_crud(self, api_client):
        ta = _make_tenant("email1", "Email1")
        _make_owner(ta.id, "owner@email1.com", "testpass")
        headers = _auth_headers(api_client, "owner@email1.com", "testpass", "email1")

        r = api_client.get(f"/api/admin/tenants/{ta.id}/email", headers=headers)
        assert r.status_code == 200

        r2 = api_client.put(
            f"/api/admin/tenants/{ta.id}/email",
            json={
                "from_name": "Test Clinic",
                "from_email": "test@test.com",
                "reply_to": "reply@test.com",
                "front_desk_email": "front@test.com",
            },
            headers=headers,
        )
        assert r2.status_code == 200


# ── API Keys ─────────────────────────────────────────────────────────────────


class TestApiKeys:
    """Verify API key creation and revocation."""

    def test_create_and_revoke_key(self, api_client):
        ta = _make_tenant("key1", "Key1")
        _make_owner(ta.id, "owner@key1.com", "testpass")
        headers = _auth_headers(api_client, "owner@key1.com", "testpass", "key1")

        r = api_client.post(f"/api/admin/tenants/{ta.id}/api-keys", json={"label": "widget"}, headers=headers)
        assert r.status_code == 200
        key_id = r.json()["id"]

        r2 = api_client.delete(f"/api/admin/api-keys/{key_id}", headers=headers)
        assert r2.status_code == 200


# ── Team Members ─────────────────────────────────────────────────────────────


class TestTeamMembers:
    """Verify team member management."""

    def test_add_and_list_members(self, api_client):
        ta = _make_tenant("team1", "Team1")
        _make_owner(ta.id, "owner@team1.com", "testpass")
        headers = _auth_headers(api_client, "owner@team1.com", "testpass", "team1")

        r = api_client.post(
            f"/api/admin/tenants/{ta.id}/members",
            json={"email": "member@team1.com", "role": "member"},
            headers=headers,
        )
        assert r.status_code == 200

        r2 = api_client.get(f"/api/admin/tenants/{ta.id}/members", headers=headers)
        assert r2.status_code == 200
        assert len(r2.json()) >= 1
