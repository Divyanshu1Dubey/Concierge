"""Clinic mailbox sending, reply tracking and the follow-up cadence, with a fake Gmail."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid

import pytest
from fastapi.testclient import TestClient

from saas import cadence, mailbox
from saas.database import connect, rows
from saas.repositories import create_api_key, create_lead, create_tenant, create_user

CLINIC = "frontdesk@clinic.test"
PATIENT = "pat@patient.test"


class FakeSMTP:
    sent: list[EmailMessage] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


class FakeIMAP:
    """Two folders of raw messages; records how it was used."""

    def __init__(self, inbox: list[bytes], sent: list[bytes] | None = None):
        self.folders = {"INBOX": inbox, '"[Gmail]/Sent Mail"': sent or []}
        self.current = None
        self.calls: list[tuple] = []

    def select(self, folder, readonly=False):
        self.calls.append(("select", folder, readonly))
        self.current = self.folders[folder]
        return "OK", [b"1"]

    def response(self, code):
        return code, [b"42"]

    def uid(self, cmd, *args):
        self.calls.append(("uid", cmd, args))
        if cmd == "SEARCH":
            return "OK", [" ".join(str(i + 1) for i in range(len(self.current))).encode()]
        uid = int(args[0])
        return "OK", [(b"1 (BODY[] {n}", self.current[uid - 1]), b")"]

    def logout(self):
        pass


@pytest.fixture
def clinic(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(mailbox, "_smtp", lambda s: FakeSMTP())
    t = create_tenant(slug=f"c-{uuid.uuid4().hex[:6]}", name="Bright Smiles")
    create_user(t.id, "owner@clinic.test", password="pw-123456")
    mailbox.connect_gmail(t.id, CLINIC, "abcd efgh ijkl mnop", from_name="Bright Smiles Dental")
    lead = create_lead(t.id, {"name": "Pat Smith", "email": PATIENT, "service": "cleaning",
                              "intent": "appointment_request"})
    cadence.enroll(t.id, lead["id"])
    return t.id, lead["id"]


def _reply(to_msg_id: str | None, body: str, sender: str = PATIENT, subject: str = "Re: Your appointment request") -> bytes:
    m = EmailMessage()
    m["From"] = f"Pat <{sender}>"
    m["To"] = CLINIC
    m["Subject"] = subject
    m["Message-ID"] = make_msgid(domain="patient.test")
    m["Date"] = "Mon, 05 Oct 2026 10:00:00 -0400"
    if to_msg_id:
        m["In-Reply-To"] = to_msg_id
        m["References"] = to_msg_id
    m.set_content(body)
    return bytes(m)


def _first_draft(tid, lid):
    ids = cadence.run_due(tid)
    assert len(ids) == 1
    return ids[0]


# ── Sending ──────────────────────────────────────────────────────────────


def test_credentials_are_encrypted_at_rest(clinic):
    tid, _ = clinic
    s = mailbox.get_settings_row(tid)
    assert "abcd" not in (s["smtp_password_enc"] or "") and s["smtp_host"] == "smtp.gmail.com"
    assert mailbox.mailbox_status(tid)["connected"] is True


def test_send_draft_goes_from_clinic_to_patient(clinic):
    tid, lid = clinic
    did = _first_draft(tid, lid)
    out = mailbox.send_draft(tid, did, body="Hi Pat, what times work?")
    msg = FakeSMTP.sent[-1]
    assert msg["To"] == PATIENT and CLINIC in msg["From"] and "Bright Smiles Dental" in msg["From"]
    assert msg.get_content().strip() == "Hi Pat, what times work?"
    thread = mailbox.lead_thread(tid, lid)
    assert [m["direction"] for m in thread] == ["out"] and thread[0]["message_id"] == out["message_id"]
    with connect() as c:
        assert rows(c, "SELECT status FROM ai_drafts WHERE id = ?", did)[0]["status"] == "sent"
        assert rows(c, "SELECT status FROM leads WHERE id = ?", lid)[0]["status"] == "contacted"
    assert cadence.get_enrollment(tid, lid)["next_step"]["id"] == "follow_up_1"


def test_follow_up_stays_in_same_thread(clinic):
    tid, lid = clinic
    first = mailbox.send_draft(tid, _first_draft(tid, lid))
    later = datetime.now() + timedelta(hours=25)
    [did] = cadence.run_due(tid, now=later)
    mailbox.send_draft(tid, did)
    msg = FakeSMTP.sent[-1]
    assert msg["In-Reply-To"] == first["message_id"]
    assert msg["Subject"].startswith("Re: ")


def test_cannot_send_twice(clinic):
    tid, lid = clinic
    did = _first_draft(tid, lid)
    mailbox.send_draft(tid, did)
    with pytest.raises(mailbox.MailboxError):
        mailbox.send_draft(tid, did)


def test_smtp_failure_marks_draft_failed(clinic, monkeypatch):
    tid, lid = clinic
    did = _first_draft(tid, lid)

    def boom(s):
        raise OSError("Username and Password not accepted")
    monkeypatch.setattr(mailbox, "_smtp", boom)
    with pytest.raises(mailbox.MailboxError, match="app password"):
        mailbox.send_draft(tid, did)
    with connect() as c:
        assert rows(c, "SELECT status FROM ai_drafts WHERE id = ?", did)[0]["status"] == "failed"


# ── Cadence ──────────────────────────────────────────────────────────────


def test_first_draft_is_created_once_and_waits_for_approval(clinic):
    tid, lid = clinic
    did = _first_draft(tid, lid)
    assert cadence.run_due(tid) == []  # pending draft blocks duplicates
    with connect() as c:
        d = rows(c, "SELECT * FROM ai_drafts WHERE id = ?", did)[0]
    assert d["status"] == "pending" and d["cadence_step"] == "first_reply" and "Pat" in d["body"]
    assert FakeSMTP.sent == []  # nothing is emailed without approval


def test_follow_up_waits_for_delay(clinic):
    tid, lid = clinic
    mailbox.send_draft(tid, _first_draft(tid, lid))
    assert cadence.run_due(tid, now=datetime.now() + timedelta(hours=23)) == []
    assert len(cadence.run_due(tid, now=datetime.now() + timedelta(hours=25))) == 1


def test_discarding_a_step_skips_it(clinic):
    tid, lid = clinic
    from saas.main import app
    mailbox.send_draft(tid, _first_draft(tid, lid))
    [did] = cadence.run_due(tid, now=datetime.now() + timedelta(hours=25))
    with connect() as c:
        c.execute("UPDATE ai_drafts SET status='discarded' WHERE id = ?", (did,))
    cadence.on_discard(tid, lid, "follow_up_1")
    assert cadence.get_enrollment(tid, lid)["next_step"]["id"] == "follow_up_2"


def test_cadence_completes_after_last_step(clinic):
    tid, lid = clinic
    t = datetime.now()
    mailbox.send_draft(tid, _first_draft(tid, lid))
    for hours in (25, 25 + 73, 25 + 73 + 169):
        [did] = cadence.run_due(tid, now=t + timedelta(hours=hours))
        mailbox.send_draft(tid, did)
        with connect() as c:  # pretend the email went out at that time
            c.execute("UPDATE cadence_enrollments SET anchor_at = ? WHERE lead_id = ?",
                      ((t + timedelta(hours=hours)).isoformat(timespec="seconds"), lid))
    assert cadence.get_enrollment(tid, lid)["status"] == "completed"


def test_invalid_cadence_rejected():
    bad = {"steps": [{"id": "a", "delay_hours": 0}], "on_reply": [{"when": ["booked"], "do": ["explode"]}]}
    with pytest.raises(ValueError, match="unknown action"):
        cadence.validate(bad)
    with pytest.raises(ValueError, match="skip"):
        cadence.validate({"steps": [{"id": "a"}], "on_reply": [{"when": ["*"], "do": ["skip:nope"]}]}) or None


# ── Reply tracking ───────────────────────────────────────────────────────


def _sync_with(monkeypatch, tid, inbox, sent=None):
    fake = FakeIMAP(inbox, sent)
    monkeypatch.setattr(mailbox, "_imap", lambda s: fake)
    return mailbox.sync_mailbox(tid), fake


def test_reply_booked_stops_cadence_and_marks_booked(clinic, monkeypatch):
    tid, lid = clinic
    first = mailbox.send_draft(tid, _first_draft(tid, lid))
    stats, fake = _sync_with(monkeypatch, tid, [
        _reply(first["message_id"], "Thanks! I already booked by phone.\n\nOn Mon, Oct 5 Bright Smiles wrote:\n> Hi Pat"),
    ])
    assert stats["inbound"] == 1
    inbound = [m for m in mailbox.lead_thread(tid, lid) if m["direction"] == "in"][0]
    assert inbound["body"] == "Thanks! I already booked by phone."  # quoted history stripped
    assert inbound["classification"]["intent"] == "booked"
    assert cadence.get_enrollment(tid, lid)["status"] == "stopped"
    with connect() as c:
        assert rows(c, "SELECT status FROM leads WHERE id = ?", lid)[0]["status"] == "booked"


def test_sync_is_read_only_and_skips_unrelated_mail(clinic, monkeypatch):
    tid, lid = clinic
    mailbox.send_draft(tid, _first_draft(tid, lid))
    stats, fake = _sync_with(monkeypatch, tid, [_reply(None, "Your invoice", sender="vendor@supplies.test",
                                                       subject="Invoice 123")])
    assert stats["inbound"] == 0 and stats["skipped"] == 1
    assert all(c[2] is True for c in fake.calls if c[0] == "select")  # readonly
    assert all(any("BODY.PEEK[]" in a for a in c[2]) for c in fake.calls if c[:2] == ("uid", "FETCH"))  # never marks read
    with connect() as c:
        assert rows(c, "SELECT COUNT(1) n FROM email_messages WHERE direction = 'in'")[0]["n"] == 0


def test_sync_is_incremental(clinic, monkeypatch):
    tid, lid = clinic
    first = mailbox.send_draft(tid, _first_draft(tid, lid))
    msgs = [_reply(first["message_id"], "Tuesday at 3pm works")]
    _sync_with(monkeypatch, tid, msgs)
    stats, _ = _sync_with(monkeypatch, tid, msgs)
    assert stats["inbound"] == 0
    assert len([m for m in mailbox.lead_thread(tid, lid) if m["direction"] == "in"]) == 1


def test_any_other_reply_pauses_and_queues_ai_reply_and_task(clinic, monkeypatch):
    tid, lid = clinic
    first = mailbox.send_draft(tid, _first_draft(tid, lid))
    later = datetime.now() + timedelta(hours=25)
    cadence.run_due(tid, now=later)  # a follow-up draft is waiting
    _sync_with(monkeypatch, tid, [_reply(first["message_id"], "Tuesday at 3pm works for me")])
    enr = cadence.get_enrollment(tid, lid)
    assert enr["status"] == "paused"
    with connect() as c:
        drafts = rows(c, "SELECT source, status FROM ai_drafts WHERE lead_id = ? ORDER BY id", lid)
        tasks = rows(c, "SELECT title FROM frontdesk_tasks WHERE lead_id = ?", lid)
    assert {"source": "cadence", "status": "discarded"} in drafts  # stale follow-up can't be sent
    assert {"source": "reply", "status": "pending"} in drafts
    assert tasks and "replied" in tasks[0]["title"]


def test_custom_rule_skips_one_email(clinic, monkeypatch):
    """'If the patient replies with times, drop email 2' — the cadence keeps going without it."""
    tid, lid = clinic
    cfg = cadence.get_cadence(tid)
    cfg["on_reply"] = [{"when": ["wants_appointment"], "do": ["skip:follow_up_1"]}]
    cadence.save_cadence(tid, cfg)
    first = mailbox.send_draft(tid, _first_draft(tid, lid))
    _sync_with(monkeypatch, tid, [_reply(first["message_id"], "Thursday morning works")])
    enr = cadence.get_enrollment(tid, lid)
    assert enr["status"] == "active" and "follow_up_1" in enr["skipped"]
    assert enr["next_step"]["id"] == "follow_up_2"


def test_email_desk_sent_from_gmail_resets_clock(clinic, monkeypatch):
    tid, lid = clinic
    mailbox.send_draft(tid, _first_draft(tid, lid))
    with connect() as c:
        c.execute("UPDATE cadence_enrollments SET anchor_at = '2020-01-01T00:00:00' WHERE lead_id = ?", (lid,))
    desk = EmailMessage()
    desk["From"], desk["To"], desk["Subject"] = CLINIC, PATIENT, "Quick question"
    desk["Message-ID"], desk["Date"] = make_msgid(domain="clinic.test"), "Mon, 05 Oct 2026 11:00:00 -0400"
    desk.set_content("Hi Pat, calling you now")
    stats, _ = _sync_with(monkeypatch, tid, [], sent=[bytes(desk)])
    assert stats["outbound"] == 1
    assert cadence.get_enrollment(tid, lid)["anchor_at"] > "2026"
    assert cadence.run_due(tid) == []  # clock restarted, follow-up 1 not due yet


# ── Through the HTTP API ─────────────────────────────────────────────────


def test_front_desk_send_flow_over_http(clinic, monkeypatch):
    tid, lid = clinic
    from saas.main import app
    from saas.repositories import get_tenant
    client = TestClient(app)
    tok = client.post("/api/admin/auth/login", json={"tenant_slug": get_tenant(tid).slug,
                                                     "email": "owner@clinic.test", "password": "pw-123456"}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.post("/api/admin/fd/cadence/run", headers=h).json()["drafts_created"] == 1
    view = client.get(f"/api/admin/fd/leads/{lid}/emails", headers=h).json()
    did = view["drafts"][0]["id"]
    assert view["cadence"]["next_step"]["id"] == "first_reply"
    r = client.post(f"/api/admin/fd/drafts/{did}/send", json={"body": "Edited before sending"}, headers=h)
    assert r.status_code == 200, r.text
    assert FakeSMTP.sent[-1].get_content().strip() == "Edited before sending"
    view = client.get(f"/api/admin/fd/leads/{lid}/emails", headers=h).json()
    assert len(view["messages"]) == 1 and view["drafts"] == []
    assert client.post(f"/api/admin/fd/leads/{lid}/cadence", json={"action": "stop"}, headers=h).json()["status"] == "stopped"
    r = client.put("/api/admin/fd/cadence", json={"steps": [], "on_reply": []}, headers=h)
    assert r.status_code == 422


def test_widget_lead_is_enrolled():
    from saas.main import app
    t = create_tenant(slug=f"w-{uuid.uuid4().hex[:6]}", name="W")
    key = create_api_key(t.id, "w", "s")
    client = TestClient(app)
    r = client.post("/api/v1/public/leads", params={"client_key": key.public_key},
                    json={"name": "Lee", "email": "lee@x.test", "intent": "appointment_request"})
    assert cadence.get_enrollment(t.id, r.json()["lead_id"])["status"] == "active"


# ── Widget chat ──────────────────────────────────────────────────────────


def _chat(messages):
    from saas.main import app
    t = create_tenant(slug=f"chat-{uuid.uuid4().hex[:6]}", name="Chat")
    key = create_api_key(t.id, "w", "s")
    client = TestClient(app)
    conv = client.post("/api/v1/public/conversations", params={"client_key": key.public_key}).json()
    out = None
    for m in messages:
        out = client.post(f"/api/v1/public/conversations/{conv['conversation_id']}/messages",
                          params={"client_key": key.public_key}, json={"message": m}).json()
    return out


def test_chat_rules_handle_natural_intro():
    out = _chat(["Hi, I'm Sam, need a cleaning, sam@x.test"])
    assert out["state"] == "submitted" and out["fields"]["name"] == "Sam"


def test_chat_rules_do_not_mistake_pain_for_a_name():
    out = _chat(["I'm in pain, my tooth is swollen"])
    assert "name" not in out["fields"] and out["fields"]["intent"] == "emergency"


def test_chat_short_answer_to_name_question():
    out = _chat(["I need a cleaning", "sam smith", "sam@x.test"])
    assert out["state"] == "submitted" and out["fields"]["name"] == "Sam Smith"


def test_chat_uses_gemini_extraction(monkeypatch):
    from saas import ai_engine
    seen = {}

    def fake_extract(message, known, last_question):
        seen["called"] = True
        return {"name": "Samantha Lee", "email": "sam@x.test", "phone": "919-555-0100",
                "intent": "appointment_request", "preferred_date": "next Tuesday", "preferred_time": "after 3pm"}
    monkeypatch.setattr(ai_engine, "extract_intake", fake_extract)
    out = _chat(["hey it's samantha lee, can I get in next tuesday after 3? 919 555 0100, sam@x.test"])
    assert seen and out["state"] == "submitted"
    assert out["fields"]["preferred_date"] == "next Tuesday" and out["fields"]["name"] == "Samantha Lee"
    with connect() as c:
        lead = rows(c, "SELECT * FROM leads ORDER BY id DESC LIMIT 1")[0]
    assert lead["preferred_time"] == "after 3pm" and lead["phone"] == "919-555-0100"


def test_chat_asks_what_to_schedule_first_with_choices():
    out = _chat(["Hi there"])
    assert "schedule" in out["reply"].lower()
    assert "Checkup & cleaning" in out["options"] and "Something else" in out["options"]


def test_tapping_a_choice_answers_and_moves_on():
    out = _chat(["Hi there", "Checkup & cleaning"])
    assert "options" not in out and "name" in out["reply"].lower()
    out = _chat(["Hi there", "Something else", "Sam Lee", "sam@x.test"])
    assert out["state"] == "submitted"


def test_clinic_can_set_its_own_choices():
    from saas.conversation import ConversationEngine
    eng = ConversationEngine({"service_options": ["Botox", "Fillers"]})
    assert eng.options_for("service") == ["Botox", "Fillers"]
    assert eng.options_for("email") == []


def test_tapped_choice_is_saved_as_the_service():
    _chat(["Hi there", "Checkup & cleaning", "Sam Lee", "sam@x.test"])
    with connect() as c:
        lead = rows(c, "SELECT service FROM leads ORDER BY id DESC LIMIT 1")[0]
    assert lead["service"] == "Checkup & cleaning"


def test_greeting_offers_choices_and_one_tap_skips_to_contact_details():
    from saas.main import app
    t = create_tenant(slug=f"greet-{uuid.uuid4().hex[:6]}", name="G")
    key = create_api_key(t.id, "w", "s")
    client = TestClient(app)
    start = client.post("/api/v1/public/conversations", params={"client_key": key.public_key}).json()
    assert start["options"][:4] == ["Checkup & cleaning", "Implants", "Restorative (fillings, crowns)", "Emergency"]
    r = client.post(f"/api/v1/public/conversations/{start['conversation_id']}/messages",
                    params={"client_key": key.public_key}, json={"message": "Implants"}).json()
    assert "name" in r["reply"].lower() and "options" not in r


def test_demo_mode_send_reply_and_fast_forward():
    """Local demo with no mailbox: the whole semi-automated loop works without real email."""
    t = create_tenant(slug=f"demo-{uuid.uuid4().hex[:6]}", name="Demo")
    lead = create_lead(t.id, {"name": "Pat Smith", "email": PATIENT, "service": "cleaning"})
    cadence.enroll(t.id, lead["id"])
    assert mailbox.demo_mode(t.id)
    [did] = cadence.run_due(t.id)
    assert mailbox.send_draft(t.id, did)["demo"] is True
    assert cadence.fast_forward(t.id, 25)  # follow-up 1 drafted
    result = mailbox.simulate_reply(t.id, lead["id"], "Already booked, thanks!")
    assert result["intent"] == "booked" and cadence.get_enrollment(t.id, lead["id"])["status"] == "stopped"
    assert [m["source"] for m in mailbox.lead_thread(t.id, lead["id"])] == ["demo", "demo"]


def test_email_address_does_not_overwrite_chosen_service():
    _chat(["Implants", "Avi Sanghavi", "avi@example.test"])
    with connect() as c:
        lead = rows(c, "SELECT service FROM leads ORDER BY id DESC LIMIT 1")[0]
    assert lead["service"] == "Implants"
