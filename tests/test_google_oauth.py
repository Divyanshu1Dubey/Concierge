"""'Sign in with Google' for the clinic mailbox, with Google's endpoints faked."""

from __future__ import annotations

import base64
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from saas import google_oauth, mailbox
from saas.repositories import create_lead, create_tenant, create_user


class Resp:
    def __init__(self, status, data):
        self.status_code, self._data, self.text = status, data, str(data)

    def json(self):
        return self._data


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csecret")
    calls = {"token": [], "revoked": []}

    def post(url, data=None, **kw):
        if url == google_oauth.TOKEN_URL:
            calls["token"].append(data)
            if data["grant_type"] == "authorization_code":
                if data["code"] != "good-code":
                    return Resp(400, {"error": "invalid_grant"})
                return Resp(200, {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600,
                                  "scope": "openid https://mail.google.com/ email"})
            return Resp(200, {"access_token": "at-2", "expires_in": 3600})
        if url == google_oauth.REVOKE_URL:
            calls["revoked"].append(data["token"])
            return Resp(200, {})
        raise AssertionError(url)

    monkeypatch.setattr(google_oauth.httpx, "post", post)
    monkeypatch.setattr(google_oauth.httpx, "get", lambda url, **kw: Resp(200, {"email": "FrontDesk@Clinic.test"}))
    google_oauth._access_cache.clear()
    return calls


def _clinic(client, role="owner"):
    slug = f"g-{uuid.uuid4().hex[:6]}"
    t = create_tenant(slug=slug, name="Bright Smiles")
    create_user(t.id, "owner@clinic.test", password="pw-123456", role=role)
    tok = client.post("/api/admin/auth/login", json={"tenant_slug": slug, "email": "owner@clinic.test",
                                                     "password": "pw-123456"}).json()["access_token"]
    return t.id, {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def client():
    from saas.main import app
    return TestClient(app, follow_redirects=False)


def test_full_google_connect_flow(client, google):
    tid, h = _clinic(client)
    url = client.post("/api/admin/fd/mailbox/google/start", json={"from_name": "Bright Smiles Dental"}, headers=h).json()["url"]
    q = parse_qs(urlparse(url).query)
    assert q["access_type"] == ["offline"] and "https://mail.google.com/" in q["scope"][0]
    assert q["redirect_uri"][0].endswith("/oauth/google/callback")

    r = client.get("/oauth/google/callback", params={"code": "good-code", "state": q["state"][0]})
    assert r.status_code == 303 and r.headers["location"] == "/frontdesk?mailbox=connected"
    st = client.get("/api/admin/fd/mailbox", headers=h).json()
    assert st["connected"] and st["method"] == "oauth" and st["address"] == "frontdesk@clinic.test"
    assert st["from_name"] == "Bright Smiles Dental"
    row = mailbox.get_settings_row(tid)
    assert "rt-1" not in (row["oauth_refresh_enc"] or "") and row["smtp_password_enc"] is None  # encrypted, no password


def test_tampered_or_foreign_state_rejected(client, google):
    tid, h = _clinic(client)
    url = client.post("/api/admin/fd/mailbox/google/start", json={}, headers=h).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = client.get("/oauth/google/callback", params={"code": "good-code", "state": state[:-3] + "abc"})
    assert "mailbox_error" in r.headers["location"]
    assert not mailbox.is_connected(tid)


def test_user_cancel_is_reported(client, google):
    r = client.get("/oauth/google/callback", params={"error": "access_denied", "state": "x"})
    assert "cancelled" in r.headers["location"]


def test_bad_code_is_reported(client, google):
    tid, h = _clinic(client)
    state = parse_qs(urlparse(client.post("/api/admin/fd/mailbox/google/start", json={}, headers=h).json()["url"]).query)["state"][0]
    r = client.get("/oauth/google/callback", params={"code": "bad", "state": state})
    assert "mailbox_error" in r.headers["location"] and not mailbox.is_connected(tid)


def test_only_managers_can_connect(client, google):
    _, h = _clinic(client, role="viewer")
    assert client.post("/api/admin/fd/mailbox/google/start", json={}, headers=h).status_code == 403


def test_not_configured_gives_clear_error(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    _, h = _clinic(client)
    r = client.post("/api/admin/fd/mailbox/google/start", json={}, headers=h)
    assert r.status_code == 409 and "GOOGLE_CLIENT_ID" in r.json()["detail"]
    assert client.get("/api/admin/fd/mailbox", headers=h).json()["google_sign_in_available"] is False


def test_send_uses_xoauth2_with_refreshed_token(client, google, monkeypatch):
    tid, h = _clinic(client)
    mailbox.connect_gmail_oauth(tid, "frontdesk@clinic.test", "rt-1")
    seen = {}

    class SMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def auth(self, mech, fn, initial_response_ok=True): seen["mech"], seen["auth"] = mech, fn()
        def login(self, *a): raise AssertionError("password login must not be used")
        def send_message(self, msg): seen["to"] = msg["To"]

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTP)
    lead = create_lead(tid, {"name": "Pat", "email": "pat@x.test"})
    from saas.repositories import create_ai_draft
    d = create_ai_draft(tid, lead_id=lead["id"], subject="Hi", body="Hello Pat")
    mailbox.send_draft(tid, d["id"])
    assert seen["mech"] == "XOAUTH2" and seen["auth"] == "user=frontdesk@clinic.test\x01auth=Bearer at-2\x01\x01"
    assert seen["to"] == "pat@x.test"
    assert google["token"][-1]["grant_type"] == "refresh_token"


def test_disconnect_revokes_token(client, google):
    tid, h = _clinic(client)
    mailbox.connect_gmail_oauth(tid, "frontdesk@clinic.test", "rt-1")
    assert client.delete("/api/admin/fd/mailbox", headers=h).json()["connected"] is False
    assert google["revoked"] == ["rt-1"]
    assert mailbox.connected_tenants() == []
