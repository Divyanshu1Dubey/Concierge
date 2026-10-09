"""Regression tests for defects found by the multi-agent launch review."""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import pytest
from fastapi.testclient import TestClient

from saas import cadence, mailbox
from saas.config import get_settings
from saas.database import connect, now_iso, rows
from saas.repositories import create_api_key, create_lead, create_tenant, create_user

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src" / "saas" / "templates"


@pytest.fixture
def client():
    from saas.main import app
    return TestClient(app, follow_redirects=False)


def _login(client, slug, email, password="pw-123456"):
    r = client.post("/api/admin/auth/login", json={"tenant_slug": slug, "email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def clinic(client):
    slug = f"rv-{uuid.uuid4().hex[:6]}"
    t = create_tenant(slug=slug, name="Review Dental")
    create_user(t.id, "owner@rv.test", password="pw-123456", role="owner")
    create_user(t.id, "member@rv.test", password="pw-123456", role="member")
    return {"id": t.id, "slug": slug, "owner": _login(client, slug, "owner@rv.test"),
            "member": _login(client, slug, "member@rv.test")}


# ── XSS ──────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
@pytest.mark.parametrize("page,fn", [("desk.html", "esc"), ("settings.html", "esc"), ("frontdesk.html", "escapeHtml")])
def test_page_escapers_escape_quotes(page, fn):
    src = (TEMPLATES / page).read_text()
    m = re.search(r"function " + fn + r"\((\w+)\) \{.*?\n?\}", src, re.S)
    body = src[m.start():src.index("}", src.index("return", m.start())) + 1]
    out = subprocess.run(["node", "-e", body + f";process.stdout.write({fn}(`1\" onmouseover=\"x' y<b>&`))"],
                         capture_output=True, text=True, timeout=20).stdout
    assert '"' not in out and "'" not in out and "<" not in out
    assert "&quot;" in out and "&#39;" in out


def test_frontdesk_ai_text_not_in_inline_handlers():
    src = (TEMPLATES / "frontdesk.html").read_text()
    assert "useAiText(aiTexts[" in src and "escapeAttr" not in src


def test_hosted_page_escapes_clinic_name(client, clinic):
    client.patch(f"/api/admin/tenants/{clinic['id']}", json={"name": "</title><script>alert(1)</script>"}, headers=clinic["owner"])
    html = client.get(f"/concierge/{clinic['slug']}").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_public_lead_phone_is_sanitized(client, clinic):
    key = create_api_key(clinic["id"], "w", "s").public_key
    r = client.post("/api/v1/public/leads", params={"client_key": key},
                    json={"name": "X", "email": "x@x.test", "phone": '1" onmouseover="steal()'})
    with connect() as c:
        phone = rows(c, "SELECT phone FROM leads WHERE id = ?", r.json()["lead_id"])[0]["phone"]
    assert '"' not in phone and "onmouseover" not in phone and phone.startswith("1")


# ── AI provider chain ────────────────────────────────────────────────────


def test_llm_chain_passes_system_and_schema(monkeypatch):
    from saas import ai_engine
    monkeypatch.setenv("CONCIERGE_USE_LLM", "1")
    monkeypatch.setattr(ai_engine, "GEMINI_API_KEY", "test-key")
    seen = {}

    def fake(prompt, model, *, emit=None, system="", schema=None):
        seen.update(system=system, schema=schema, model=model)
        return {"text": "ok"}

    monkeypatch.setattr(ai_engine, "_call_gemini", fake)
    result, provider = ai_engine._llm("hi", system="SYS", schema={"type": "object"})
    assert result == {"text": "ok"} and provider == "gemini"
    assert seen["system"] == "SYS" and seen["schema"] == {"type": "object"}


# ── Roles on legacy admin routes ─────────────────────────────────────────


@pytest.mark.parametrize("method,path,body", [
    ("patch", "/api/admin/tenants/{t}", {"enabled": False}),
    ("post", "/api/admin/tenants/{t}/integration/regenerate-key", None),
    ("post", "/api/admin/tenants/{t}/integration/domains", {"domain": "evil.test"}),
])
def test_members_cannot_change_clinic_setup(client, clinic, method, path, body):
    kw = {"headers": clinic["member"]}
    if body is not None:
        kw["json"] = body
    assert getattr(client, method)(path.format(t=clinic["id"]), **kw).status_code == 403


# ── Mailbox robustness ───────────────────────────────────────────────────


class FakeSMTP:
    sent: list = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


class Imap:
    def __init__(self, inbox):
        self.inbox = inbox

    def select(self, folder, readonly=False):
        self.cur = self.inbox if folder == "INBOX" else []
        return "OK", [b"1"]

    def response(self, code):
        return code, [b"7"]

    def uid(self, cmd, *args):
        if cmd == "SEARCH":
            return "OK", [" ".join(str(i + 1) for i in range(len(self.cur))).encode()]
        return "OK", [(b"1 (BODY[] {n}", self.cur[int(args[0]) - 1]), b")"]

    def list(self):
        return "OK", [b'(\\HasNoChildren \\Sent) "/" "Sent"']

    def logout(self):
        pass


@pytest.fixture
def connected(clinic, monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(mailbox, "_smtp", lambda s: FakeSMTP())
    mailbox.connect_mailbox(clinic["id"], "einstein", "desk@rv.test", "pw")
    lead = create_lead(clinic["id"], {"name": "Pat Lee", "email": "pat@x.test"})
    return clinic["id"], lead["id"]


def test_odd_message_does_not_block_reply_tracking(connected, monkeypatch):
    tid, lid = connected
    now = formatdate()  # not a thread reply: must be dated after the lead was created to count
    bad = (b"From: pat@x.test\r\nTo: desk@rv.test\r\nSubject: Re: ma\xc3\xb1ana \xe2\x80\x94 cita\r\n"
           b"Message-ID: <bad@x>\r\nDate: " + now.encode() + b"\r\n\r\nHola, el martes funciona.\r\n")
    good = EmailMessage()
    good["From"], good["To"], good["Subject"] = "pat@x.test", "desk@rv.test", "Re: request"
    good["Message-ID"], good["Date"] = make_msgid(domain="x"), now
    good.set_content("Thursday works")
    monkeypatch.setattr(mailbox, "_imap", lambda s: Imap([bad, bytes(good)]))
    stats = mailbox.sync_mailbox(tid)
    bodies = [m["body"] for m in mailbox.lead_thread(tid, lid)]
    assert "Thursday works" in bodies and stats["inbound"] >= 1
    assert json.loads(mailbox.get_settings_row(tid)["imap_state"])["in:INBOX"]["last_uid"] == 2


def test_folded_subject_does_not_break_sending(connected):
    tid, lid = connected
    mailbox.record_message(tid, lid, "in", "<root@x>", from_addr="pat@x.test", to_addr=None,
                           subject="Question about my cleaning\r\n and insurance", body="hi", source="mailbox")
    from saas.repositories import create_ai_draft
    d = create_ai_draft(tid, lead_id=lid, subject="x", body="Hello")
    mailbox.send_draft(tid, d["id"])
    assert FakeSMTP.sent[-1]["Subject"] == "Re: Question about my cleaning and insurance"


def test_discarded_draft_cannot_be_sent(connected):
    tid, lid = connected
    from saas.repositories import create_ai_draft
    d = create_ai_draft(tid, lead_id=lid, subject="x", body="Hello")
    with connect() as c:
        c.execute("UPDATE ai_drafts SET status = 'discarded' WHERE id = ?", (d["id"],))
    with pytest.raises(mailbox.MailboxError, match="discarded"):
        mailbox.send_draft(tid, d["id"])
    assert FakeSMTP.sent == []


def test_outlook_quoted_history_is_stripped():
    body = ("Do you have anything Tuesday afternoon?\n\n________________________________\n"
            "From: Front Desk <desk@rv.test>\nSent: Monday, October 5, 2026 9:00 AM\nTo: Pat\n"
            "Subject: Your appointment request\n\nwe'll get you scheduled")
    assert mailbox.strip_quoted(body) == "Do you have anything Tuesday afternoon?"
    body2 = "Works for me\n\nFrom: Front Desk <desk@rv.test>\nSent: Monday\nTo: Pat\n\nbooked"
    assert mailbox.strip_quoted(body2) == "Works for me"


def test_legacy_rows_without_incoming_server_need_reconnect(clinic, monkeypatch):
    with connect() as c:
        c.execute("INSERT INTO email_settings (tenant_id, provider, smtp_host, smtp_port, smtp_user, smtp_password_enc, "
                  "updated_at) VALUES (?, 'smtp', 'smtp.einsteinmail.com', 465, 'desk@rv.test', 'x', ?)",
                  (clinic["id"], now_iso()))
    assert not mailbox.is_connected(clinic["id"])
    with pytest.raises(mailbox.MailboxError):
        mailbox.sync_mailbox(clinic["id"])


def test_hosts_rechecked_right_before_connecting(clinic, monkeypatch):
    mailbox.connect_mailbox(clinic["id"], "einstein", "desk@rv.test", "pw")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.delenv("CONCIERGE_DEMO", raising=False)
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))])
    with pytest.raises(mailbox.MailboxError, match="not a public mail server"):
        mailbox._smtp(mailbox.get_settings_row(clinic["id"]))
    with pytest.raises(mailbox.MailboxError, match="not a public mail server"):
        mailbox._imap(mailbox.get_settings_row(clinic["id"]))


