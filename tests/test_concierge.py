from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from concierge import api, mailer, schedule, store
from concierge.compose import SLOT_CLOSE, SLOT_OPEN, compose, fill_slot, has_slot
from concierge.config import load_config
from concierge.models import PatientRequest, RequestType, Triage
from concierge.pipeline import build_draft, process, receive
from concierge.rules import plan_booking

CFG = load_config()
TZ = schedule.tz(CFG)
# A Monday at 07:00 clinic time, so the whole day is open in tests.
MONDAY = datetime(2026, 10, 5, 7, 0, tzinfo=TZ)


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(schedule, "now", lambda cfg: MONDAY)
    return MONDAY


def draft_for(msg, **kw):
    return build_draft(PatientRequest(message=msg, **kw), CFG, use_llm=False)


# --- booking rules from the one-pager ----------------------------------------------

def test_new_patient_is_90_min_split_with_fallback_column():
    plan = plan_booking(Triage(request_type=RequestType.NEW_PATIENT, reason="x"), CFG)
    assert plan.minutes == 90
    assert "30 Dr + 60 Hyg" in plan.desk_hint and "column 2" in plan.desk_hint


def test_emergency_is_60_min_same_day():
    plan = plan_booking(Triage(request_type=RequestType.EMERGENCY, reason="x"), CFG)
    assert plan.minutes == 60 and plan.same_day and "TODAY" in plan.desk_hint


def test_policy_lines_in_booking_drafts():
    body = draft_for("I'm a new patient, can I book a cleaning?").body
    assert "48 hours" in body and "$65" in body


def test_financing_only_when_asked():
    assert "Cherry" not in draft_for("new patient, want a cleaning").body
    body = draft_for("new patient, how much does whitening cost? any financing?").body
    assert "Cherry" in body and "CareCredit" in body


def test_emergency_has_safety_warning_and_no_fee_pitch():
    body = draft_for("my face is swollen and it hurts").body
    assert "911" in body and "$65" not in body


# --- keyword triage ------------------------------------------------------------------

@pytest.mark.parametrize("msg,kind", [
    ("My tooth is killing me, really bad pain since last night", RequestType.EMERGENCY),
    ("I chipped my front tooth", RequestType.EMERGENCY),
    ("I'd like to cancel my appointment Thursday", RequestType.CANCEL),
    ("Can I reschedule my appointment to next week?", RequestType.RESCHEDULE),
    ("need to push my cleaning on Thursday to next week", RequestType.RESCHEDULE),
    ("I just moved to Raleigh and need a dentist, first visit", RequestType.NEW_PATIENT),
    ("Time for my cleaning, can I book one?", RequestType.EXISTING_PATIENT),
    ("Do you take Delta Dental PPO?", RequestType.QUESTION),
])
def test_heuristic_types(msg, kind):
    assert draft_for(msg).triage.request_type == kind


def test_heuristic_reads_preferred_times():
    assert "Tuesday afternoons" in draft_for("cleaning please, Tuesday afternoons work").triage.preferred_times


def test_form_fields_win_and_email_extracted():
    d = draft_for("new patient here, reach me at pat@example.com", name="Pat Lee")
    assert d.to == "pat@example.com" and d.body.startswith("Hi Pat,")


# --- the slot: hint lives inside it and disappears ----------------------------------

@pytest.mark.parametrize("msg", ["new patient please", "tooth pain", "book a cleaning", "reschedule my appointment",
                                 "cancel my appt", "do you take insurance?"])
def test_exactly_one_slot_and_hint_only_inside_it(msg):
    body = draft_for(msg).body
    assert body.count(SLOT_OPEN) == 1 and body.count(SLOT_CLOSE) == 1
    sent = fill_slot(body, "Tuesday Oct 7 at 9:00 AM")
    assert not has_slot(sent)
    for internal in ("Hyg", "column", "TYPE", "pt prefers"):
        assert internal not in sent


def test_preferred_times_go_in_slot():
    t = Triage(request_type=RequestType.NEW_PATIENT, reason="x", preferred_times="Tue mornings")
    assert "pt prefers: Tue mornings" in compose(t, plan_booking(t, CFG), CFG).body


# --- AI fallback chain ---------------------------------------------------------------

