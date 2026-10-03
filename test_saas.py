"""SaaS platform tests."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from fastapi.testclient import TestClient
import pytest

from saas.auth import authenticate, create_access_token, get_user_by_email, verify_password
from saas.database import connect
from saas.repositories import (
    add_domain,
    create_api_key,
    create_tenant,
    get_api_key_by_public,
    get_tenant,
    get_tenant_by_slug,
    list_domains,
    remove_domain,
    track_event,
    update_tenant,
)
from saas.security import hash_password
from saas.public_api import public_app


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


def _make_tenant(name="Test Tenant", slug=None):
    _counter[0] += 1
    if slug is None:
        slug = f"test-{_counter[0]}"
    tenant = create_tenant(name=name, slug=slug)
    key = create_api_key(tenant.id, label="default", secret="secret123")
    return tenant, key.public_key


def test_tenant_creation():
    tenant, pub = _make_tenant()
    assert tenant.id is not None
    assert tenant.slug is not None
    same = get_tenant_by_slug(tenant.slug)
    assert same.id == tenant.id
    assert get_tenant_by_slug("missing-nonexistent-slug") is None


def test_api_key_lifecycle():
    tenant, pub = _make_tenant()
    key = get_api_key_by_public(pub)
    assert key is not None
    assert key.tenant_id == tenant.id


def test_domain_workflow():
    tenant, _ = _make_tenant()
    d = add_domain(tenant.id, "example.com")
    assert d.domain == "example.com"
    assert len(list_domains(tenant.id)) == 1
    remove_domain(d.id)
    assert len(list_domains(tenant.id)) == 0


def test_enable_disable():
    tenant, _ = _make_tenant()
    t = get_tenant(tenant.id)
    assert t.enabled is True
    update_tenant(tenant.id, enabled=0)
    t = get_tenant(tenant.id)
    assert t.enabled == 0


def test_public_requires_client_key():
    client = TestClient(public_app)
    r = client.get("/api/v1/public/config")
    assert r.status_code == 422
    r = client.get("/api/v1/public/config", params={"client_key": "invalid"})
    assert r.status_code == 401


def test_public_conversation_flow():
    tenant, pub = _make_tenant()
    with connect() as c:
        r = c.execute("SELECT id FROM tenant_settings WHERE tenant_id = ?", (tenant.id,)).fetchone()
        if r:
            c.execute("UPDATE tenant_settings SET flags = json_set(flags, '$.greeting', ?) WHERE tenant_id = ?",
                      ("Hi from demo", tenant.id))
        else:
            c.execute("INSERT INTO tenant_settings (tenant_id, flags, updated_at) VALUES (?, ?, ?)",
                      (tenant.id, json.dumps({"greeting": "Hi from demo"}), "2024-01-01T00:00:00Z"))
    client = TestClient(public_app)
    r = client.get("/api/v1/public/config", params={"client_key": pub})
    assert r.status_code == 200
    assert r.json()["greeting"] == "Hi from demo"
    r = client.post("/api/v1/public/conversations", params={"client_key": pub}, json={})
    assert r.status_code == 200
    body = r.json()
    assert body["conversation_id"] is not None
    assert body["reply"] == "Hi from demo"
    r = client.post("/api/v1/public/conversations/" + str(body["conversation_id"]) + "/messages",
                    params={"client_key": pub}, json={"message": "My name is Alice"})
    assert r.status_code == 200
    assert r.json()["reply"]


def test_tenant_isolation():
    t1, k1 = _make_tenant("A", "a")
    t2, k2 = _make_tenant("B", "b")
    r1 = TestClient(public_app).post("/api/v1/public/conversations", params={"client_key": k1}, json={})
    conv_id = r1.json()["conversation_id"]
    r = TestClient(public_app).post(
        "/api/v1/public/conversations/" + str(conv_id) + "/messages",
        params={"client_key": k2},
        json={"message": "hack"},
    )
    assert r.status_code in (404, 422, 400)


def test_auth_password_flow():
    pw = hash_password("pass123")
    with connect() as c:
        c.execute(
            "INSERT INTO tenants (name, slug, enabled, created_at, updated_at) VALUES (?,?,?,?,?)",
            ("Admin", "admin", 1, "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        )
        tid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute(
            "INSERT INTO users (tenant_id, email, display_name, hashed_password, role, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tid, "admin@heyjarvis.ai", "Admin", pw, "owner", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        )
    user = authenticate(tid, "admin@heyjarvis.ai", "pass123")
    assert user is not None


def test_health_public():
    client = TestClient(public_app)
    assert client.get("/health").status_code == 200
    assert client.get("/health").json()["ok"] is True


def test_track_event_writes():
    tenant, _ = _make_tenant()
    track_event(tenant.id, "widget_loaded", {"url": "/"})
    with connect() as c:
        rows = c.execute("SELECT COUNT(1) FROM analytics_events WHERE tenant_id = ?", (tenant.id,)).fetchone()
    assert rows[0] >= 1


# ── Multi-Tenancy ──────────────────────────────────────────────────────────


def test_tenant_isolation():
    """Tenants must not see each other's data."""
    t1, key1 = _make_tenant()
    t2, key2 = _make_tenant()
    client = TestClient(public_app)
    client.post(f"/api/v1/public/conversations?client_key={key1}", json={
        "message": "What should I ask?", "visitor_name": "Alice", "visitor_email": "a@x.com"
    })
    client.post(f"/api/v1/public/conversations?client_key={key2}", json={
        "message": "Need dentist", "visitor_name": "Bob", "visitor_email": "b@y.com"
    })
    with connect() as db:
        conv1 = db.execute("SELECT id FROM conversations WHERE tenant_id=?", (t1.id,)).fetchone()
        conv2 = db.execute("SELECT id FROM conversations WHERE tenant_id=?", (t2.id,)).fetchone()
    assert conv1 is not None
    assert conv2 is not None
    # t1 should not see t2's conversations
    with connect() as db:
        bad = db.execute("SELECT COUNT(*) FROM conversations WHERE tenant_id=? AND id=?",
                         (t1.id, conv2[0])).fetchone()[0]
    assert bad == 0


