"""Go-live mailbox fixes: Einstein on 587, auto-replies and old mail are not patient replies, copies in Sent,
and the follow-up cadence resuming once the front desk answers a patient."""

from __future__ import annotations

import smtplib
import time
import uuid
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from saas import cadence, mailbox
from saas.database import connect, rows, utcnow
from saas.repositories import create_ai_draft, create_lead, create_tenant, create_user

CLINIC = "frontdesk@raleigh.test"
PATIENT = "pat@patient.test"


class FakeIMAP:
    """Named folders of raw messages. Supports SEARCH HEADER Message-ID and APPEND; records appends."""

    def __init__(self):
        self.folders = {"INBOX": [], "Sent": []}
        self.pending: list[bytes] = []  # filed in Sent by the "server" only after the first look
        self.appended: list[tuple] = []
        self.header_searches = 0
        self.fail_append = False
        self.current = None

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "Sent"']

    def select(self, folder, readonly=False):
        assert readonly
        self.current = self.folders[folder.strip('"')]
        return "OK", [str(len(self.current)).encode()]

    def response(self, code):
        return code, [b"1"]

    def uid(self, cmd, *args):
        if cmd == "SEARCH" and args[-1].startswith("HEADER Message-ID"):
            self.header_searches += 1
            if self.header_searches > 1 and self.pending:
                self.folders["Sent"] += self.pending
                self.pending = []
            mid = args[-1].split('"')[1].encode()
            return "OK", [" ".join(str(i + 1) for i, raw in enumerate(self.current) if mid in raw).encode()]
        if cmd == "SEARCH":
            return "OK", [" ".join(str(i + 1) for i in range(len(self.current))).encode()]
        return "OK", [(b"1 (BODY[] {n}", self.current[int(args[0]) - 1]), b")"]

    def append(self, folder, flags, date_time, message):
        if self.fail_append:
            raise OSError("APPEND refused")
        self.appended.append((folder, flags, message))
        self.folders[folder.strip('"')].append(message)
        return "OK", [b"APPEND completed"]

    def logout(self):
        pass


class FakeSMTP:
    """files_sent: the server files sent mail in Sent itself (True), a moment later ('late'), or not at all."""

    def __init__(self, imap=None, files_sent=False):
        self.imap, self.files_sent, self.sent = imap, files_sent, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send_message(self, msg):
        self.sent.append(msg)
        if self.files_sent == "late":
            self.imap.pending.append(bytes(msg))
        elif self.files_sent:
            self.imap.folders["Sent"].append(bytes(msg))


@pytest.fixture
def clinic(monkeypatch):
    """Einstein mailbox, connected and tested like the Settings page does; one enrolled patient."""
    t = create_tenant(slug=f"rd-{uuid.uuid4().hex[:6]}", name="Raleigh Dentistry")
    create_user(t.id, "owner@raleigh.test", password="pw-123456")
    imap = FakeIMAP()
    smtp = FakeSMTP(imap)
    monkeypatch.setattr(mailbox, "_smtp", lambda s: smtp)
    monkeypatch.setattr(mailbox, "_imap", lambda s: imap)
    monkeypatch.setattr(mailbox, "SENT_COPY_WAITS", (0, 0, 0))
    mailbox.connect_mailbox(t.id, "einstein", CLINIC, "pw", from_name="Raleigh Dentistry")
    assert mailbox.test_mailbox(t.id)["sent_folder"] == "Sent"
    lead = create_lead(t.id, {"name": "Pat Smith", "email": PATIENT, "service": "cleaning"})
    cadence.enroll(t.id, lead["id"])
    return SimpleNamespace(tid=t.id, lid=lead["id"], slug=t.slug, imap=imap, smtp=smtp)


def _send_first(ns) -> str:
    [did] = cadence.run_due(ns.tid)
    return mailbox.send_draft(ns.tid, did)["message_id"]


def _mail(sender=PATIENT, to=CLINIC, body="Tuesday at 3pm works for me", reply_to=None, date=None,
          headers=None) -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, to, "Re: Your appointment request"
    m["Message-ID"] = make_msgid(domain="patient.test")
    m["Date"] = date or formatdate()
    if reply_to:
        m["In-Reply-To"] = reply_to
        m["References"] = reply_to
    for k, v in (headers or {}).items():
        m[k] = v
    m.set_content(body)
    return bytes(m)


