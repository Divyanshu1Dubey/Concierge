"""Launch features: any IMAP/SMTP mailbox (Einstein Mail), clinic details, team logins, merged AI actions."""

from __future__ import annotations

import smtplib
import uuid

import pytest
from fastapi.testclient import TestClient

from saas import cadence, mailbox
from saas.config import get_settings
from saas.database import connect, rows
from saas.repositories import create_api_key, create_lead, create_tenant, create_user


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
    slug = f"rd-{uuid.uuid4().hex[:6]}"
    t = create_tenant(slug=slug, name="Raleigh Dentistry")
    create_user(t.id, "owner@rd.test", password="pw-123456", role="owner")
    return {"id": t.id, "slug": slug, "owner": _login(client, slug, "owner@rd.test")}


class FakeSMTP:
    def __init__(self, host=None, port=None, **kw):
        self.host, self.port, self.logins, self.sent = host, port, [], []
        FakeSMTP.last = self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, **kw):
        self.tls = True

    def login(self, user, password):
        self.logins.append((user, password))

    def send_message(self, msg):
        self.sent.append(msg)


class FakeIMAP:
    def __init__(self, folders=None):
        self.folders = folders if folders is not None else [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "Sent Items"']

    def list(self):
        return "OK", self.folders

    def logout(self):
        pass


# ── Mailbox providers ────────────────────────────────────────────────────


def test_einstein_preset_fills_servers(clinic):
    st = mailbox.connect_mailbox(clinic["id"], "einstein", "FrontDesk@RaleighDentistry.com", "secret")
    row = mailbox.get_settings_row(clinic["id"])
    assert (row["smtp_host"], row["smtp_port"], row["imap_host"], row["imap_port"]) == \
           ("smtp.einsteinmail.com", 587, "imap.einsteinmail.com", 993)
    assert st["connected"] and st["provider"] == "einstein" and st["address"] == "frontdesk@raleighdentistry.com"
    assert "secret" not in (row["smtp_password_enc"] or "")


@pytest.mark.parametrize("kwargs,err", [
    ({"smtp_host": "", "imap_host": ""}, "server addresses"),
    ({"smtp_host": "smtp.x.com", "imap_host": "imap.x.com", "smtp_port": 22}, "Outgoing port"),
    ({"smtp_host": "smtp.x.com", "imap_host": "imap.x.com", "imap_port": 8080}, "Incoming port"),
    ({"smtp_host": "smtp.x.com; rm -rf", "imap_host": "imap.x.com"}, "not a valid server"),
])
def test_custom_provider_validation(clinic, kwargs, err):
    with pytest.raises(ValueError, match=err):
        mailbox.connect_mailbox(clinic["id"], "custom", "a@b.com", "pw", **kwargs)


def test_production_rejects_internal_mail_servers(clinic, monkeypatch):
    """A clinic admin must not be able to point the server at internal addresses (SSRF)."""
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.delenv("CONCIERGE_DEMO", raising=False)
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("169.254.169.254", 0))])
    with pytest.raises(ValueError, match="not a public mail server"):
        mailbox.connect_mailbox(clinic["id"], "custom", "a@b.com", "pw", smtp_host="evil.test", imap_host="evil.test")
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("18.204.29.158", 0))])
    assert mailbox.connect_mailbox(clinic["id"], "einstein", "a@b.com", "pw")["connected"]


def test_separate_login_username_is_used(clinic, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)  # Einstein sends on 587 with STARTTLS
    mailbox.connect_mailbox(clinic["id"], "einstein", "frontdesk@rd.test", "pw", username="rd-frontdesk")
    with mailbox._smtp(mailbox.get_settings_row(clinic["id"])):
        pass
    assert FakeSMTP.last.logins == [("rd-frontdesk", "pw")]


