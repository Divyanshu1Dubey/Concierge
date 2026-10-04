"""HTTP app: patient intake + the two dashboards.

Intake
  POST /requests          server-to-server webhook (X-Concierge-Token)
  POST /public/requests   clinic website form (CORS allowlist, honeypot, rate limit)
  GET  /widget.js         drop-in form for any website builder
Dashboards (localhost only until real auth is added: they show patient data)
  GET  /                  demo landing: patient form + links
  GET  /desk              Front Desk: queue, live AI reasoning, slots, send via SMTP
  GET  /ops               Operations: volume, AI fallback chain, speed, delivery

Run:  uvicorn concierge.api:app --port 8000
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import statistics
import time
from collections import Counter, defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import mailer, schedule, store
from . import triage as tr
from .compose import fill_slot, has_slot
from .config import load_config
from .models import PatientRequest, RequestType
from .pipeline import receive, safe_process

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
cfg = load_config()


# --- 48h confirmations ------------------------------------------------------------------

def send_confirmations(ids: list[int] | None = None) -> list[dict]:
    results = []
    for appt in schedule.confirmations_due(cfg):
        if ids is not None and appt["id"] not in ids:
            continue
        if not appt["patient_email"]:
            results.append({"id": appt["id"], "ok": False, "error": "no patient email"})
            continue
        subject, body = schedule.confirmation_email(cfg, appt)
        res = mailer.send(appt["patient_email"], subject, body)
        if appt.get("patient_id"):
            log_contact(appt["patient_id"], "email", subject, body, res, request_id=appt["request_id"])
        if res.ok:
            with store.connect() as c:
                store.update(c, "appointments", appt["id"], confirmed_at=store.now_iso(), confirmation_ref=res.ref)
        if appt["request_id"]:
            store.add_event(appt["request_id"], 0, "confirmation", {"ok": res.ok, "mode": res.mode, "error": res.error})
        results.append({"id": appt["id"], "ok": res.ok, "mode": res.mode, "error": res.error})
    return results


async def _auto_confirm_loop():
    while True:
        try:
            sent = await asyncio.to_thread(send_confirmations)
            if sent:
                log.info("auto-confirm: %d processed", len(sent))
        except Exception:
            log.exception("auto-confirm failed")
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(_auto_confirm_loop()) if os.environ.get("CONCIERGE_AUTO_CONFIRM") == "1" else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="HeyJarvis Concierge", version="0.3.0", lifespan=lifespan)
_origins = [o.strip() for o in os.environ.get("CONCIERGE_ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not _origins:
    _origins = [
        "http://localhost:8000",
        "http://localhost:8002",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8002",
        "null",
        "*",
    ]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["POST"], allow_headers=["Content-Type"])


# --- intake ------------------------------------------------------------------------------

def check_token(x_concierge_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("CONCIERGE_TOKEN")
    if not expected:
        raise HTTPException(503, "CONCIERGE_TOKEN not configured")
    if not x_concierge_token or not hmac.compare_digest(x_concierge_token, expected):
        raise HTTPException(401, "bad token")


def _intake(req: PatientRequest, background: BackgroundTasks) -> int:
    request_id = receive(req)
    background.add_task(safe_process, request_id, cfg)
    return request_id


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/requests", dependencies=[Depends(check_token)])
def create_request(req: PatientRequest, background: BackgroundTasks) -> dict:
    return {"status": "received", "id": _intake(req, background)}


class PublicRequest(PatientRequest):
    website: str | None = None  # honeypot: humans never see this field


_hits: dict[str, deque] = defaultdict(deque)
RATE_LIMIT = int(os.environ.get("CONCIERGE_RATE_LIMIT", "5"))  # per IP per minute


def _rate_limited(ip: str) -> bool:
    t, q = time.monotonic(), _hits[ip]
    while q and t - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(t)
    return False


@app.post("/public/requests")
def public_request(body: PublicRequest, request: Request, background: BackgroundTasks) -> dict:
    if body.website:  # bot filled the honeypot: pretend success, store nothing
        return {"status": "received"}
    if _rate_limited(request.client.host if request.client else "?"):
        raise HTTPException(429, "Too many requests, please call the office.")
    _intake(PatientRequest(**body.model_dump(exclude={"website"})), background)
    return {"status": "received"}  # no id: patients can't look anything up


@app.get("/widget.js")
def widget() -> FileResponse:
    return FileResponse(STATIC / "widget.js", media_type="application/javascript")


# --- dashboards (local only) -----------------------------------------------------------------

def local_only(request: Request) -> None:
    if os.environ.get("CONCIERGE_DEMO", "1") == "0":
        raise HTTPException(404)
    if os.environ.get("CONCIERGE_ALLOW_REMOTE_DASHBOARD") == "1" or os.environ.get("CONCIERGE_ALLOW_REMOTE") == "1":
        return
    if (request.client.host if request.client else "") not in LOCAL_HOSTS:
        raise HTTPException(403, "dashboards are localhost-only until auth is added")


@app.get("/", dependencies=[Depends(local_only)])
def page_index() -> FileResponse:
    return FileResponse(STATIC / "index.html", media_type="text/html")


@app.get("/desk", dependencies=[Depends(local_only)])
def page_desk() -> FileResponse:
    return FileResponse(STATIC / "desk.html", media_type="text/html")


@app.get("/ops", dependencies=[Depends(local_only)])
def page_ops() -> FileResponse:
    return FileResponse(STATIC / "ops.html", media_type="text/html")


@app.get("/dashboard.css", dependencies=[Depends(local_only)])
def dashboard_css() -> FileResponse:
    return FileResponse(STATIC / "dashboard.css", media_type="text/css")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


_smtp_check: dict = {"at": 0.0, "result": None}


@app.get("/api/status", dependencies=[Depends(local_only)])
def api_status() -> dict:
    if _smtp_check["result"] is None or time.monotonic() - _smtp_check["at"] > 300:
        _smtp_check.update(at=time.monotonic(), result=mailer.check_login())
    ok, detail = _smtp_check["result"]
    env = os.environ
    return {
        "clinic": cfg.clinic.name,
        "timezone": cfg.hours.timezone,
        "providers": [
            {"provider": "gemini", "model": tr.MODEL, "ready": bool(env.get("GEMINI_API_KEY"))},
            {"provider": "gemini", "model": tr.FALLBACK_MODEL, "ready": bool(env.get("GEMINI_API_KEY"))},
            {"provider": "groq", "model": tr.GROQ_MODEL, "ready": bool(env.get("GROQ_API_KEY"))},
            {"provider": "keywords", "model": "keyword rules", "ready": True},
        ],
        "smtp": {"mode": mailer.mode(), "ok": ok, "detail": detail, "from": mailer.sender()},
        "auto_confirm": env.get("CONCIERGE_AUTO_CONFIRM") == "1",
        "confirm_hours": cfg.schedule.confirm_hours_before,
    }


@app.post("/api/simulate", dependencies=[Depends(local_only)])
def api_simulate(req: PatientRequest, background: BackgroundTasks) -> dict:
    return {"id": _intake(req.model_copy(update={"source": "simulated"}), background)}


@app.get("/api/requests", dependencies=[Depends(local_only)])
def api_requests(view: str = "open") -> list[dict]:
    where = "status IN ('processing','new','error')" if view == "open" else "1=1"
    with store.connect() as c:
        return store.rows(c, "SELECT id, created_at, name, email, request_type, status, triaged_by, model, "
                             "preferred_times, substr(message, 1, 140) AS snippet FROM requests "
                             f"WHERE {where} ORDER BY id DESC LIMIT 100")


def _events(request_id: int, after: int = 0) -> list[dict]:
    with store.connect() as c:
        evs = store.rows(c, "SELECT id, t_ms, kind, data FROM events WHERE request_id = ? AND id > ? ORDER BY id",
                         request_id, after)
    for e in evs:
        e["data"] = json.loads(e["data"])
    return evs


def _request_row(request_id: int) -> dict:
    with store.connect() as c:
        found = store.rows(c, "SELECT * FROM requests WHERE id = ?", request_id)
    if not found:
        raise HTTPException(404, "no such request")
    return found[0]


@app.get("/api/requests/{request_id}", dependencies=[Depends(local_only)])
def api_request(request_id: int) -> dict:
    row = _request_row(request_id)
    return {"request": row, "events": _events(request_id),
            "patient": _patient(row["patient_id"]) if row["patient_id"] else None,
            "upcoming": schedule.upcoming_for(cfg, row["email"]) if row["email"] else []}


@app.get("/api/requests/{request_id}/events", dependencies=[Depends(local_only)])
def api_request_events(request_id: int, after: int = 0) -> dict:
    row = _request_row(request_id)
    return {"status": row["status"], "events": _events(request_id, after)}


@app.get("/api/requests/{request_id}/slots", dependencies=[Depends(local_only)])
def api_slots(request_id: int, minutes: int | None = None, any_time: bool = False) -> dict:
    row = _request_row(request_id)
    if not row["request_type"]:
        return {"slots": [], "note": "Still reading the request…"}
    return schedule.suggest(cfg, RequestType(row["request_type"]),
                            None if any_time else row["preferred_times"], minutes=minutes)


class SendBody(BaseModel):
    to: str
    subject: str
    body: str
    slot: dict | None = None
    time_text: str | None = None
    cancel_appointment_ids: list[int] = []


@app.post("/api/requests/{request_id}/send", dependencies=[Depends(local_only)])
def api_send(request_id: int, payload: SendBody) -> dict:
    row = _request_row(request_id)
    if row["status"] == "sent":
        raise HTTPException(409, "already sent")
    if "@" not in payload.to:
        raise HTTPException(400, "Add the patient's email address first.")
    when = schedule.fmt_when(datetime.fromisoformat(payload.slot["start"])) if payload.slot else payload.time_text
    body = fill_slot(payload.body, when) if when else payload.body
    if has_slot(body):
        raise HTTPException(400, "Pick a time (or type one) before sending.")

    appt_id = None
    if payload.slot:
        try:
            appt_id = schedule.book(cfg, request_id, row["request_type"], payload.slot, row["name"], payload.to,
                                    patient_id=row["patient_id"])
        except ValueError as e:
            raise HTTPException(409, f"{e}. Pick another time.")

    res = mailer.send(payload.to, payload.subject, body)
    if row["patient_id"]:
        log_contact(row["patient_id"], "email", payload.subject, body, res, request_id=request_id)
    if not res.ok:
        if appt_id:
            schedule.cancel(appt_id)  # don't hold a chair for an email that never went out
        store.add_event(request_id, 0, "sent", {"ok": False, "mode": res.mode, "error": res.error})
        raise HTTPException(502, f"Email not sent: {res.error}")

    for old in payload.cancel_appointment_ids:
        schedule.cancel(old)
    with store.connect() as c:
        store.update(c, "requests", request_id, status="sent", delivered_ref=res.ref, delivery_ok=1,
                     email=payload.to, subject=payload.subject, body=body)
        if row["patient_id"]:  # the desk may have added or fixed the address
            p = store.rows(c, "SELECT email FROM patients WHERE id = ?", row["patient_id"])
            if p and not p[0]["email"]:
                store.update(c, "patients", row["patient_id"], email=payload.to, updated_at=store.now_iso())
    store.add_event(request_id, 0, "sent", {"ok": True, "mode": res.mode, "when": when, "appointment_id": appt_id,
                                            "cancelled": payload.cancel_appointment_ids})
    return {"ok": True, "mode": res.mode, "ref": res.ref, "appointment_id": appt_id, "when": when}


@app.post("/api/requests/{request_id}/dismiss", dependencies=[Depends(local_only)])
def api_dismiss(request_id: int) -> dict:
    _request_row(request_id)
    with store.connect() as c:
        store.update(c, "requests", request_id, status="done")
    return {"ok": True}


@app.get("/api/schedule", dependencies=[Depends(local_only)])
def api_schedule(day: str | None = None) -> dict:
    d = date.fromisoformat(day) if day else schedule.now(cfg).date()
    return schedule.day_view(cfg, d)


@app.get("/api/confirmations", dependencies=[Depends(local_only)])
def api_confirmations() -> list[dict]:
    out = []
    for a in schedule.confirmations_due(cfg):
        subject, body = schedule.confirmation_email(cfg, a)
        out.append({**a, "when": schedule.fmt_when(datetime.fromisoformat(a["start"])),
                    "subject": subject, "body": body})
    return out


class ConfirmBody(BaseModel):
    ids: list[int] | None = None


@app.post("/api/confirmations/send", dependencies=[Depends(local_only)])
def api_confirmations_send(payload: ConfirmBody) -> dict:
    return {"results": send_confirmations(payload.ids)}


# --- patients ----------------------------------------------------------------------------

def log_contact(patient_id: int, channel: str, subject: str | None, body: str | None,
                res: mailer.SendResult | None = None, request_id: int | None = None) -> None:
    with store.connect() as c:
        store.insert(c, "contacts", patient_id=patient_id, request_id=request_id, channel=channel, subject=subject,
                     body=body, ok=None if res is None else int(res.ok), ref=res.ref if res else None,
                     error=res.error if res else None, created_at=store.now_iso())


def _patient(patient_id: int) -> dict:
    with store.connect() as c:
        found = store.rows(c, "SELECT * FROM patients WHERE id = ?", patient_id)
    if not found:
        raise HTTPException(404, "no such patient")
    return found[0]


@app.get("/api/patients", dependencies=[Depends(local_only)])
def api_patients(q: str = "") -> list[dict]:
    like = f"%{q.strip().lower()}%"
    digits = store.phone_digits(q) or "~"
    with store.connect() as c:
        return store.rows(c, """
            SELECT p.*, count(DISTINCT r.id) AS requests,
                   max(r.created_at) AS last_request_at,
                   (SELECT min(a.start) FROM appointments a WHERE a.patient_id = p.id AND a.status = 'booked'
                      AND a.end > ?) AS next_visit
            FROM patients p LEFT JOIN requests r ON r.patient_id = p.id
            WHERE lower(coalesce(p.name,'')) LIKE ? OR lower(coalesce(p.email,'')) LIKE ?
                  OR coalesce(p.phone_digits,'') LIKE ?
            GROUP BY p.id ORDER BY coalesce(max(r.created_at), p.updated_at) DESC LIMIT 200""",
            schedule.now(cfg).isoformat(), like, like, f"%{digits}%")


@app.get("/api/patients/{patient_id}", dependencies=[Depends(local_only)])
def api_patient(patient_id: int) -> dict:
    patient = _patient(patient_id)
    with store.connect() as c:
        requests = store.rows(c, "SELECT id, created_at, request_type, status, substr(message,1,160) AS snippet "
                                 "FROM requests WHERE patient_id = ? ORDER BY id DESC", patient_id)
        appts = store.rows(c, "SELECT id, kind, start, end, status, confirmed_at FROM appointments "
                              "WHERE patient_id = ? ORDER BY start DESC", patient_id)
        contacts = store.rows(c, "SELECT * FROM contacts WHERE patient_id = ? ORDER BY id DESC", patient_id)
    for a in appts:
        a["when"] = schedule.fmt_when(datetime.fromisoformat(a["start"]))
    from .compose import first_name
    return {"patient": patient, "requests": requests, "appointments": appts, "contacts": contacts,
            "greeting": f"Hi {first_name(patient['name'])},", "signature": cfg.clinic.signature,
            "clinic_phone": cfg.clinic.phone}


class PatientEdit(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


@app.post("/api/patients/{patient_id}", dependencies=[Depends(local_only)])
def api_patient_edit(patient_id: int, payload: PatientEdit) -> dict:
    _patient(patient_id)
    changes = {k: (v.strip() or None) for k, v in payload.model_dump().items() if v is not None}
    if "phone" in changes:
        changes["phone_digits"] = store.phone_digits(changes["phone"])
    with store.connect() as c:
        store.update(c, "patients", patient_id, **changes, updated_at=store.now_iso())
    return _patient(patient_id)


class PatientEmail(BaseModel):
    subject: str
    body: str


@app.post("/api/patients/{patient_id}/email", dependencies=[Depends(local_only)])
def api_patient_email(patient_id: int, payload: PatientEmail) -> dict:
    p = _patient(patient_id)
    if not p["email"]:
        raise HTTPException(400, "This patient has no email address. Add one first.")
    if not payload.subject.strip() or not payload.body.strip():
        raise HTTPException(400, "Add a subject and a message.")
    res = mailer.send(p["email"], payload.subject, payload.body)
    log_contact(patient_id, "email", payload.subject, payload.body, res)
    if not res.ok:
        raise HTTPException(502, f"Email not sent: {res.error}")
    return {"ok": True, "mode": res.mode}


class ContactNote(BaseModel):
    channel: str  # call | sms | note
    note: str = ""


@app.post("/api/patients/{patient_id}/log", dependencies=[Depends(local_only)])
def api_patient_log(patient_id: int, payload: ContactNote) -> dict:
    _patient(patient_id)
    if payload.channel not in ("call", "sms", "note"):
        raise HTTPException(400, "channel must be call, sms or note")
    log_contact(patient_id, payload.channel, None, payload.note.strip() or None)
    return {"ok": True}


# --- ops stats ----------------------------------------------------------------------------

def _handler(row: dict) -> str:
    if row["triaged_by"] == "heuristic":
        return "Keyword rules"
    return f"{'Gemini' if row['triaged_by'] == 'gemini' else 'Groq'} · {row['model']}"


def _pct(values: list[int], p: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, round(p * (len(s) - 1)))]


@app.get("/api/stats", dependencies=[Depends(local_only)])
def api_stats(days: int = 14) -> dict:
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with store.connect() as c:
        reqs = store.rows(c, "SELECT id, created_at, request_type, triaged_by, model, status, elapsed_ms "
                             "FROM requests WHERE created_at >= ? ORDER BY id", since)
        evs = store.rows(c, "SELECT e.request_id, e.kind, e.data FROM events e JOIN requests r ON r.id = e.request_id "
                            "WHERE r.created_at >= ? AND e.kind IN ('fail','success','sent','confirmation') "
                            "ORDER BY e.id", since)
        appts = store.rows(c, "SELECT status, confirmed_at FROM appointments")
    for e in evs:
        e["data"] = json.loads(e["data"])

    done = [r for r in reqs if r["triaged_by"]]
    today = date.today()
    per_day = Counter(r["created_at"][:10] for r in reqs)
    lat = [r["elapsed_ms"] for r in done if r["elapsed_ms"] is not None]

    fails: Counter = Counter()
    fail_reasons: dict[str, Counter] = defaultdict(Counter)
    chain: dict[int, list] = defaultdict(list)
    for e in evs:
        d = e["data"]
        if e["kind"] in ("fail", "success"):
            chain[e["request_id"]].append({"kind": e["kind"], "model": d.get("model"), "ms": d.get("ms"),
                                           "reason": d.get("reason")})
        if e["kind"] == "fail":
            fails[d["model"]] += 1
            fail_reasons[d["model"]][(d.get("reason") or "")[:48]] += 1
    first_try = sum(1 for r in done if not any(a["kind"] == "fail" for a in chain[r["id"]]))
    handler_lat: dict[str, list] = defaultdict(list)
    for r in done:
        if r["elapsed_ms"] is not None:
            handler_lat[_handler(r)].append(r["elapsed_ms"])
    sent = [e for e in evs if e["kind"] == "sent"]

    return {
        "days": days,
        "totals": {
            "requests": len(reqs),
            "today": per_day.get(today.isoformat(), 0),
            "ai_handled_pct": round(100 * sum(r["triaged_by"] != "heuristic" for r in done) / len(done)) if done else None,
            "first_try_pct": round(100 * first_try / len(done)) if done else None,
            "p50_ms": _pct(lat, 0.5), "p95_ms": _pct(lat, 0.95),
            "mean_ms": round(statistics.mean(lat)) if lat else None,
            "replies_sent": sum(bool(e["data"].get("ok")) for e in sent),
            "send_failures": sum(not e["data"].get("ok") for e in sent),
            "booked": sum(a["status"] == "booked" for a in appts),
            "confirmations_sent": sum(1 for a in appts if a["confirmed_at"]),
            "awaiting_desk": sum(r["status"] == "new" for r in reqs),
            "errors": sum(r["status"] == "error" for r in reqs),
        },
        "per_day": [{"date": (today - timedelta(days=i)).isoformat(),
                     "count": per_day.get((today - timedelta(days=i)).isoformat(), 0)}
                    for i in range(days - 1, -1, -1)],
        "by_type": Counter(r["request_type"] for r in done).most_common(),
        "by_handler": Counter(_handler(r) for r in done).most_common(),
        "handler_latency": {k: {"p50": _pct(v, .5), "n": len(v)} for k, v in handler_lat.items()},
        "failures": [{"model": m, "count": n, "top_reason": fail_reasons[m].most_common(1)[0][0]}
                     for m, n in fails.most_common()],
        "funnel": [
            {"stage": "Received", "count": len(reqs)},
            {"stage": "Read by AI or rules", "count": len(done)},
            {"stage": "Reply sent", "count": sum(r["status"] == "sent" for r in reqs)},
        ],
        "recent": [{"id": r["id"], "created_at": r["created_at"], "type": r["request_type"],
                    "handler": _handler(r), "ms": r["elapsed_ms"], "status": r["status"], "chain": chain[r["id"]]}
                   for r in reversed(done[-12:])],
    }
