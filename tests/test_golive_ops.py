"""Go-live operations: fail-closed image, scheduler that never dies, no dev surfaces or PHI-on-disk in
production, no access logs, Gemini-only AI, and security headers."""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import re
import secrets
import subprocess
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

from saas.config import get_settings
from saas.repositories import create_lead, create_tenant, create_user
from saas.security import create_access_token

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.delenv("CONCIERGE_DEMO", raising=False)


@pytest.fixture
def client():
    from saas.main import app
    return TestClient(app)


def _clinic() -> dict:
    t = create_tenant(slug=f"golive-{uuid.uuid4().hex[:6]}", name="Go Live Dental")
    u = create_user(t.id, f"owner@{t.slug}.test", role="owner")
    lead = create_lead(t.id, {"name": "Pat Patient", "email": "pat@x.test", "phone": "919-555-0100",
                              "message": "Crown is loose"})
    return {"tenant": t, "lead_id": lead["id"],
            "auth": {"Authorization": f"Bearer {create_access_token(str(u.id), tenant_id=t.id)}"}}


# ── 1. Fail closed ──────────────────────────────────────────────────────────


def test_docker_image_bakes_production_env():
    text = (ROOT / "Dockerfile").read_text()
    env_block = re.search(r"^ENV (?:.*\\\n)*.*$", text, re.M).group(0)
    assert re.search(r"\bAPP_ENV=production\b", env_block)


