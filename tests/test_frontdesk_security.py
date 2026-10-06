"""Front desk + admin API: authentication and tenant isolation.

Every test runs against the real mounted app (saas.main:app) so the URL
prefixes match production: /api/admin/... and /api/admin/fd/...
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from saas.repositories import (
    append_message,
    create_api_key,
    create_conversation,
    create_lead,
    create_tenant,
    create_user,
)

PASSWORD = "correct-horse-battery"


@pytest.fixture
def client():
    from saas.main import app
    return TestClient(app)


def _clinic(client, name: str, role: str = "owner") -> dict:
    """Tenant + staff user + widget key + one lead with a conversation. Returns ids and a JWT."""
    slug = f"{name.lower()}-{uuid.uuid4().hex[:6]}"
    tenant = create_tenant(slug=slug, name=name)
    email = f"desk@{slug}.test"
    create_user(tenant.id, email, password=PASSWORD, role=role)
    key = create_api_key(tenant.id, label="widget", secret="s")
    conv = create_conversation(tenant.id)
    append_message(conv["id"], "user", f"I need a cleaning at {name}")
    lead = create_lead(tenant.id, {"conversation_id": conv["id"], "name": f"{name} Patient",
                                   "email": f"patient@{slug}.test", "intent": "appointment_request"})
    r = client.post("/api/admin/auth/login", json={"tenant_slug": slug, "email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"tenant_id": tenant.id, "slug": slug, "email": email, "public_key": key.public_key,
            "conv_id": conv["id"], "lead_id": lead["id"],
            "auth": {"Authorization": f"Bearer {r.json()['access_token']}"}}


# ── Authentication ────────────────────────────────────────────────────────


def test_front_desk_requires_login(client):
    assert client.get("/api/admin/fd/leads").status_code == 401


def test_public_widget_key_cannot_read_front_desk(client):
    """The widget key is visible in page source; it must never unlock patient data."""
    a = _clinic(client, "Alpha")
    r = client.get("/api/admin/fd/leads", headers={"X-API-Key": a["public_key"]})
    assert r.status_code == 401
    r = client.get("/api/admin/fd/leads", headers={"Authorization": f"Bearer {a['public_key']}"})
    assert r.status_code == 401


def test_garbage_token_is_401_not_500(client):
    r = client.get("/api/admin/tenants/1/leads", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_wrong_password_rejected(client):
    a = _clinic(client, "Alpha")
    r = client.post("/api/admin/auth/login", json={"tenant_slug": a["slug"], "email": a["email"], "password": "nope"})
    assert r.status_code == 401


def test_user_without_password_cannot_log_in(client):
    tenant = create_tenant(slug=f"nopw-{uuid.uuid4().hex[:6]}", name="NoPw")
    create_user(tenant.id, "nopw@test.com", password=None)
    r = client.post("/api/admin/auth/login", json={"tenant_slug": tenant.slug, "email": "nopw@test.com", "password": "anything"})
    assert r.status_code == 401


def test_login_is_rate_limited(client):
    a = _clinic(client, "Alpha")
    codes = [client.post("/api/admin/auth/login",
                         json={"tenant_slug": a["slug"], "email": a["email"], "password": "x"}).status_code
             for _ in range(12)]
    assert 429 in codes


# ── Front desk tenant isolation ───────────────────────────────────────────


def test_front_desk_sees_only_own_leads(client):
    a, b = _clinic(client, "Alpha"), _clinic(client, "Beta")
    ids = {l["id"] for l in client.get("/api/admin/fd/leads", headers=a["auth"]).json()}
    assert a["lead_id"] in ids and b["lead_id"] not in ids


@pytest.mark.parametrize("path", [
    "/api/admin/fd/leads/{lead}",
    "/api/admin/fd/conversations/{conv}",
    "/api/admin/fd/conversations/{conv}/messages",
])
def test_front_desk_cannot_read_other_clinic_records(client, path):
    a, b = _clinic(client, "Alpha"), _clinic(client, "Beta")
    r = client.get(path.format(lead=b["lead_id"], conv=b["conv_id"]), headers=a["auth"])
    assert r.status_code in (403, 404)


@pytest.mark.parametrize("path", [
    "/api/admin/fd/ai/draft", "/api/admin/fd/ai/summarize", "/api/admin/fd/ai/next-action",
    "/api/admin/fd/ai/follow-up", "/api/admin/fd/ai/classify",
])
def test_front_desk_ai_cannot_read_other_clinic_lead(client, path):
    a, b = _clinic(client, "Alpha"), _clinic(client, "Beta")
    r = client.post(path, json={"lead_id": b["lead_id"]}, headers=a["auth"])
    assert r.status_code == 404


@pytest.mark.parametrize("path,body", [
    ("/api/admin/fd/notes", {"note": "x"}),
    ("/api/admin/fd/tasks", {"title": "x"}),
    ("/api/admin/fd/drafts", {"subject": "x", "body": "y"}),
])
def test_front_desk_cannot_attach_to_other_clinic_lead(client, path, body):
    a, b = _clinic(client, "Alpha"), _clinic(client, "Beta")
    r = client.post(path, json={**body, "lead_id": b["lead_id"]}, headers=a["auth"])
    assert r.status_code == 404


def test_front_desk_cannot_update_other_clinic_lead_status(client):
    a, b = _clinic(client, "Alpha"), _clinic(client, "Beta")
    r = client.patch(f"/api/admin/fd/leads/{b['lead_id']}/status", json={"status": "closed"}, headers=a["auth"])
    assert r.status_code == 404


def test_front_desk_workflow_on_own_lead(client):
    a = _clinic(client, "Alpha")
    h, lid = a["auth"], a["lead_id"]
    assert client.post("/api/admin/fd/notes", json={"note": "called, left voicemail", "lead_id": lid}, headers=h).status_code == 201
    assert client.post("/api/admin/fd/notes", json={"note": "  "}, headers=h).status_code == 422
    t = client.post("/api/admin/fd/tasks", json={"title": "Call back", "lead_id": lid}, headers=h)
    assert t.status_code == 201
    assert client.post("/api/admin/fd/tasks", json={"title": ""}, headers=h).status_code == 422
    assert client.post(f"/api/admin/fd/tasks/{t.json()['id']}/complete", headers=h).status_code == 200
    d = client.post("/api/admin/fd/drafts", json={"lead_id": lid, "subject": "Hi", "body": "Hello"}, headers=h)
    assert d.status_code == 201
    r = client.post(f"/api/admin/fd/drafts/{d.json()['id']}/send", headers=h)
    assert r.status_code == 409 and "not connected" in r.json()["detail"]  # no clinic mailbox yet
    assert client.patch(f"/api/admin/fd/leads/{lid}/status", json={"status": "contacted"}, headers=h).status_code == 200


# ── Admin tenant isolation ────────────────────────────────────────────────


@pytest.mark.parametrize("method,path", [
    ("get", "/api/admin/tenants/{t}/leads"),
    ("get", "/api/admin/tenants/{t}/conversations"),
    ("get", "/api/admin/tenants/{t}/members"),
    ("get", "/api/admin/tenants/{t}/email"),
    ("put", "/api/admin/tenants/{t}/email"),
    ("get", "/api/admin/tenants/{t}/widget"),
    ("put", "/api/admin/tenants/{t}/widget"),
    ("get", "/api/admin/tenants/{t}/analytics"),
    ("get", "/api/admin/tenants/{t}/audit"),
    ("get", "/api/admin/tenants/{t}/domains"),
    ("post", "/api/admin/tenants/{t}/domains"),
    ("post", "/api/admin/tenants/{t}/members"),
    ("post", "/api/admin/tenants/{t}/api-keys"),
    ("put", "/api/admin/tenants/{t}/business-rules"),
    ("put", "/api/admin/tenants/{t}/settings"),
    ("put", "/api/admin/tenants/{t}/templates/default"),
])
def test_admin_cannot_touch_other_clinic(client, method, path):
    a, b = _clinic(client, "Alpha"), _clinic(client, "Beta")
    kwargs = {"headers": a["auth"]}
    if method in ("put", "post"):
        kwargs["json"] = {"email": "attacker@evil.test", "role": "owner", "domain": "evil.test",
                          "from_email": "attacker@evil.test", "label": "x"}
    r = getattr(client, method)(path.format(t=b["tenant_id"]), **kwargs)
    assert r.status_code == 403


@pytest.mark.parametrize("method,path", [
    ("get", "/api/admin/leads/{lead}"),
    ("patch", "/api/admin/leads/{lead}"),
    ("get", "/api/admin/conversations/{conv}/messages"),
])
def test_admin_cannot_touch_other_clinic_by_record_id(client, method, path):
    a, b = _clinic(client, "Alpha"), _clinic(client, "Beta")
    kwargs = {"headers": a["auth"]}
    if method == "patch":
        kwargs["json"] = {"status": "closed"}
    r = getattr(client, method)(path.format(lead=b["lead_id"], conv=b["conv_id"]), **kwargs)
    assert r.status_code == 403


def test_admin_tenant_list_only_shows_own_clinic(client):
    a, b = _clinic(client, "Alpha"), _clinic(client, "Beta")
    ids = {t["id"] for t in client.get("/api/admin/tenants", headers=a["auth"]).json()}
    assert ids == {a["tenant_id"]}


def test_admin_cannot_promote_to_owner(client):
    a = _clinic(client, "Alpha", role="admin")
    r = client.post(f"/api/admin/tenants/{a['tenant_id']}/members", json={"email": "new@x.test", "role": "owner"},
                    headers=a["auth"])
    assert r.status_code == 403


# ── Public widget endpoints ───────────────────────────────────────────────


def test_public_lead_create_is_rate_limited(client):
    a = _clinic(client, "Alpha")
    codes = [client.post("/api/v1/public/leads", params={"client_key": a["public_key"]},
                         json={"name": "Spam", "email": "spam@x.test"}).status_code for _ in range(8)]
    assert codes[0] == 200 and 429 in codes


def test_production_refuses_placeholder_secrets(monkeypatch):
    from saas import main
    monkeypatch.setattr(main.settings, "app_env", "production")
    monkeypatch.setattr(main.settings, "jwt_secret", "change-me")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        main._check_production_secrets()