def test_fallback_to_second_gemini_then_events(monkeypatch):
    import concierge.triage as tr

    calls, events = [], []
    def fake(req, model, emit):
        calls.append(model)
        if model == tr.MODEL:
            raise RuntimeError("503 UNAVAILABLE")
        emit("thought", text="Cracked tooth means urgent.")
        return Triage(request_type=RequestType.EMERGENCY, reason="x", triaged_by="gemini")
    monkeypatch.setattr(tr, "_triage_llm", lambda req, model, emit=None: fake(req, model, emit))
    t = tr.triage(PatientRequest(message="hi"), use_llm=True, emit=lambda k, **d: events.append(k))
    assert calls == [tr.MODEL, tr.FALLBACK_MODEL] and t.model == tr.FALLBACK_MODEL
    assert events == ["attempt", "fail", "attempt", "thought", "success"]


def test_groq_after_both_gemini_models_fail(monkeypatch):
    import concierge.triage as tr

    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(tr, "_triage_llm", lambda req, model, emit=None: (_ for _ in ()).throw(RuntimeError("503")))
    monkeypatch.setattr(tr, "_triage_groq",
                        lambda req, emit=None: Triage(request_type=RequestType.CANCEL, reason="x", triaged_by="groq"))
    assert tr.triage(PatientRequest(message="hello"), use_llm=True).triaged_by == "groq"


def test_keywords_when_every_model_fails(monkeypatch):
    import concierge.triage as tr

    monkeypatch.setattr(tr, "_triage_llm", lambda req, model, emit=None: (_ for _ in ()).throw(RuntimeError("503")))
    assert tr.triage(PatientRequest(message="tooth pain"), use_llm=True).triaged_by == "heuristic"


# --- scheduling: columns, fallback, same day, preferences ------------------------------

def _block(column, day, start, end):
    return {"column": column, "start": f"{day}T{start}:00-04:00", "end": f"{day}T{end}:00-04:00"}


def test_new_patient_slot_uses_hygiene_then_doctor(frozen):
    s = schedule.suggest(CFG, RequestType.NEW_PATIENT)["slots"][0]
    assert [seg["column"] for seg in s["segments"]] == ["hyg1", "dr1"]
    start, end = datetime.fromisoformat(s["start"]), datetime.fromisoformat(s["end"])
    assert end - start == timedelta(minutes=90) and start.hour == 8


def test_new_patient_falls_back_to_doctor_column_2_when_hygiene_full(frozen):
    day = MONDAY.date()
    schedule.book(CFG, None, "existing_patient", {
        "start": f"{day}T08:00:00-04:00", "end": f"{day}T17:00:00-04:00",
        "segments": [_block("hyg1", day, "08:00", "12:00"), _block("hyg1", day, "13:00", "17:00")]}, "Busy", None)
    s = schedule.suggest(CFG, RequestType.NEW_PATIENT)["slots"][0]
    assert datetime.fromisoformat(s["start"]).date() == day
    assert [seg["column"] for seg in s["segments"]] == ["dr2"] and "dr2" in s["note"]


def test_emergency_same_day_in_doctor_column(frozen):
    found = schedule.suggest(CFG, RequestType.EMERGENCY)
    assert found["slots"] and all(s["same_day"] for s in found["slots"])
    assert found["slots"][0]["segments"][0]["column"].startswith("dr")


def test_emergency_rolls_to_next_day_when_doctors_full(frozen):
    day = MONDAY.date()
    for col in ("dr1", "dr2"):
        schedule.book(CFG, None, "emergency", {
            "start": f"{day}T08:00:00-04:00", "end": f"{day}T17:00:00-04:00",
            "segments": [_block(col, day, "08:00", "12:00"), _block(col, day, "13:00", "17:00")]}, "Busy", None)
    found = schedule.suggest(CFG, RequestType.EMERGENCY)
    assert not found["slots"][0]["same_day"] and "No same-day room" in found["note"]


def test_lunch_is_never_offered(frozen):
    for s in schedule.suggest(CFG, RequestType.EXISTING_PATIENT, limit=40)["slots"]:
        start, end = datetime.fromisoformat(s["start"]), datetime.fromisoformat(s["end"])
        assert end.hour <= 12 or start.hour >= 13


def test_preference_filter_afternoons(frozen):
    found = schedule.suggest(CFG, RequestType.EXISTING_PATIENT, "Tuesday afternoons")
    assert found["slots"]
    for s in found["slots"]:
        start = datetime.fromisoformat(s["start"])
        assert start.weekday() == 1 and start.hour >= 12