def test_production_boot_has_no_api_docs(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "CONCIERGE_DEMO"}
    env.update(APP_ENV="production", JWT_SECRET=secrets.token_hex(32), ENCRYPTION_KEY=secrets.token_hex(32),
               DATABASE_URL=str(tmp_path / "prod.db"), CONCIERGE_DB=str(tmp_path / "prod.db"),
               CONCIERGE_SCHEDULER="0", PYTHONPATH=str(ROOT / "src"))
    out = subprocess.run([sys.executable, "-c", "from saas.main import app; print(app.docs_url, app.redoc_url, app.openapi_url)"],
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.split() == ["None", "None", "None"]


# ── 2. Scheduler ────────────────────────────────────────────────────────────


def test_health_reports_scheduler_tick_age(client, monkeypatch):
    from saas import cadence, main
    monkeypatch.setattr(main, "_last_tick_ok", None)
    body = client.get("/health").json()
    assert body["ok"] is True and body["scheduler_last_tick_age_s"] is None
    monkeypatch.setattr(cadence, "run_due", lambda: None)
    main.scheduler_tick()
    body = client.get("/health").json()
    assert body["ok"] is True and body["scheduler_last_tick_age_s"] == 0


def test_tick_survives_mailbox_listing_failure(monkeypatch, caplog):
    from saas import cadence, mailbox, main
    ran = []

    def broken():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(main, "_last_tick_ok", None)
    monkeypatch.setattr(mailbox, "connected_tenants", broken)
    monkeypatch.setattr(cadence, "run_due", lambda: ran.append(1))
    with caplog.at_level(logging.ERROR, logger="heyjarvis.scheduler"):
        main.scheduler_tick()
    assert ran == [1]  # follow-ups still drafted
    assert main._last_tick_ok is None  # not a clean tick: /health age keeps growing
    assert any(r.exc_info for r in caplog.records)


def test_scheduler_loop_keeps_running_after_an_error(monkeypatch):
    from saas import main
    calls = []

    def tick():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(main, "scheduler_tick", tick)
    monkeypatch.setattr(main, "SCHEDULER_INTERVAL_S", 0)

    async def run():
        task = asyncio.create_task(main._scheduler_loop())
        for _ in range(500):
            await asyncio.sleep(0.01)
            if len(calls) >= 3:
                break
        assert not task.done()
        task.cancel()

    asyncio.run(run())
    assert len(calls) >= 3


# ── 3. No legacy/dev surfaces in production ─────────────────────────────────

DEV_ONLY = ["/admin", "/admin.html", "/install", "/docs", "/redoc", "/openapi.json", "/api/docs",
            "/api/openapi.json", "/api/admin/docs", "/api/admin/openapi.json", "/api/admin/fd/docs",
            "/api/admin/fd/openapi.json", "/static/dist/index.html", "/static//dist/index.html",
            "/static/dist/vite.svg", "/api/admin/fd/redoc", "/docs/oauth2-redirect"]


@pytest.mark.parametrize("path", DEV_ONLY)
def test_dev_surfaces_hidden_in_production(production, client, path):
    assert client.get(path).status_code == 404


def test_production_keeps_the_real_pages(production, client):
    t = create_tenant(slug=f"keep-{uuid.uuid4().hex[:6]}", name="Keep Dental")
    for path in ("/frontdesk", "/frontdesk/settings", "/frontdesk/full", "/widget.js", "/static/widget.js",
                 "/health", f"/concierge/{t.slug}"):
        assert client.get(path).status_code == 200, path
    assert client.get("/oauth/google/callback", follow_redirects=False).status_code == 303
    assert client.get("/api/admin/fd/leads").status_code == 401  # APIs stay up (login required)


def test_dev_surfaces_still_work_locally(client):
    for path in ("/admin", "/docs", "/openapi.json", "/static/dist/index.html", "/static/..%2fstatic/dist/index.html"):
        assert client.get(path).status_code == 200, path


# An encoded slash is decoded after routing, so 'dist' is not the first path segment; the served file still is.
@pytest.mark.parametrize("path", ["/static/..%2fstatic/dist/index.html", "/static/..%2Fstatic/dist/vite.svg",
                                  "/static/%2e%2e%2fstatic/dist/index.html", "/static/%2e%2e/static/dist/index.html",
                                  "/static/x/..%2f..%2fstatic/dist/index.html", "/static/..%2fstatic/DIST/index.html",
                                  "/static/./dist/index.html", "/static/..%2fstatic/dist"])
def test_retired_bundle_blocked_through_encoded_paths(production, client, path):
    assert client.get(path).status_code == 404


def test_retired_bundle_left_out_of_deploys():
    assert "/src/saas/static/dist/" in (ROOT / ".railwayignore").read_text().splitlines()
    # .dockerignore patterns are anchored at the context root: the existing 'dist/' doesn't reach static/dist.
    assert "src/saas/static/dist/" in (ROOT / ".dockerignore").read_text().splitlines()
    pages = [ROOT / "src" / "saas" / "templates" / f for f in ("desk.html", "settings.html", "frontdesk.html", "hosted.html")]
    for page in pages + [ROOT / "src" / "saas" / "static" / "widget.js"]:
        assert "static/dist" not in page.read_text(), page.name  # nothing live loads the bundle


# ── 4. Legacy notification emailer never writes PHI to disk in production ──


@pytest.fixture
def outbox(monkeypatch, tmp_path):
    from saas import emailer
    box = tmp_path / "sent"
    box.mkdir()
    monkeypatch.setattr(emailer, "OUTBOX", box)
    return box


@pytest.mark.parametrize("action", ["resend", "retry", "resend-email", "retry-notify"])
def test_resend_refused_without_mailbox_in_production(production, client, outbox, action):
    c = _clinic()
    r = client.post(f"/api/admin/fd/leads/{c['lead_id']}/{action}", headers=c["auth"])
    assert r.status_code == 409
    assert "Connect the clinic mailbox" in r.json()["detail"]
    assert list(outbox.iterdir()) == []


def test_admin_test_email_refused_without_mailbox_in_production(production, client, outbox):
    c = _clinic()
    r = client.post(f"/api/admin/tenants/{c['tenant'].id}/email/test", headers=c["auth"])
    assert r.status_code == 409
    assert list(outbox.iterdir()) == []


def test_send_email_refuses_dry_run_in_production(production, outbox):
    from saas import emailer
    c = _clinic()
    with pytest.raises(emailer.MailboxNotConnected):
        emailer.send_email(c["tenant"].id, "desk@x.test", "New patient", "Pat Patient, 919-555-0100")
    assert list(outbox.iterdir()) == []


def test_resend_still_dry_runs_locally(client, outbox):
    c = _clinic()
    r = client.post(f"/api/admin/fd/leads/{c['lead_id']}/resend", headers=c["auth"])
    assert r.status_code == 200 and r.json()["status"] == "sent"
    assert len(list(outbox.iterdir())) == 1


@pytest.fixture
def mailbox_clinic(monkeypatch):
    """Clinic mailbox connected the way Settings -> Email does it, no front desk address; every send captured."""
    from saas import emailer, login_codes, mailbox
    monkeypatch.setattr(mailbox, "_check_public_host", lambda host: None)  # no DNS lookups in tests
    monkeypatch.setattr(emailer.settings, "default_smtp_reply_to", None)  # no FRONT_DESK_EMAIL fallback either
    c = _clinic()
    mailbox.connect_mailbox(c["tenant"].id, "einstein", "desk@clinic.test", "pw")
    c["clinic_mail"], c["team_mail"] = [], []
    monkeypatch.setattr(emailer, "_smtp_send", lambda tid, msg: c["clinic_mail"].append(msg) or True)
    monkeypatch.setattr(login_codes, "send_system_email",
                        lambda to, subject, body, dev_note=None: c["team_mail"].append((to, subject, body)) or True)
    return c


@pytest.mark.parametrize("action", ["resend", "retry", "resend-email", "retry-notify"])
def test_realert_without_front_desk_address_sends_phi_free_team_alert(production, client, mailbox_clinic, action):
    c = mailbox_clinic
    r = client.post(f"/api/admin/fd/leads/{c['lead_id']}/{action}", headers=c["auth"])
    assert r.status_code == 200 and r.json()["notified"] == "team"
    assert c["clinic_mail"] == []  # no patient details from the clinic mailbox to 'None'
    [(to, subject, body)] = c["team_mail"]
    assert to == f"owner@{c['tenant'].slug}.test" and subject == "New patient request"
    for private in ("Pat", "pat@x.test", "919-555-0100", "Crown"):
        assert private not in subject and private not in body


def test_realert_with_front_desk_address_mails_it(production, client, mailbox_clinic):
    from saas.database import connect
    c = mailbox_clinic
    with connect() as db:
        db.execute("UPDATE email_settings SET front_desk_email = ? WHERE tenant_id = ?",
                   ("frontdesk@clinic.test", c["tenant"].id))
    r = client.post(f"/api/admin/fd/leads/{c['lead_id']}/retry", headers=c["auth"])
    assert r.status_code == 200 and r.json()["notified"] == "front_desk"
    [msg] = c["clinic_mail"]
    assert msg["To"] == "frontdesk@clinic.test" and c["team_mail"] == []


@pytest.mark.parametrize("stored", [None, "", "  ", "None"], ids=["null", "empty", "blank", "None-string"])
def test_lead_notification_never_mails_a_missing_recipient(mailbox_clinic, stored):
    from saas import emailer
    from saas.database import connect
    c = mailbox_clinic
    with connect() as db:
        db.execute("UPDATE email_settings SET front_desk_email = ? WHERE tenant_id = ?", (stored, c["tenant"].id))
    with pytest.raises(emailer.NoFrontDeskAddress):
        emailer.send_lead_notification(c["tenant"].id, c["lead_id"], "retry")
    assert c["clinic_mail"] == []


# ── 5. No access logs (URLs carry patient search terms) ─────────────────────


@pytest.mark.parametrize("name", ["Dockerfile", "Procfile", "render.yaml", "nixpacks.toml"])
def test_start_commands_disable_access_log(name):
    text = (ROOT / name).read_text()
    assert "--no-access-log" in text and "--workers 1" in text and "--proxy-headers" in text


# ── 7. Gemini only ──────────────────────────────────────────────────────────


def test_groq_needs_explicit_opt_in(monkeypatch):
    from saas import ai_engine
    monkeypatch.setattr(ai_engine, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.delenv("CONCIERGE_ALLOW_GROQ", raising=False)
    assert {p for p, _ in ai_engine._provider_chain()} == {"gemini"}
    monkeypatch.setenv("CONCIERGE_ALLOW_GROQ", "1")
    assert [p for p, _ in ai_engine._provider_chain()][-1] == "groq"


# ── 8. Security headers ─────────────────────────────────────────────────────


def test_security_headers_on_every_response(client):
    t = create_tenant(slug=f"hdr-{uuid.uuid4().hex[:6]}", name="Header Dental")
    for path in ("/health", f"/concierge/{t.slug}", "/widget.js", "/frontdesk", "/api/admin/fd/leads"):
        r = client.get(path)
        assert r.headers["X-Content-Type-Options"] == "nosniff", path
        assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin", path
        assert "Strict-Transport-Security" not in r.headers, path  # plain http


def test_hsts_over_https_and_behind_proxy():
    from saas.main import app
    assert "max-age" in TestClient(app, base_url="https://testserver").get("/health").headers["Strict-Transport-Security"]
    r = TestClient(app).get("/health", headers={"X-Forwarded-Proto": "https"})
    assert "Strict-Transport-Security" in r.headers


def test_only_staff_pages_refuse_framing(client):
    t = create_tenant(slug=f"frm-{uuid.uuid4().hex[:6]}", name="Frame Dental")
    for path in ("/frontdesk", "/frontdesk/settings", "/frontdesk/full", "/api/admin/fd/leads"):
        assert client.get(path).headers.get("X-Frame-Options") == "SAMEORIGIN", path
    # Clinics may iframe the hosted chat page; the widget script is loaded cross-site.
    for path in (f"/concierge/{t.slug}", "/widget.js", "/health"):
        assert "X-Frame-Options" not in client.get(path).headers, path