def _sync(ns, inbox=(), sent=()):
    ns.imap.folders["INBOX"] += list(inbox)
    ns.imap.folders["Sent"] += list(sent)
    return mailbox.sync_mailbox(ns.tid)


def _inbound(ns):
    return [m for m in mailbox.lead_thread(ns.tid, ns.lid) if m["direction"] == "in"]


def _reply_draft(ns) -> int:
    with connect() as c:
        return rows(c, "SELECT id FROM ai_drafts WHERE lead_id = ? AND source = 'reply' AND status = 'pending'",
                    ns.lid)[0]["id"]


def _draft(did) -> dict:
    with connect() as c:
        return rows(c, "SELECT status, cadence_step FROM ai_drafts WHERE id = ?", did)[0]


# ── 1. Einstein Mail sends on 587 with STARTTLS ──────────────────────────


def test_einstein_preset_is_587_starttls_with_full_address_login(monkeypatch):
    class SMTP:
        def __init__(self, host, port, **kw):
            self.host, self.port, self.tls, self.user = host, port, False, None
            SMTP.last = self

        def starttls(self, **kw):
            self.tls = True

        def login(self, user, password):
            self.user = user

    def no_ssl(*a, **kw):
        raise AssertionError("Einstein must not use implicit TLS on 465")
    monkeypatch.setattr(smtplib, "SMTP", SMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", no_ssl)
    t = create_tenant(slug=f"e-{uuid.uuid4().hex[:6]}", name="E")
    status = mailbox.connect_mailbox(t.id, "einstein", "FrontDesk@Raleigh.test", "pw")
    assert status["smtp_port"] == 587 and status["imap_port"] == 993
    assert status["providers"]["einstein"]["smtp_port"] == 587  # what the Settings page pre-fills
    mailbox._smtp(mailbox.get_settings_row(t.id))
    assert (SMTP.last.host, SMTP.last.port, SMTP.last.tls, SMTP.last.user) == \
           ("smtp.einsteinmail.com", 587, True, "frontdesk@raleigh.test")


# ── 2. Auto-replies and bounces are not patient replies ──────────────────


@pytest.mark.parametrize("sender,headers", [
    (PATIENT, {"Auto-Submitted": "auto-replied"}),
    (PATIENT, {"Auto-Submitted": "auto-generated; type=vacation"}),
    (PATIENT, {"X-Autoreply": "yes"}),
    (PATIENT, {"X-Autorespond": "Out of office"}),
    (PATIENT, {"Precedence": "bulk"}),
    (PATIENT, {"Precedence": "junk"}),
    (PATIENT, {"Precedence": "list"}),
    (PATIENT, {"Precedence": "auto_reply"}),
    ("Mail Delivery System <MAILER-DAEMON@mx.patient.test>", {}),
    ("postmaster@patient.test", {}),
])
def test_auto_replies_and_bounces_are_skipped(clinic, sender, headers):
    first = _send_first(clinic)
    stats = _sync(clinic, inbox=[_mail(sender=sender, reply_to=first, body="I'm out of the office until Monday.",
                                       headers=headers)])
    assert stats["inbound"] == 0 and stats["skipped"] == 1
    assert _inbound(clinic) == []
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "active"  # on_reply never ran
    with connect() as c:
        assert rows(c, "SELECT COUNT(1) n FROM frontdesk_tasks WHERE lead_id = ?", clinic.lid)[0]["n"] == 0


def test_delivery_report_is_skipped(clinic):
    first = _send_first(clinic)
    raw = (f"From: Mail System <notify@mx.patient.test>\r\nTo: {CLINIC}\r\nSubject: Undelivered Mail Returned\r\n"
           f"Message-ID: {make_msgid(domain='mx.patient.test')}\r\nIn-Reply-To: {first}\r\nDate: {formatdate()}\r\n"
           "MIME-Version: 1.0\r\nContent-Type: multipart/report; report-type=delivery-status; boundary=\"b1\"\r\n\r\n"
           "--b1\r\nContent-Type: text/plain\r\n\r\nDelivery to pat@patient.test failed.\r\n--b1--\r\n").encode()
    assert _sync(clinic, inbox=[raw])["inbound"] == 0
    assert _inbound(clinic) == [] and cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "active"


def test_auto_submitted_no_is_a_real_reply(clinic):
    first = _send_first(clinic)
    assert _sync(clinic, inbox=[_mail(reply_to=first, headers={"Auto-Submitted": "no"})])["inbound"] == 1
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "paused"


# ── 3. Older mail from the patient's address is not a reply ──────────────


def test_address_only_mail_from_before_the_lead_is_ignored(clinic):
    _send_first(clinic)
    old = _mail(body="Do you take Delta Dental?", date=formatdate(time.time() - 3 * 86400))
    stats = _sync(clinic, inbox=[old])
    assert stats["inbound"] == 0 and stats["skipped"] == 1 and _inbound(clinic) == []
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "active"
    stats = _sync(clinic, inbox=[_mail(body="Thursday morning works")])  # new mail, same address, no thread
    assert stats["inbound"] == 1 and [m["body"] for m in _inbound(clinic)] == ["Thursday morning works"]


def test_thread_reply_counts_whatever_its_date(clinic):
    first = _send_first(clinic)
    stats = _sync(clinic, inbox=[_mail(reply_to=first, date=formatdate(time.time() - 3 * 86400))])
    assert stats["inbound"] == 1


# ── 4. The clinic's own mail in INBOX is not a patient reply ─────────────


def test_clinic_own_mail_in_inbox_is_skipped(clinic):
    first = _send_first(clinic)
    copy_to_self = _mail(sender=f"Raleigh Dentistry <{CLINIC.upper()}>", to=PATIENT, reply_to=first,
                         body="Hi Pat, see you Tuesday")
    stats = _sync(clinic, inbox=[copy_to_self, _mail(sender=CLINIC, to=CLINIC, body="HeyJarvis test email")])
    assert stats["inbound"] == 0 and stats["skipped"] == 2 and _inbound(clinic) == []
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "active"


# ── 5. A copy of what HeyJarvis sends lands in the clinic's Sent folder ──


def test_test_email_adds_copy_when_server_does_not(clinic):
    out = mailbox.send_test_email(clinic.tid)
    assert out["ok"] and out["sent_copy"] == "added"
    assert mailbox.get_settings_row(clinic.tid)["append_sent"] == 1
    [(folder, flags, raw)] = clinic.imap.appended
    assert folder == '"Sent"' and flags == "(\\Seen)" and clinic.smtp.sent[-1]["Message-ID"].encode() in raw
    assert clinic.imap.header_searches == 1 + len(mailbox.SENT_COPY_WAITS)  # bounded retry before deciding

    _send_first(clinic)
    assert len(clinic.imap.appended) == 2  # every send now gets a copy
    assert clinic.smtp.sent[-1]["Message-ID"].encode() in clinic.imap.appended[-1][2]


@pytest.mark.parametrize("files_sent", [True, "late"])
def test_test_email_learns_server_files_sent_itself(clinic, files_sent):
    clinic.smtp.files_sent = files_sent
    assert mailbox.send_test_email(clinic.tid)["sent_copy"] == "server"
    assert mailbox.get_settings_row(clinic.tid)["append_sent"] == 0
    _send_first(clinic)
    assert clinic.imap.appended == []  # no duplicate copies


def test_unknown_server_gets_a_copy(clinic):
    assert mailbox.get_settings_row(clinic.tid)["append_sent"] is None  # test email never sent
    _send_first(clinic)
    assert len(clinic.imap.appended) == 1


@pytest.mark.parametrize("failure", ["append", "login"])
def test_copy_failure_never_fails_the_send(clinic, monkeypatch, failure):
    if failure == "append":
        clinic.imap.fail_append = True
    else:
        def refused(s):
            raise OSError("LOGIN failed")
        monkeypatch.setattr(mailbox, "_imap", refused)
    [did] = cadence.run_due(clinic.tid)
    out = mailbox.send_draft(clinic.tid, did)
    assert out["ok"] and clinic.smtp.sent
    with connect() as c:
        assert rows(c, "SELECT status FROM ai_drafts WHERE id = ?", did)[0]["status"] == "sent"
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["next_step"]["id"] == "follow_up_1"


@pytest.mark.parametrize("how", ["app_password", "google_sign_in", "custom_gmail_servers"])
def test_gmail_never_gets_an_appended_copy(monkeypatch, how):
    t = create_tenant(slug=f"g-{uuid.uuid4().hex[:6]}", name="G")
    if how == "app_password":
        mailbox.connect_gmail(t.id, CLINIC, "abcd efgh ijkl mnop")
    elif how == "google_sign_in":
        mailbox.connect_gmail_oauth(t.id, CLINIC, "rt-1")
    else:
        mailbox.connect_mailbox(t.id, "custom", CLINIC, "pw", smtp_host="smtp.gmail.com", imap_host="imap.gmail.com")
    with connect() as c:  # even if a value was learned somehow
        c.execute("UPDATE email_settings SET append_sent = 1, sent_folder = '[Gmail]/Sent Mail' WHERE tenant_id = ?",
                  (t.id,))
    imap = FakeIMAP()
    logins = []
    monkeypatch.setattr(mailbox, "_smtp", lambda s: FakeSMTP(imap))
    monkeypatch.setattr(mailbox, "_imap", lambda s: logins.append(1) or imap)
    assert mailbox.send_test_email(t.id)["sent_copy"] is None
    lead = create_lead(t.id, {"name": "Pat", "email": PATIENT})
    mailbox.send_draft(t.id, create_ai_draft(t.id, lead_id=lead["id"], subject="Hi", body="Hello")["id"])
    assert logins == [] and imap.appended == []


def test_appended_copy_is_not_recorded_twice_or_treated_as_new_outbound(clinic):
    _send_first(clinic)
    assert len(clinic.imap.folders["Sent"]) == 1  # the appended copy
    with connect() as c:
        c.execute("UPDATE cadence_enrollments SET anchor_at = '2026-01-01T00:00:00' WHERE lead_id = ?", (clinic.lid,))
    before = cadence.get_enrollment(clinic.tid, clinic.lid)
    stats = _sync(clinic)
    assert stats["outbound"] == 0
    assert [m["direction"] for m in mailbox.lead_thread(clinic.tid, clinic.lid)] == ["out"]
    after = cadence.get_enrollment(clinic.tid, clinic.lid)
    assert (after["anchor_at"], after["step_index"], after["status"]) == \
           (before["anchor_at"], before["step_index"], before["status"])


def test_cadence_moves_on_before_the_sent_copy(clinic, monkeypatch):
    """Filing the Sent copy is a slow IMAP round trip: a scheduler tick during it must not re-draft the step."""
    [did] = cadence.run_due(clinic.tid)
    seen = {}

    def imap_during_copy(s):
        with connect() as c:
            seen["lead"] = rows(c, "SELECT status FROM leads WHERE id = ?", clinic.lid)[0]["status"]
        seen["draft"] = _draft(did)["status"]
        seen["thread"] = len(mailbox.lead_thread(clinic.tid, clinic.lid))
        seen["next"] = cadence.get_enrollment(clinic.tid, clinic.lid)["next_step"]["id"]
        seen["tick"] = cadence.run_due(clinic.tid)
        return clinic.imap
    monkeypatch.setattr(mailbox, "_imap", imap_during_copy)
    mailbox.send_draft(clinic.tid, did)
    assert seen == {"lead": "contacted", "draft": "sent", "thread": 1, "next": "follow_up_1", "tick": []}
    assert len(clinic.imap.appended) == 1


def test_scheduler_rereads_an_enrollment_the_desk_moved_mid_run(clinic, monkeypatch):
    """A run drafts slowly (AI); a step the desk sends meanwhile must not be drafted again from a stale read."""
    other = create_lead(clinic.tid, {"name": "Lee Park", "email": "lee@patient.test"})
    cadence.enroll(clinic.tid, other["id"])
    lees = cadence.draft_for_step(clinic.tid, other["id"], cadence.get_cadence(clinic.tid)["steps"][0])
    real = cadence.draft_for_step

    def slow_draft(tid, lid, step):
        if lid == clinic.lid:  # the desk sends Lee's first reply while Pat's is being drafted
            mailbox.send_draft(clinic.tid, lees)
        return real(tid, lid, step)
    monkeypatch.setattr(cadence, "draft_for_step", slow_draft)
    assert len(cadence.run_due(clinic.tid)) == 1  # Pat's first reply only
    with connect() as c:
        assert rows(c, "SELECT id FROM ai_drafts WHERE lead_id = ? AND status = 'pending'", other["id"]) == []
    assert cadence.get_enrollment(clinic.tid, other["id"])["next_step"]["id"] == "follow_up_1"


# ── 6. A reply's pause ends when the front desk answers ──────────────────


def test_desk_answer_resumes_cadence_paused_by_reply(clinic):
    first = _send_first(clinic)
    _sync(clinic, inbox=[_mail(reply_to=first)])  # default '*' rule: pause + draft_reply + task
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "paused"
    mailbox.send_draft(clinic.tid, _reply_draft(clinic))
    enr = cadence.get_enrollment(clinic.tid, clinic.lid)
    assert enr["status"] == "active" and enr["next_step"]["id"] == "follow_up_1"
    assert cadence.run_due(clinic.tid, now=utcnow() + timedelta(hours=23)) == []  # clock restarted at the answer
    assert len(cadence.run_due(clinic.tid, now=utcnow() + timedelta(hours=25))) == 1  # patient went quiet


def test_staff_pause_is_not_resumed_by_desk_email(clinic):
    from saas.main import app
    client = TestClient(app)
    tok = client.post("/api/admin/auth/login", json={"tenant_slug": clinic.slug, "email": "owner@raleigh.test",
                                                     "password": "pw-123456"}).json()["access_token"]
    first = _send_first(clinic)
    r = client.post(f"/api/admin/fd/leads/{clinic.lid}/cadence", json={"action": "pause"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.json()["status"] == "paused"
    _sync(clinic, inbox=[_mail(reply_to=first)])  # the reply's pause must not take over the staff pause
    mailbox.send_draft(clinic.tid, _reply_draft(clinic))
    enr = cadence.get_enrollment(clinic.tid, clinic.lid)
    assert enr["status"] == "paused" and "front desk" in enr["reason"]


def test_stopped_cadence_stays_stopped_after_reply_and_answer(clinic):
    first = _send_first(clinic)
    cadence.set_state(clinic.tid, clinic.lid, "stopped", reason="stop by front desk")
    _sync(clinic, inbox=[_mail(reply_to=first)])
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "stopped"
    mailbox.send_draft(clinic.tid, _reply_draft(clinic))
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "stopped"


def test_desk_email_in_sent_resumes_only_if_after_the_reply(clinic):
    first = _send_first(clinic)
    earlier = _mail(sender=CLINIC, to=PATIENT, body="Reminder: bring your insurance card",
                    date=formatdate(time.time() - 3600))
    _sync(clinic, inbox=[_mail(reply_to=first)], sent=[earlier])  # reply and an older desk email in one sync
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "paused"
    answer = _mail(sender=CLINIC, to=PATIENT, body="Tuesday at 3pm is booked", date=formatdate(time.time() + 60))
    assert _sync(clinic, sent=[answer])["outbound"] == 1
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "active"


# ── 6b. The desk's own answer is the first reply ─────────────────────────


def test_desk_answer_before_first_reply_was_sent_resumes_at_follow_up(clinic):
    """The patient wrote in before the first reply was approved: the desk's answer replaces it."""
    [first] = cadence.run_due(clinic.tid)
    _sync(clinic, inbox=[_mail(body="I just filled in the form. Is Thursday possible?")])
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "paused"
    mailbox.send_draft(clinic.tid, _reply_draft(clinic))
    enr = cadence.get_enrollment(clinic.tid, clinic.lid)
    assert (enr["status"], enr["next_step"]["id"]) == ("active", "follow_up_1")
    assert _draft(first)["status"] == "discarded"
    assert cadence.run_due(clinic.tid) == []  # no second "thanks for reaching out"
    assert cadence.run_due(clinic.tid, now=utcnow() + timedelta(hours=23)) == []
    [nudge] = cadence.run_due(clinic.tid, now=utcnow() + timedelta(hours=25))
    assert _draft(nudge)["cadence_step"] == "follow_up_1"


def test_typed_reply_before_first_reply_replaces_it(clinic):
    [first] = cadence.run_due(clinic.tid)
    typed = create_ai_draft(clinic.tid, lead_id=clinic.lid, subject="Your appointment request",
                            body="Hi Pat, we have Tuesday at 3pm or Wednesday at 10am. Which works?")
    out = mailbox.send_draft(clinic.tid, typed["id"])
    enr = cadence.get_enrollment(clinic.tid, clinic.lid)
    assert (enr["status"], enr["next_step"]["id"]) == ("active", "follow_up_1")
    assert _draft(first)["status"] == "discarded"  # no contradictory first reply left to approve
    assert cadence.run_due(clinic.tid) == []
    _sync(clinic, inbox=[_mail(reply_to=out["message_id"], body="Wednesday at 10am please")])
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "paused"
    mailbox.send_draft(clinic.tid, _reply_draft(clinic))
    enr = cadence.get_enrollment(clinic.tid, clinic.lid)
    assert (enr["status"], enr["next_step"]["id"]) == ("active", "follow_up_1")
    assert cadence.run_due(clinic.tid) == []


def test_webmail_answer_before_first_reply_replaces_it(clinic):
    [first] = cadence.run_due(clinic.tid)
    answer = _mail(sender=CLINIC, to=PATIENT, body="Hi Pat, Tuesday at 3pm is open", date=formatdate(time.time() + 60))
    assert _sync(clinic, sent=[answer])["outbound"] == 1
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["next_step"]["id"] == "follow_up_1"
    assert _draft(first)["status"] == "discarded" and cadence.run_due(clinic.tid) == []


def test_desk_mail_from_before_the_request_is_not_a_first_reply(clinic):
    [first] = cadence.run_due(clinic.tid)
    old = _mail(sender=CLINIC, to=PATIENT, body="Reminder: cleaning next month", date=formatdate(time.time() - 3 * 86400))
    assert _sync(clinic, sent=[old])["outbound"] == 1  # the first sync looks back 14 days
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["next_step"]["id"] == "first_reply"
    assert _draft(first)["status"] == "pending"


def test_delayed_first_step_is_a_follow_up_and_stays(clinic):
    cadence.save_cadence(clinic.tid, {**cadence.get_cadence(clinic.tid), "steps": [
        {"id": "nudge", "name": "Nudge", "delay_hours": 24, "mode": "template", "template": "Hi {{name}}, still keen?"}]})
    mailbox.send_draft(clinic.tid, create_ai_draft(clinic.tid, lead_id=clinic.lid, subject="Hi", body="Hello Pat")["id"])
    enr = cadence.get_enrollment(clinic.tid, clinic.lid)
    assert (enr["status"], enr["next_step"]["id"]) == ("active", "nudge")
    [nudge] = cadence.run_due(clinic.tid, now=utcnow() + timedelta(hours=25))
    assert _draft(nudge)["cadence_step"] == "nudge"


# ── 7. set_status with a closing status stops the cadence ────────────────


@pytest.mark.parametrize("actions", [["set_status:booked"], ["set_status:closed", "pause"]])
def test_rule_closing_status_stops_cadence(clinic, actions):
    cadence.save_cadence(clinic.tid, {**cadence.get_cadence(clinic.tid), "on_reply": [{"when": ["*"], "do": actions}]})
    first = _send_first(clinic)
    _sync(clinic, inbox=[_mail(reply_to=first)])
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "stopped"
    with connect() as c:
        assert rows(c, "SELECT status FROM leads WHERE id = ?", clinic.lid)[0]["status"] == actions[0].split(":")[1]


def test_rule_open_status_keeps_cadence_going(clinic):
    cadence.save_cadence(clinic.tid, {**cadence.get_cadence(clinic.tid),
                                      "on_reply": [{"when": ["*"], "do": ["set_status:qualified"]}]})
    first = _send_first(clinic)
    _sync(clinic, inbox=[_mail(reply_to=first)])
    assert cadence.get_enrollment(clinic.tid, clinic.lid)["status"] == "active"
