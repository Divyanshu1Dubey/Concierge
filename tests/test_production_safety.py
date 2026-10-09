"""Guards against demo shortcuts leaking into production."""

from __future__ import annotations

import hashlib
import pathlib
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from saas.config import get_settings
from saas.repositories import create_tenant, create_user, get_tenant_by_slug


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.delenv("CONCIERGE_DEMO", raising=False)


def test_no_demo_clinic_in_production(production):
    assert get_tenant_by_slug("raleigh-dental-demo") is None
    from saas.repositories import ensure_demo_data
    with pytest.raises(RuntimeError):
        ensure_demo_data()


def test_unknown_clinic_id_does_not_fall_back_to_only_clinic():
    from saas.main import app
    t = create_tenant(slug=f"only-{uuid.uuid4().hex[:6]}", name="Only")
    create_user(t.id, "a@x.test", password="pw-123456")
    r = TestClient(app).post("/api/admin/auth/login", json={"tenant_slug": "typo", "email": "a@x.test", "password": "pw-123456"})
    assert r.status_code == 404


# SHA-256 of the Gmail app password the old ensure_demo_data shipped with: only the hash stays in the repo.
_LEAKED_APP_PASSWORD_SHA256 = "dd627981f33130e0600613de65676f2184baa1889a9fc37d3f45b69f9b4de5dc"


def _contains_leaked_app_password(text: str) -> bool:
    """Gmail app passwords are 16 letters, often shown as four groups of four: hash every 16-letter window."""
    for run in re.findall(r"[a-z]{16,}", text.lower().replace(" ", "")):
        for i in range(len(run) - 15):
            if hashlib.sha256(run[i:i + 16].encode()).hexdigest() == _LEAKED_APP_PASSWORD_SHA256:
                return True
    return False


def test_no_hardcoded_mail_credentials_in_source():
    src = pathlib.Path(__file__).resolve().parents[1] / "src"
    for f in src.rglob("*"):
        if not f.is_file() or "__pycache__" in f.parts:
            continue
        text = f.read_text(errors="ignore")
        assert not _contains_leaked_app_password(text) and "parulmaterial@" not in text, f


def test_production_never_fakes_a_send(production):
    from saas import mailbox
    from saas.repositories import create_ai_draft, create_lead
    t = create_tenant(slug=f"p-{uuid.uuid4().hex[:6]}", name="P")
    lead = create_lead(t.id, {"name": "Pat", "email": "pat@x.test"})
    d = create_ai_draft(t.id, lead_id=lead["id"], subject="Hi", body="Hello")
    assert mailbox.demo_mode(t.id) is False
    with pytest.raises(mailbox.MailboxError, match="not connected"):
        mailbox.send_draft(t.id, d["id"])
    with pytest.raises(mailbox.MailboxError):
        mailbox.simulate_reply(t.id, lead["id"], "hi")


def test_demo_login_refused_in_production(production):
    from saas.main import app
    c = TestClient(app)
    assert c.get("/api/admin/auth/demo").json()["available"] is False
    assert c.post("/api/admin/auth/demo").status_code == 404


def test_demo_login_works_locally():
    from saas.main import app
    r = TestClient(app).post("/api/admin/auth/demo")
    assert r.status_code == 200 and r.json()["access_token"]


def test_demo_inbox_has_every_stage():
    from saas.main import app
    from saas.repositories import ensure_demo_data
    ensure_demo_data()
    c = TestClient(app)
    tok = c.post("/api/admin/auth/demo").json()["access_token"]
    inbox = c.get("/api/admin/fd/inbox", headers={"Authorization": f"Bearer {tok}"}).json()
    statuses = {l["status"] for l in inbox}
    assert {"new", "contacted", "booked", "completed"} <= statuses
    assert any(l["draft"] for l in inbox) and any(l["last_direction"] == "out" and not l["draft"] for l in inbox)