def test_domain_validation():
    """Allowed domains restrict widget access."""
    from saas.repositories import add_domain, verify_domain
    t1, _ = _make_tenant()
    dom = add_domain(t1.id, "example.com")
    assert dom.tenant_id == t1.id
    assert dom.verified is False
    verify_domain(dom.id)
    from saas.database import connect
    with connect() as db:
        result = db.execute("SELECT verified FROM domains WHERE id=?", (dom.id,)).fetchone()
    assert result is not None
    assert result[0] == 1


def test_lead_lifecycle():
    """Lead is created from conversation and status can change."""
    t1, key1 = _make_tenant()
    client = TestClient(public_app)
    r = client.post(f"/api/v1/public/conversations?client_key={key1}", json={
        "message": "I need cleaning", "visitor_name": "Test", "visitor_email": "t@x.com"
    })
    assert r.status_code in (200, 201), r.text
    conv_id = r.json().get("conversationId")
    with connect() as db:
        lead = db.execute("SELECT * FROM leads WHERE conversation_id=?", (conv_id,)).fetchone()
    assert lead is not None
    lead_id = lead[0]
    from saas.repositories import update_lead_status
    update_lead_status(lead_id, "contacted")
    with connect() as db:
        updated = db.execute("SELECT status FROM leads WHERE id=?", (lead_id,)).fetchone()
    assert updated[0] == "contacted"


def test_email_settings_crud():
    """Email settings can be created and updated per tenant."""
    from saas.repositories import get_tenant_email, create_or_update_email
    t1, _ = _make_tenant()
    email_data = {
        "from_name": "Test Clinic",
        "from_email": "clinic@test.com",
        "reply_to": "reply@test.com",
        "front_desk_email": "desk@test.com",
        "backup_email": "backup@test.com",
        "smtp_host": "",
        "smtp_port": 0,
        "smtp_username": "",
        "smtp_password": "",
        "smtp_security": "tls",
        "delivery_mode": "email_draft",
    }
    create_or_update_email(t1.id, **email_data)
    loaded = get_tenant_email(t1.id)
    assert loaded is not None
    assert loaded["from_name"] == "Test Clinic"
    assert loaded["delivery_mode"] == "email_draft"


