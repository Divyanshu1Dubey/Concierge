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
            "DELETE FROM analytics_events",
            "DELETE FROM api_keys",
            "DELETE FROM domains",
            "DELETE FROM tenant_settings",
            "DELETE FROM messages",
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


def _make_tenant(name="Test Tenant", slug="test"):
    tenant = create_tenant(name=name, slug=slug)
    key = create_api_key(tenant.id, label="default", secret="secret123")
    return tenant, key.public_key


def test_tenant_creation():
    tenant, pub = _make_tenant()
    assert tenant.id is not None
    same = get_tenant_by_slug("test")
    assert same.id == tenant.id
    assert get_tenant_by_slug("missing") is None


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