def test_port_587_uses_starttls(clinic, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    mailbox.connect_mailbox(clinic["id"], "custom", "frontdesk@rd.test", "pw", smtp_host="smtp.rd.test", smtp_port=587, imap_host="imap.rd.test")
    mailbox._smtp(mailbox.get_settings_row(clinic["id"]))
    assert FakeSMTP.last.port == 587 and FakeSMTP.last.tls


def test_imap_143_uses_starttls(clinic, monkeypatch):
    import imaplib
    seen = {}

    class IMAP4:
        def __init__(self, host, port, timeout=None):
            seen["plain"] = (host, port)

        def starttls(self, ssl_context=None):
            seen["tls"] = True

        def login(self, user, pw):
            seen["login"] = user

    monkeypatch.setattr(imaplib, "IMAP4", IMAP4)
    mailbox.connect_mailbox(clinic["id"], "custom", "a@rd.test", "pw", smtp_host="smtp.rd.test",
                            imap_host="imap.rd.test", imap_port=143)
    mailbox._imap(mailbox.get_settings_row(clinic["id"]))
    assert seen == {"plain": ("imap.rd.test", 143), "tls": True, "login": "a@rd.test"}


@pytest.mark.parametrize("folders,expected", [
    ([b'(\\HasNoChildren \\Sent) "/" "Sent Items"', b'(\\HasNoChildren) "/" "Sent"'], "Sent Items"),
    ([b'(\\HasNoChildren) "." "INBOX"', b'(\\HasNoChildren) "." "INBOX.Sent"'], "INBOX.Sent"),
    ([b'(\\HasNoChildren) "/" Sent'], "Sent"),
    ([b'(\\HasNoChildren) "/" "INBOX"'], None),
])
def test_detect_sent_folder(folders, expected):
    assert mailbox.detect_sent_folder(FakeIMAP(folders)) == expected


def test_connect_test_saves_detected_sent_folder(clinic, monkeypatch):
    monkeypatch.setattr(mailbox, "_smtp", lambda s: FakeSMTP())
    monkeypatch.setattr(mailbox, "_imap", lambda s: FakeIMAP())
    mailbox.connect_mailbox(clinic["id"], "einstein", "frontdesk@rd.test", "pw")
    out = mailbox.test_mailbox(clinic["id"])
    assert out["ok"] and out["sent_folder"] == "Sent Items"
    assert mailbox.get_settings_row(clinic["id"])["sent_folder"] == "Sent Items"


def test_friendly_errors_depend_on_provider(clinic):
    err = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
    mailbox.connect_mailbox(clinic["id"], "einstein", "a@rd.test", "pw")
    assert "mail server rejected the login" in mailbox._friendly(err, mailbox.get_settings_row(clinic["id"]))
    mailbox.connect_mailbox(clinic["id"], "gmail", "a@gmail.com", "pw")
    assert "Google" in mailbox._friendly(err, mailbox.get_settings_row(clinic["id"]))


def test_send_test_email_goes_to_itself(clinic, monkeypatch):
    fake = FakeSMTP()
    monkeypatch.setattr(mailbox, "_smtp", lambda s: fake)
    monkeypatch.setattr(mailbox, "_imap", lambda s: FakeIMAP())
    mailbox.connect_mailbox(clinic["id"], "einstein", "frontdesk@rd.test", "pw", from_name="Raleigh Dentistry")
    assert mailbox.send_test_email(clinic["id"])["to"] == "frontdesk@rd.test"
    assert fake.sent[0]["To"] == "frontdesk@rd.test" and "Raleigh Dentistry" in fake.sent[0]["From"]


def test_mailbox_api_connect_and_test_send(client, clinic, monkeypatch):
    monkeypatch.setattr(mailbox, "_smtp", lambda s: FakeSMTP())
    monkeypatch.setattr(mailbox, "_imap", lambda s: FakeIMAP())
    h = clinic["owner"]
    r = client.put("/api/admin/fd/mailbox", json={"provider": "einstein", "address": "frontdesk@rd.test", "password": "pw"}, headers=h)
    assert r.status_code == 200 and r.json()["test"]["ok"] and r.json()["provider"] == "einstein"
    assert client.put("/api/admin/fd/mailbox", json={"provider": "einstein", "address": "frontdesk@rd.test"}, headers=h).status_code == 422
    assert client.post("/api/admin/fd/mailbox/test-send", headers=h).json()["ok"]
    status = client.get("/api/admin/fd/mailbox", headers=h).json()
    assert all("enc" not in k for k in status)


def test_sync_finds_sent_folder_for_non_gmail(clinic, monkeypatch):
    seen = []

    class Imap(FakeIMAP):
        def select(self, folder, readonly=False):
            seen.append(folder)
            return "OK", [b"0"]

        def response(self, code):
            return code, [b"1"]

        def uid(self, cmd, *args):
            return "OK", [b""]

    monkeypatch.setattr(mailbox, "_imap", lambda s: Imap())
    mailbox.connect_mailbox(clinic["id"], "einstein", "frontdesk@rd.test", "pw")
    mailbox.sync_mailbox(clinic["id"])
    assert seen == ["INBOX", '"Sent Items"']


# ── Clinic details ───────────────────────────────────────────────────────


def test_clinic_profile_api_and_permissions(client, clinic):
    h = clinic["owner"]
    r = client.put("/api/admin/fd/clinic", json={"name": "Raleigh Comprehensive Dentistry", "phone": "(919) 555-0100",
                                                 "address": "1 Main St", "hours": "Mon-Fri 8-5"}, headers=h)
    assert r.status_code == 200 and r.json()["phone"] == "(919) 555-0100"
    assert client.get("/api/admin/fd/clinic", headers=h).json()["name"] == "Raleigh Comprehensive Dentistry"
    assert client.put("/api/admin/fd/clinic", json={"name": "  "}, headers=h).status_code == 422
    create_user(clinic["id"], "desk@rd.test", password="pw-123456", role="member")
    m = _login(client, clinic["slug"], "desk@rd.test")
    assert client.put("/api/admin/fd/clinic", json={"phone": "1"}, headers=m).status_code == 403
    assert client.get("/api/admin/fd/clinic", headers=m).status_code == 200


def test_emails_use_clinic_phone(clinic):
    from saas.repositories import save_clinic_profile
    save_clinic_profile(clinic["id"], {"phone": "(919) 555-0100"})
    er = create_lead(clinic["id"], {"name": "Mike Chang", "email": "m@x.test", "intent": "emergency"})
    lead = create_lead(clinic["id"], {"name": "Sara Lee", "email": "s@x.test", "service": "cleaning"})
    for l in (er, lead):
        cadence.enroll(clinic["id"], l["id"])
    cadence.run_due(clinic["id"])
    with connect() as c:
        bodies = {r["lead_id"]: r["body"] for r in rows(c, "SELECT lead_id, body FROM ai_drafts")}
    assert "call our office right away at (919) 555-0100" in bodies[er["id"]]
    assert "call us at (919) 555-0100" in bodies[lead["id"]] and bodies[lead["id"]].rstrip().endswith("(919) 555-0100")


def test_emails_without_phone_read_naturally(clinic):
    er = create_lead(clinic["id"], {"name": "Mike Chang", "email": "m@x.test", "intent": "emergency"})
    cadence.enroll(clinic["id"], er["id"])
    [did] = cadence.run_due(clinic["id"])
    with connect() as c:
        body = rows(c, "SELECT body FROM ai_drafts WHERE id = ?", did)[0]["body"]
    assert "right away so we can see you" in body and " at  " not in body


def test_chat_emergency_gives_phone(client, clinic):
    from saas.repositories import save_clinic_profile
    save_clinic_profile(clinic["id"], {"phone": "(919) 555-0100"})
    key = create_api_key(clinic["id"], "w", "s").public_key
    cfg = client.get("/api/v1/public/config", params={"client_key": key}).json()
    assert cfg["widget_config"]["clinic"]["phone"] == "(919) 555-0100"
    conv = client.post("/api/v1/public/conversations", params={"client_key": key}).json()
    out = client.post(f"/api/v1/public/conversations/{conv['conversation_id']}/messages", params={"client_key": key},
                      json={"message": "I'm Mike, my tooth is in severe pain, mike@x.test"}).json()
    assert out["state"] == "submitted" and "(919) 555-0100" in out["reply"]


def test_onboard_cli_saves_clinic_details(monkeypatch, capsys):
    import sys
    from saas import cli
    from saas.repositories import get_clinic_profile, get_tenant_by_slug
    slug = f"cli-{uuid.uuid4().hex[:6]}"
    monkeypatch.setattr(sys, "argv", ["saas.cli", "onboard", "--slug", slug, "--name", "CLI Dental", "--owner-email",
                                      "o@cli.test", "--domain", "cli.test", "--phone", "(919) 555-0199",
                                      "--hours", "Mon-Fri 8-5"])
    cli.onboard()
    p = get_clinic_profile(get_tenant_by_slug(slug).id)
    assert p["phone"] == "(919) 555-0199" and p["hours"] == "Mon-Fri 8-5"
    assert "data-heyjarvis-client" in capsys.readouterr().out


# ── Team ─────────────────────────────────────────────────────────────────


@pytest.fixture
def invites(monkeypatch):
    from saas import login_codes
    sent = []
    monkeypatch.setattr(login_codes, "send_system_email", lambda to, subject, body, dev_note=None: sent.append((to, subject, body)) or True)
    monkeypatch.setattr(login_codes, "_send", lambda to, code, name: sent.append((to, "code", code)))
    return sent


def test_owner_adds_teammate_who_signs_in_with_code(client, clinic, invites):
    r = client.post("/api/admin/fd/team", json={"email": "Jamie@RD.test", "name": "Jamie", "role": "member"}, headers=clinic["owner"])
    assert r.status_code == 200 and r.json()["invite_sent"]
    to, subject, body = invites[-1]
    assert to == "jamie@rd.test" and clinic["slug"] in body and "/frontdesk" in body
    team = client.get("/api/admin/fd/team", headers=clinic["owner"]).json()["team"]
    assert [p["email"] for p in team] == ["owner@rd.test", "jamie@rd.test"]
    client.post("/api/admin/auth/code/request", json={"tenant_slug": clinic["slug"], "email": "jamie@rd.test"})
    code = invites[-1][2]
    r = client.post("/api/admin/auth/code/verify", json={"tenant_slug": clinic["slug"], "email": "jamie@rd.test", "code": code})
    assert r.status_code == 200


def test_team_permissions(client, clinic, invites):
    h = clinic["owner"]
    assert client.post("/api/admin/fd/team", json={"email": "bad"}, headers=h).status_code == 422
    assert client.post("/api/admin/fd/team", json={"email": "x@rd.test", "role": "owner"}, headers=h).status_code == 422
    client.post("/api/admin/fd/team", json={"email": "adm@rd.test", "role": "admin"}, headers=h)
    assert client.post("/api/admin/fd/team", json={"email": "adm@rd.test"}, headers=h).status_code == 409
    create_user(clinic["id"], "mem@rd.test", password="pw-123456", role="member")
    m = _login(client, clinic["slug"], "mem@rd.test")
    assert client.post("/api/admin/fd/team", json={"email": "z@rd.test"}, headers=m).status_code == 403
    create_user(clinic["id"], "adm2@rd.test", password="pw-123456", role="admin")
    a = _login(client, clinic["slug"], "adm2@rd.test")
    assert client.post("/api/admin/fd/team", json={"email": "z@rd.test", "role": "admin"}, headers=a).status_code == 403
    assert client.post("/api/admin/fd/team", json={"email": "z@rd.test", "role": "member"}, headers=a).status_code == 200


def test_removed_teammate_loses_access_immediately(client, clinic, invites):
    create_user(clinic["id"], "gone@rd.test", password="pw-123456", role="member")
    g = _login(client, clinic["slug"], "gone@rd.test")
    assert client.get("/api/admin/fd/inbox", headers=g).status_code == 200
    uid = [p for p in client.get("/api/admin/fd/team", headers=clinic["owner"]).json()["team"] if p["email"] == "gone@rd.test"][0]["id"]
    assert client.delete(f"/api/admin/fd/team/{uid}", headers=clinic["owner"]).status_code == 200
    assert client.get("/api/admin/fd/inbox", headers=g).status_code == 401  # existing session revoked
    assert client.post("/api/admin/auth/login", json={"tenant_slug": clinic["slug"], "email": "gone@rd.test",
                                                      "password": "pw-123456"}).status_code == 401
    n = len(invites)
    client.post("/api/admin/auth/code/request", json={"tenant_slug": clinic["slug"], "email": "gone@rd.test"})
    assert len(invites) == n  # no code emailed to a removed person
    r = client.post("/api/admin/fd/team", json={"email": "gone@rd.test"}, headers=clinic["owner"])
    assert r.status_code == 200 and r.json()["id"] == uid  # re-adding restores the same account


def test_cannot_remove_self_owner_or_other_clinic(client, clinic, invites):
    team = client.get("/api/admin/fd/team", headers=clinic["owner"]).json()["team"]
    me = [p for p in team if p["you"]][0]
    assert client.delete(f"/api/admin/fd/team/{me['id']}", headers=clinic["owner"]).status_code == 409
    create_user(clinic["id"], "adm@rd.test", password="pw-123456", role="admin")
    a = _login(client, clinic["slug"], "adm@rd.test")
    assert client.delete(f"/api/admin/fd/team/{me['id']}", headers=a).status_code == 403
    other = create_tenant(slug=f"o-{uuid.uuid4().hex[:6]}", name="Other")
    stranger = create_user(other.id, "s@o.test", password="pw-123456", role="member")
    assert client.delete(f"/api/admin/fd/team/{stranger.id}", headers=clinic["owner"]).status_code == 404


# ── Merged AI actions and routes ─────────────────────────────────────────


def test_ai_action_draft_and_rewrite_do_not_crash(client, clinic, monkeypatch):
    lead = create_lead(clinic["id"], {"name": "Pat", "email": "p@x.test", "message": "Need a cleaning"})
    h = clinic["owner"]
    r = client.post("/api/admin/fd/ai/action", json={"action": "draft", "lead_id": lead["id"], "instruction": "Offer Tuesday"}, headers=h)
    assert r.status_code == 200 and r.json()["result"]
    from saas import ai_engine
    monkeypatch.setattr(ai_engine, "_llm", lambda prompt, system="", schema=None: ({"text": "Shorter."}, "gemini"))
    assert client.post("/api/admin/fd/ai/shorten", json={"text": "A long message"}, headers=h).json()["body"] == "Shorter."
    assert client.post("/api/admin/fd/ai/action", json={"action": "warmer", "lead_id": lead["id"], "instruction": "Hi"},
                       headers=h).json()["result"] == "Shorter."


def test_react_desk_retired_and_settings_page_served(client):
    assert client.get("/desk").headers["location"] == "/frontdesk"
    assert client.get("/app/").headers["location"] == "/frontdesk"
    assert client.get("/frontdesk/settings").status_code == 200