def test_double_booking_is_refused(frozen):
    slot = schedule.suggest(CFG, RequestType.EMERGENCY)["slots"][0]
    schedule.book(CFG, None, "emergency", slot, "A", "a@x.com")
    with pytest.raises(ValueError):
        schedule.book(CFG, None, "emergency", slot, "B", "b@x.com")


def test_confirmations_due_within_48h(frozen):
    soon = schedule.suggest(CFG, RequestType.EMERGENCY)["slots"][0]
    schedule.book(CFG, None, "emergency", soon, "Soon", "soon@x.com")
    late = MONDAY + timedelta(days=5, hours=2)
    seg = {"column": "dr1", "start": late.isoformat(), "end": (late + timedelta(hours=1)).isoformat()}
    schedule.book(CFG, None, "emergency", {"start": seg["start"], "end": seg["end"], "segments": [seg]}, "Later", "l@x.com")
    due = schedule.confirmations_due(CFG)
    assert [a["patient_name"] for a in due] == ["Soon"]
    subject, body = schedule.confirmation_email(CFG, due[0])
    assert "Confirming" in subject and "$65" in body


# --- pipeline records the AI trace ----------------------------------------------------

def test_process_stores_draft_and_trace(frozen):
    rid = receive(PatientRequest(message="new patient, Tue mornings please", email="pat@example.com"))
    process(rid, CFG, use_llm=False)
    with store.connect() as c:
        row = store.rows(c, "SELECT * FROM requests WHERE id = ?", rid)[0]
        kinds = [r["kind"] for r in store.rows(c, "SELECT kind FROM events WHERE request_id = ?", rid)]
    assert row["status"] == "new" and row["request_type"] == "new_patient" and has_slot(row["body"])
    assert {"attempt", "success", "classified", "slots", "done"} <= set(kinds)


# --- mailer ---------------------------------------------------------------------------

def test_mailer_dry_run_saves_file(isolated):
    res = mailer.send("pat@example.com", "Hi", "Body")
    assert res.ok and res.mode == "dry-run" and list((isolated / "outbox" / "sent").glob("*.eml"))


