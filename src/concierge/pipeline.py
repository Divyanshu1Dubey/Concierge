"""request -> stored -> AI triage (streamed) -> booking rules -> slots -> reply draft.

Every step is recorded as an event, so the desk dashboard can replay the AI's
reasoning live and the ops dashboard can measure the fallback chain.
"""

from __future__ import annotations

import logging
import time

from . import schedule, store
from .compose import compose
from .config import Config
from .models import Draft, PatientRequest, RequestType
from .rules import plan_booking
from .triage import triage

log = logging.getLogger(__name__)

THOUGHT_FLUSH_CHARS = 60


class Recorder:
    """Writes events for one request. Streamed thought tokens are buffered
    into readable chunks so the dashboard shows phrases, not single tokens."""

    def __init__(self, request_id: int):
        self.request_id = request_id
        self.started = time.perf_counter()
        self.buf = ""

    def ms(self) -> int:
        return round((time.perf_counter() - self.started) * 1000)

    def _write(self, kind: str, data: dict) -> None:
        store.add_event(self.request_id, self.ms(), kind, data)

    def flush(self) -> None:
        if self.buf:
            self._write("thought", {"text": self.buf})
            self.buf = ""

    def __call__(self, kind: str, **data) -> None:
        if kind == "answer":
            return  # raw JSON tokens: not useful to show
        if kind == "thought":
            self.buf += data.get("text", "")
            ends_phrase = self.buf.rstrip()[-1:] in ".,;:!?)\n"
            if (len(self.buf) >= THOUGHT_FLUSH_CHARS and ends_phrase) or len(self.buf) > 240:
                self.flush()
            return
        self.flush()
        self._write(kind, data)


def receive(req: PatientRequest) -> int:
    """Stores the raw request and returns its id. Fast: safe inside the web request."""
    with store.connect() as c:
        patient_id = store.upsert_patient(c, req.name, req.email, req.phone)  # the form's details win
        return store.insert(c, "requests", created_at=store.now_iso(), source=req.source, message=req.message,
                            name=req.name, email=req.email, phone=req.phone, status="processing",
                            patient_id=patient_id)


def process(request_id: int, cfg: Config, *, use_llm: bool | None = None) -> Draft:
    with store.connect() as c:
        row = store.rows(c, "SELECT * FROM requests WHERE id = ?", request_id)[0]
    req = PatientRequest(message=row["message"], name=row["name"], email=row["email"], phone=row["phone"],
                         source=row["source"] or "web_form")
    rec = Recorder(request_id)
    rec("step", text="Request received. Reading what the patient needs…")

    t = triage(req, use_llm=use_llm, emit=rec)
    kind = RequestType(t.request_type)
    rec("classified", request_type=kind.value, reason=t.reason, preferred_times=t.preferred_times,
        patient_name=t.patient_name, cost_question=t.asked_about_cost_or_financing)

    plan = plan_booking(t, cfg)
    rec("step", text=f"Applying the clinic's booking rules → {plan.desk_hint}")

    if kind in (RequestType.RESCHEDULE, RequestType.CANCEL):
        existing = schedule.upcoming_for(cfg, t.patient_email)
        rec("step", text=f"Found {len(existing)} upcoming appointment(s) for this patient."
            if t.patient_email else "No email given, so existing appointments can't be matched.")

    if kind not in (RequestType.CANCEL, RequestType.QUESTION):
        rec("step", text="Checking open chairs: " + ", ".join(sum(schedule.columns(cfg).values(), [])) + "…")
        found = schedule.suggest(cfg, kind, t.preferred_times)
        rec("slots", count=len(found["slots"]), first=found["slots"][0]["label"] if found["slots"] else None,
            note=found["note"])

    draft = compose(t, plan, cfg)
    rec("step", text="Reply drafted. Waiting for the front desk to pick a time and send.")
    rec("done", ms=rec.ms())

    with store.connect() as c:
        # Details the AI read from the message only fill blanks on the patient record.
        patient_id = (store.upsert_patient(c, t.patient_name, t.patient_email, t.patient_phone, overwrite=False)
                      or row["patient_id"])
        store.update(c, "requests", request_id, patient_id=patient_id, request_type=kind.value, triaged_by=t.triaged_by, model=t.model,
                     preferred_times=t.preferred_times, minutes=plan.minutes, desk_hint=draft.plan.desk_hint,
                     subject=draft.subject, body=draft.body, status="new", elapsed_ms=rec.ms(),
                     name=t.patient_name, email=t.patient_email, phone=t.patient_phone)
    # Type and source only: no names or message text in logs (PHI).
    log.info("request %s triaged type=%s via=%s in %sms", request_id, kind.value, t.triaged_by, rec.ms())
    return draft.model_copy(update={"original_message": req.message})


def safe_process(request_id: int, cfg: Config) -> None:
    """Background entry point: a crash leaves a visible error, never a lost request."""
    try:
        process(request_id, cfg)
    except Exception as e:
        log.exception("processing request %s failed", request_id)
        store.add_event(request_id, 0, "error", {"text": f"{type(e).__name__}: {e}"})
        with store.connect() as c:
            store.update(c, "requests", request_id, status="error")


def build_draft(req: PatientRequest, cfg: Config, *, use_llm: bool | None = None) -> Draft:
    """Stateless preview used by the CLI and tests."""
    t = triage(req, use_llm=use_llm)
    draft = compose(t, plan_booking(t, cfg), cfg)
    return draft.model_copy(update={"original_message": req.message})