# ── Follow-up logic ──────────────────────────────────────────────────────


@pytest.mark.parametrize("text,intent", [
    ("Can I get scheduled for Tuesday morning?", "wants_appointment"),
    ("I haven't booked yet - what times do you have Thursday?", "wants_appointment"),
    ("I called yesterday but nobody picked up. Is Friday at 2pm open?", "wants_appointment"),
    ("Thanks! I already booked by phone.", "booked"),
    ("Please cancel my appointment", "cancel"),
    ("I can't cancel online, can you help?", "question"),
    ("No thanks, I found another dentist", "not_interested"),
])
def test_rules_classifier_is_conservative(text, intent):
    assert cadence.classify_reply(text)["intent"] == intent


def test_concurrent_runs_create_one_draft_per_step(clinic):
    lead = create_lead(clinic["id"], {"name": "Pat", "email": "p@x.test"})
    cadence.enroll(clinic["id"], lead["id"])
    results = []
    threads = [threading.Thread(target=lambda: results.append(cadence.run_due(clinic["id"]))) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    with connect() as c:
        n = rows(c, "SELECT COUNT(*) n FROM ai_drafts WHERE lead_id = ? AND status = 'pending'", lead["id"])[0]["n"]
    assert n == 1


def test_booked_status_stops_followups(client, clinic):
    lead = create_lead(clinic["id"], {"name": "Pat", "email": "p@x.test"})
    cadence.enroll(clinic["id"], lead["id"])
    client.patch(f"/api/admin/fd/leads/{lead['id']}/status", json={"status": "booked"}, headers=clinic["member"])
    assert cadence.get_enrollment(clinic["id"], lead["id"])["status"] == "stopped"


# ── Chat names ───────────────────────────────────────────────────────────


def _chat(client, key, messages):
    conv = client.post("/api/v1/public/conversations", params={"client_key": key}).json()
    out = None
    for m in messages:
        out = client.post(f"/api/v1/public/conversations/{conv['conversation_id']}/messages",
                          params={"client_key": key}, json={"message": m},
                          headers={"X-Conversation-Token": conv["conversation_token"]}).json()
    return out


def test_name_not_overwritten_by_later_sentences(client, clinic):
    key = create_api_key(clinic["id"], "w", "s").public_key
    out = _chat(client, key, ["Checkup & cleaning", "Sarah", "this is my email sarah@gmail.com"])
    assert out["state"] == "submitted" and out["fields"]["name"] == "Sarah"


def test_this_is_urgent_is_not_a_name(client, clinic):
    key = create_api_key(clinic["id"], "w", "s").public_key
    out = _chat(client, key, ["This is urgent, my tooth broke"])
    assert "name" not in out["fields"] and "name" in out["reply"].lower()


# ── Google sign-in state ─────────────────────────────────────────────────


def test_google_callback_rejects_other_browser(monkeypatch, clinic):
    from urllib.parse import parse_qs, urlparse

    from saas import google_oauth
    from saas.main import app
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    attacker = TestClient(app, follow_redirects=False)
    tok = attacker.post("/api/admin/auth/login", json={"tenant_slug": clinic["slug"], "email": "owner@rv.test",
                                                       "password": "pw-123456"}).json()["access_token"]
    url = attacker.post("/api/admin/fd/mailbox/google/start", json={},
                        headers={"Authorization": f"Bearer {tok}"}).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    monkeypatch.setattr(google_oauth, "exchange_code", lambda code: pytest.fail("must not exchange the code"))
    victim = TestClient(app, follow_redirects=False)  # different browser: no state cookie
    r = victim.get("/oauth/google/callback", params={"code": "c", "state": state})
    assert "different browser" in r.headers["location"].replace("%20", " ")


# ── Deploy, time, alerts ─────────────────────────────────────────────────


def test_deploy_configs_trust_proxy_and_single_worker():
    for f in ("render.yaml", "Dockerfile", "Procfile"):
        text = (ROOT / f).read_text()
        assert "--proxy-headers" in text and "--workers 1" in text, f


def test_timestamps_are_utc():
    stored = datetime.fromisoformat(now_iso())
    assert abs((datetime.now(timezone.utc).replace(tzinfo=None) - stored).total_seconds()) < 5


def test_new_request_alert_reaches_team_without_details(client, clinic, monkeypatch):
    from saas import login_codes
    sent = []
    monkeypatch.setattr(login_codes, "send_system_email", lambda to, subject, body, dev_note=None: sent.append((to, subject, body)) or True)
    key = create_api_key(clinic["id"], "w", "s").public_key
    client.post("/api/v1/public/leads", params={"client_key": key},
                json={"name": "Dana Cruz", "email": "dana@x.test", "intent": "emergency", "message": "my private symptoms"})
    assert sorted(t for t, _, _ in sent) == ["member@rv.test", "owner@rv.test"]
    to, subject, body = sent[0]
    assert subject.startswith("URGENT") and "emergency" in body
    assert f"/frontdesk?clinic={clinic['slug']}" in body
    for private in ("Dana", "Cruz", "dana@x.test", "private symptoms"):
        assert private not in subject and private not in body