def test_mailer_live_failure_is_reported(monkeypatch):
    monkeypatch.setenv("CONCIERGE_SMTP_DRYRUN", "0")
    monkeypatch.setenv("SMTP_USER", "desk@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "x")

    def boom(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", boom)
    res = mailer.send("pat@example.com", "Hi", "Body")
    assert not res.ok and "network down" in res.error


# --- web: intake, desk flow, ops ------------------------------------------------------------

@pytest.fixture
def client(frozen):
    api._hits.clear()
    return TestClient(api.app)


def _new_request(client, msg="new patient, Tuesday mornings", email="pat@example.com"):
    rid = client.post("/api/simulate", json={"message": msg, "name": "Pat Lee", "email": email}).json()["id"]
    return rid, client.get(f"/api/requests/{rid}").json()["request"]


def _send(client, rid, row, slot=None, **extra):
    return client.post(f"/api/requests/{rid}/send", json={"to": row["email"], "subject": row["subject"],
                                                            "body": row["body"], "slot": slot, **extra})


def test_public_intake_is_processed_and_returns_nothing_private(client):
    r = client.post("/public/requests", json={"message": "new patient please", "email": "pat@example.com"})
    assert r.json() == {"status": "received"}
    rows = client.get("/api/requests").json()
    assert rows[0]["request_type"] == "new_patient" and rows[0]["status"] == "new"


def test_public_honeypot_and_rate_limit(client):
    assert client.post("/public/requests", json={"message": "spam", "website": "x"}).status_code == 200
    assert client.get("/api/requests").json() == []
    codes = [client.post("/public/requests", json={"message": "cleaning"}).status_code for _ in range(api.RATE_LIMIT + 1)]
    assert codes[-1] == 429


def test_desk_send_with_slot_books_and_emails(client, isolated):
    rid, row = _new_request(client)
    slot = client.get(f"/api/requests/{rid}/slots").json()["slots"][0]
    r = _send(client, rid, row, slot)
    assert r.status_code == 200 and r.json()["mode"] == "dry-run"
    sent = next((isolated / "outbox" / "sent").glob("*.eml")).read_text()
    assert slot["label"] in sent and ">>>" not in sent and "Hyg" not in sent
    assert len(client.get(f"/api/schedule?day={slot['start'][:10]}").json()["appointments"]) == 1
    assert _send(client, rid, row, slot).status_code == 409  # already sent


def test_desk_send_requires_time_and_email(client):
    rid, row = _new_request(client)
    assert _send(client, rid, row).status_code == 400
    no_email = client.post(f"/api/requests/{rid}/send", json={"to": "", "subject": "s", "body": "x", "time_text": "Fri"})
    assert no_email.status_code == 400


def test_typed_time_sends_without_booking(client):
    rid, row = _new_request(client)
    r = _send(client, rid, row, time_text="Friday at 3:30 PM")
    assert r.status_code == 200 and r.json()["appointment_id"] is None


def test_failed_email_releases_the_chair(client, monkeypatch):
    rid, row = _new_request(client)
    slot = client.get(f"/api/requests/{rid}/slots").json()["slots"][0]
    monkeypatch.setattr(mailer, "send", lambda *a, **k: mailer.SendResult(False, "", "live", "SMTPAuthenticationError"))
    assert _send(client, rid, row, slot).status_code == 502
    assert client.get(f"/api/schedule?day={slot['start'][:10]}").json()["appointments"] == []


def test_reschedule_cancels_old_appointment(client):
    rid, row = _new_request(client)
    slot = client.get(f"/api/requests/{rid}/slots").json()["slots"][0]
    _send(client, rid, row, slot)
    rid2, row2 = _new_request(client, "need to move my appointment to next week afternoons")
    upcoming = client.get(f"/api/requests/{rid2}").json()["upcoming"]
    assert row2["request_type"] == "reschedule" and len(upcoming) == 1
    new_slot = client.get(f"/api/requests/{rid2}/slots").json()["slots"][0]
    _send(client, rid2, row2, new_slot, cancel_appointment_ids=[upcoming[0]["id"]])
    assert [a["start"] for a in schedule.upcoming_for(CFG, "pat@example.com")] == [new_slot["start"]]


def test_confirmation_send_marks_confirmed(client):
    rid, row = _new_request(client, "tooth pain")
    _send(client, rid, row, client.get(f"/api/requests/{rid}/slots").json()["slots"][0])
    assert len(client.get("/api/confirmations").json()) == 1
    res = client.post("/api/confirmations/send", json={}).json()["results"]
    assert res[0]["ok"] and client.get("/api/confirmations").json() == []


def test_pages_stats_and_status(client):
    for path, text in (("/", "Concierge"), ("/desk", "Front Desk"), ("/ops", "Operations"), ("/widget.js", "/public/requests")):
        assert text in client.get(path).text
    _new_request(client)
    stats = client.get("/api/stats").json()
    assert stats["totals"]["requests"] == 1 and stats["by_handler"][0][0] == "Keyword rules"
    status = client.get("/api/status").json()
    assert status["smtp"]["mode"] == "dry-run" and len(status["providers"]) == 4


def test_dashboards_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("CONCIERGE_DEMO", "0")
    assert client.get("/desk").status_code == 404


def test_webhook_requires_token(client, monkeypatch):
    monkeypatch.setenv("CONCIERGE_TOKEN", "s3cret")
    assert client.post("/requests", json={"message": "hi"}).status_code == 401
    assert client.post("/requests", json={"message": "hi"}, headers={"X-Concierge-Token": "s3cret"}).status_code == 200


def test_streamed_thought_tokens_are_stored_as_readable_chunks():
    from concierge.pipeline import Recorder

    rid = receive(PatientRequest(message="x"))
    rec = Recorder(rid)
    for token in "We need to parse the message. It is an emergency, so book today.".split(" "):
        rec("thought", text=token + " ")
    rec("answer", text='{"request_type"')  # raw JSON tokens are not stored
    rec("success", provider="groq", model="m", ms=5)
    with store.connect() as c:
        evs = store.rows(c, "SELECT kind, data FROM events WHERE request_id = ? ORDER BY id", rid)
    thoughts = [e for e in evs if e["kind"] == "thought"]
    assert 1 <= len(thoughts) <= 3 and evs[-1]["kind"] == "success"
    assert "".join(__import__("json").loads(t["data"])["text"] for t in thoughts).startswith("We need to parse")


# --- patients & contact -------------------------------------------------------------------

def test_greeting_uses_form_name_in_proper_case():
    d = draft_for("new patient please", name="KASHISH SHRIVASTAV")
    assert d.body.startswith("Hi Kashish,")
    from concierge.compose import first_name
    assert first_name("maria lopez") == "Maria" and first_name("DeShawn Ray") == "DeShawn" and first_name("") == "there"


def test_form_name_beats_name_in_message():
    d = draft_for("Hey it's Tom, need a cleaning", name="Kashish Shrivastav")
    assert d.body.startswith("Hi Kashish,")


def test_patient_upsert_matches_email_then_phone():
    with store.connect() as c:
        a = store.upsert_patient(c, "Kashish S", "K@Example.com", "079902 10320")
        b = store.upsert_patient(c, "Kashish Shrivastav", "k@example.com", None)      # same email
        d = store.upsert_patient(c, None, None, "+44 7990 210320")                       # same last 10 digits
        e = store.upsert_patient(c, "AI guess", "k@example.com", None, overwrite=False)  # fills blanks only
        row = store.rows(c, "SELECT * FROM patients WHERE id = ?", a)[0]
        assert store.upsert_patient(c, "Nobody", None, None) is None
    assert a == b == d == e
    # Latest form wins for name and phone; the AI guess ("overwrite=False") changed nothing.
    assert row["name"] == "Kashish Shrivastav" and row["phone"] == "+44 7990 210320"


def test_requests_link_to_patient_and_profile_shows_history(client):
    rid, row = _new_request(client)
    detail = client.get(f"/api/requests/{rid}").json()
    pid = detail["patient"]["id"]
    assert detail["patient"]["email"] == "pat@example.com"
    _send(client, rid, row, time_text="Friday at 3:30 PM")
    patients = client.get("/api/patients?q=pat").json()
    assert [p["id"] for p in patients] == [pid] and patients[0]["requests"] == 1
    prof = client.get(f"/api/patients/{pid}").json()
    assert prof["greeting"] == "Hi Pat," and len(prof["requests"]) == 1
    assert prof["contacts"][0]["channel"] == "email" and prof["contacts"][0]["ok"] == 1


def test_patient_email_call_log_and_edit(client, isolated):
    rid, _ = _new_request(client)
    pid = client.get(f"/api/requests/{rid}").json()["patient"]["id"]
    r = client.post(f"/api/patients/{pid}/email", json={"subject": "Hello", "body": "Hi Pat,\n\nSee you soon."})
    assert r.status_code == 200 and r.json()["mode"] == "dry-run"
    assert client.post(f"/api/patients/{pid}/log", json={"channel": "call", "note": "Left voicemail"}).json()["ok"]
    assert client.post(f"/api/patients/{pid}/log", json={"channel": "fax"}).status_code == 400
    edited = client.post(f"/api/patients/{pid}", json={"phone": "(919) 555-0100"}).json()
    assert edited["phone"] == "(919) 555-0100" and edited["phone_digits"] == "9195550100"
    channels = [c["channel"] for c in client.get(f"/api/patients/{pid}").json()["contacts"]]
    assert channels == ["call", "email"]
    assert client.get("/api/patients?q=555-0100").json()[0]["id"] == pid


def test_patient_without_email_cannot_be_emailed(client):
    rid = client.post("/api/simulate", json={"message": "cleaning", "phone": "919 555 0177"}).json()["id"]
    pid = client.get(f"/api/requests/{rid}").json()["patient"]["id"]
    assert client.post(f"/api/patients/{pid}/email", json={"subject": "s", "body": "b"}).status_code == 400


def test_old_database_gets_patients_backfilled(isolated, monkeypatch):
    import sqlite3
    path = isolated / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""CREATE TABLE requests (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
        source TEXT, message TEXT, name TEXT, email TEXT, phone TEXT, request_type TEXT, triaged_by TEXT, model TEXT,
        preferred_times TEXT, minutes INTEGER, desk_hint TEXT, subject TEXT, body TEXT, status TEXT NOT NULL DEFAULT 'new',
        delivered_ref TEXT, delivery_ok INTEGER, elapsed_ms INTEGER);
        INSERT INTO requests (created_at, message, name, email, phone) VALUES ('2026-10-01T10:00:00', 'hi', 'Old Pt', 'old@x.com', '9195550111');""")
    old.commit(); old.close()
    monkeypatch.setenv("CONCIERGE_DB", str(path))
    with store.connect() as c:
        r = store.rows(c, "SELECT patient_id FROM requests")[0]
        p = store.rows(c, "SELECT * FROM patients")[0]
    assert r["patient_id"] == p["id"] and p["email"] == "old@x.com"
