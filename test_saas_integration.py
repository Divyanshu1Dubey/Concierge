"""Integration center tests for the HeyJarvis SaaS platform."""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pytest
from fastapi.testclient import TestClient

from saas.auth import create_access_token
from saas.database import connect, reset_schema_cache
from saas.public_api import admin_app, public_app
from saas.repositories import (
    add_domain,
    create_api_key,
    create_tenant,
    create_user,
    get_api_key_by_public,
    get_tenant,
    list_domains,
    remove_domain,
    revoke_api_key,
)
from saas.security import hash_password


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
    reset_schema_cache()
    yield


import secrets as _secrets


def _make_tenant(name="Test Tenant"):
    slug = "int-" + _secrets.token_hex(4)
    tenant = create_tenant(name=name, slug=slug)
    key = create_api_key(tenant.id, label="primary", secret="secret123")
    return tenant, key.public_key


def _auth_header(tenant_id):
    pw = hash_password("pass")
    with connect() as c:
        c.execute(
            "INSERT INTO users (tenant_id, email, display_name, hashed_password, role, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, "admin@test.com", "Admin", pw, "owner", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        )
        uid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    token = create_access_token(str(uid), tenant_id=tenant_id)
    return {"Authorization": f"Bearer {token}"}


# ── Integration Config ───────────────────────────────────────────────────────


def test_integration_status():
    tenant, pub = _make_tenant()
    client = TestClient(admin_app)
    headers = _auth_header(tenant.id)
    r = client.get(f"/tenants/{tenant.id}/integration", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "public_key" in data
    assert "widget_url" in data
    assert "concierge_url" in data
    assert "domains" in data
    assert "domain_count" in data
    assert data["public_key"] == pub
    assert tenant.slug in data["concierge_url"]


def test_add_domain():
    tenant, _ = _make_tenant()
    headers = _auth_header(tenant.id)
    client = TestClient(admin_app)
    r = client.post(
        f"/tenants/{tenant.id}/integration/domains",
        headers={**headers, "Content-Type": "application/json"},
        json={"domain": "example.com"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["domain"] == "example.com"
    assert data["tenant_id"] == tenant.id
    # duplicate rejected
    r2 = client.post(
        f"/tenants/{tenant.id}/integration/domains",
        headers={**headers, "Content-Type": "application/json"},
        json={"domain": "example.com"},
    )
    assert r2.status_code == 409


def test_remove_domain():
    tenant, _ = _make_tenant()
    d = add_domain(tenant.id, "example.com")
    headers = _auth_header(tenant.id)
    client = TestClient(admin_app)
    r = client.delete(f"/tenants/{tenant.id}/integration/domains/{d.id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    remaining = list_domains(tenant.id)
    assert len(remaining) == 0


def test_verify_domain():
    tenant, _ = _make_tenant()
    d = add_domain(tenant.id, "example.com")
    assert d.verified is False
    headers = _auth_header(tenant.id)
    client = TestClient(admin_app)
    r = client.post(f"/tenants/{tenant.id}/integration/domains/{d.id}/verify", headers=headers)
    assert r.status_code == 200
    assert r.json()["verified"] == 1


def test_regenerate_client_key():
    tenant, old_key = _make_tenant()
    headers = _auth_header(tenant.id)
    admin_client = TestClient(admin_app)
    public_client = TestClient(public_app)
    r = admin_client.post(f"/tenants/{tenant.id}/integration/regenerate-key", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "public_key" in data
    assert data["public_key"] != old_key
    # old key should be revoked
    old = get_api_key_by_public(old_key)
    assert old is None or old.revoked_at is not None
    # new key works for public config
    r2 = public_client.get("/v1/public/config", params={"client_key": data["public_key"]})
    assert r2.status_code == 200


def test_integration_test_endpoint():
    tenant, _ = _make_tenant()
    headers = _auth_header(tenant.id)
    client = TestClient(admin_app)
    # no domains
    r = client.post(f"/tenants/{tenant.id}/integration/test", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    # add domain
    add_domain(tenant.id, "example.com")
    r2 = client.post(f"/tenants/{tenant.id}/integration/test", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "ready"


def test_integration_tenant_isolation():
    t1, _ = _make_tenant("A")
    t2, _ = _make_tenant("B")
    h1 = _auth_header(t1.id)
    h2 = _auth_header(t2.id)
    client = TestClient(admin_app)
    # t1 adds domain to t1
    r = client.post(
        f"/tenants/{t1.id}/integration/domains",
        headers={**h1, "Content-Type": "application/json"},
        json={"domain": "t1.com"},
    )
    assert r.status_code == 200
    # t2 tries to access t1's integration
    r2 = client.get(f"/tenants/{t1.id}/integration", headers=h2)
    assert r2.status_code == 403
    r3 = client.post(
        f"/tenants/{t1.id}/integration/domains",
        headers={**h2, "Content-Type": "application/json"},
        json={"domain": "hack.com"},
    )
    assert r3.status_code == 403


def test_wordpress_download():
    tenant, _ = _make_tenant()
    headers = _auth_header(tenant.id)
    client = TestClient(admin_app)
    r = client.get(f"/tenants/{tenant.id}/integration/wordpress", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers.get("content-disposition", "")
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert any("heyjarvis-concierge.php" in n for n in names)
