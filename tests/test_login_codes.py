"""Emailed one-time login codes for front desk staff."""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi.testclient import TestClient

from saas import login_codes
from saas.repositories import create_tenant, create_user


@pytest.fixture
def setup(monkeypatch):
    sent = []
    monkeypatch.setattr(login_codes, "_send", lambda to, code, name: sent.append((to, code)))
    from saas.main import app
    slug = f"otp-{uuid.uuid4().hex[:6]}"
    t = create_tenant(slug=slug, name="Bright Smiles")
    create_user(t.id, "desk@clinic.test", password=None)
    return TestClient(app), slug, sent


def _req(client, slug, email="desk@clinic.test"):
    return client.post("/api/admin/auth/code/request", json={"tenant_slug": slug, "email": email})


def _ver(client, slug, code, email="desk@clinic.test"):
    return client.post("/api/admin/auth/code/verify", json={"tenant_slug": slug, "email": email, "code": code})


def test_code_login_works_once(setup):
    client, slug, sent = setup
    assert _req(client, slug).status_code == 200
    to, code = sent[-1]
    assert to == "desk@clinic.test" and re.fullmatch(r"\d{6}", code)
    r = _ver(client, slug, code)
    assert r.status_code == 200 and r.json()["access_token"]
    assert _ver(client, slug, code).status_code == 401  # single use


def test_unknown_email_gets_same_answer_and_no_email(setup):
    client, slug, sent = setup
    r = _req(client, slug, "nobody@x.test")
    assert r.status_code == 200 and sent == []


def test_wrong_guesses_lock_the_code(setup):
    client, slug, sent = setup
    _req(client, slug)
    code = sent[-1][1]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(login_codes.MAX_ATTEMPTS):
        assert _ver(client, slug, wrong).status_code == 401
    assert _ver(client, slug, code).status_code == 401


def test_new_code_replaces_old(setup):
    client, slug, sent = setup
    _req(client, slug)
    old = sent[-1][1]
    _req(client, slug)
    new = sent[-1][1]
    if old != new:
        assert _ver(client, slug, old).status_code == 401
    assert _ver(client, slug, new).status_code == 200


def test_expired_code_rejected(setup):
    client, slug, sent = setup
    _req(client, slug)
    from saas.database import connect
    with connect() as c:
        c.execute("UPDATE login_codes SET expires_at = '2000-01-01T00:00:00'")
    assert _ver(client, slug, sent[-1][1]).status_code == 401


def test_codes_stored_hashed(setup):
    client, slug, sent = setup
    _req(client, slug)
    from saas.database import connect, rows
    with connect() as c:
        stored = rows(c, "SELECT code_hash FROM login_codes")[0]["code_hash"]
    assert sent[-1][1] not in stored