def test_api_key_generation():
    """API keys are created with public and secret parts."""
    from saas.repositories import create_api_key, get_api_key
    t1, _ = _make_tenant()
    key = create_api_key(t1.id, "Test Key", "sk_secret123")
    assert key.tenant_id == t1.id
    assert key.public_key.startswith("pk_")
    assert key.label == "Test Key"
    fetched = get_api_key(key.id)
    assert fetched is not None
    assert fetched.public_key == key.public_key


def test_business_rules_per_tenant():
    """Each tenant can have independent business rules."""
    from saas.repositories import create_or_update_business_rules, get_business_rules
    t1, _ = _make_tenant()
    rules = {
        "new_patient_minutes": 90,
        "normal_appointment_minutes": 30,
        "emergency_minutes": 60,
        "doctor_columns": 2,
        "hygiene_columns": 1,
        "confirmation_hours": 48,
        "no_show_fee": "$65",
    }
    create_or_update_business_rules(t1.id, rules)
    loaded = get_business_rules(t1.id)
    assert loaded is not None
    assert loaded["new_patient_minutes"] == 90
    assert loaded["emergency_minutes"] == 60


def test_template_variables():
    """Email templates can be created with variables."""
    from saas.repositories import get_templates, save_template
    t1, _ = _make_tenant()
    save_template(t1.id, "appointment_request", "New Request", "Patient: {{patient_name}}")
    templates = get_templates(t1.id)
    names = [t["name"] for t in templates]
    assert "appointment_request" in names
    for t in templates:
        if t["name"] == "appointment_request":
            assert "{{patient_name}}" in t["body"]
            break


def test_audit_logging():
    """Administrative actions are logged."""
    from saas.repositories import audit
    t1, _ = _make_tenant()
    audit(t1.id, 1, "settings_changed", {"key": "widget_title", "old": "Old", "new": "New"})
    with connect() as db:
        row = db.execute("SELECT * FROM audit_logs WHERE tenant_id=? AND action=?",
                         (t1.id, "settings_changed")).fetchone()
    assert row is not None
    import json
    metadata = json.loads(row[4])
    assert metadata["key"] == "widget_title"


def test_widget_loader_served():
    """Widget JS should be served at /widget.js."""
    client = TestClient(public_app)
    r = client.get("/widget.js")
    assert r.status_code == 200
    body = r.text
    assert "heyjarvis" in body.lower() or "widget" in body.lower()


def test_concierge_page_renders():
    """Hosted concierge page should render."""
    t1, _ = _make_tenant()
    client = TestClient(public_app)
    r = client.get(f"/concierge/{t1.slug}")
    assert r.status_code == 200
    assert "HeyJarvis" in r.text or "Concierge" in r.text or t1.name in r.text


def test_public_config_api():
    """Public config API returns tenant widget configuration."""
    t1, _ = _make_tenant()
    client = TestClient(public_app)
    r = client.get(f"/api/v1/public/config", params={"client_key": t1.public_key, "origin": "https://example.com"})
    assert r.status_code == 200
    data = r.json()
    assert "widget" in data


def test_admin_endpoints_require_auth():
    """Admin endpoints must reject unauthenticated requests."""
    client = TestClient(admin_app)
    r = client.get("/api/admin/tenants")
    assert r.status_code == 401


def test_admin_requires_correct_tenant():
    """Admin user cannot access other tenant's data."""
    t1, _ = _make_tenant()
    t2, _ = _make_tenant()
    from saas.repositories import create_user
    from saas.security import hash_password
    u1 = create_user(t1.id, "u1@test.com", "User One", hash_password("pass"), "owner")
    token = create_access_token(str(u1.id))
    client = TestClient(admin_app)
    r = client.get(f"/api/admin/tenants/{t2.id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
