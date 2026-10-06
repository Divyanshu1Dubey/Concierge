"""One follow-up cadence per clinic, with editable reply rules.

Every new lead with an email is enrolled. When a step is due, the scheduler
creates a DRAFT in the front desk queue; nothing is emailed until a person
approves it. Delays count from the last email the patient received (any email
from the clinic resets the clock, including ones the desk sent from Gmail by hand).

When the patient replies, the reply is classified and the first matching rule
in `on_reply` runs. Actions:
  stop                  end the cadence for this patient
  pause / resume        hold or continue the cadence
  skip:<step_id>        drop one future step (e.g. "skip:follow_up_1")
  set_status:<status>   change the lead status (new, contacted, booked, closed, ...)
  task:<title>          add a front desk task
  draft_reply           queue an AI reply to the patient's message for approval
Pending (unsent) cadence drafts are discarded on stop/pause/skip so stale
follow-ups can't be sent by accident.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from saas.database import connect, insert, now_iso, row, rows

log = logging.getLogger(__name__)

REPLY_INTENTS = ["booked", "wants_appointment", "reschedule", "cancel", "question",
                 "not_interested", "unsubscribe", "other"]
LEAD_STATUSES = {"new", "contacted", "qualified", "booked", "closed", "spam", "scheduled", "completed", "archived"}

DEFAULT_CADENCE: dict[str, Any] = {
    "enabled": True,
    "steps": [
        {"id": "first_reply", "name": "First reply", "delay_hours": 0, "mode": "ai",
         "instruction": "Reply to the patient's appointment request. Thank them, restate what they asked for, and "
                        "ask them to reply with two or three days/times that work, or to call the office. "
                        "Do not promise a specific slot.",
         "template": "Hi {{name}},\n\nThanks for reaching out to {{practice_name}} about {{service}}. "
                     "Could you reply with two or three days and times that work for you? You can also call us "
                     "and we'll get you scheduled.\n\nBest,\n{{practice_name}}"},
        {"id": "follow_up_1", "name": "Follow-up 1", "delay_hours": 24, "mode": "ai",
         "instruction": "Short, friendly nudge: we haven't heard back, we're happy to find a time, reply with "
                        "what works. 2-3 sentences.",
         "template": "Hi {{name}},\n\nJust following up on your request. Reply with a few times that work and "
                     "we'll take care of the rest.\n\nBest,\n{{practice_name}}"},
        {"id": "follow_up_2", "name": "Follow-up 2", "delay_hours": 72, "mode": "ai",
         "instruction": "Second nudge, warm and brief. Mention they can also call the office directly.",
         "template": "Hi {{name}},\n\nWe'd still love to get you in. Reply here or give us a call whenever "
                     "is convenient.\n\nBest,\n{{practice_name}}"},
        {"id": "last_check_in", "name": "Last check-in", "delay_hours": 168, "mode": "ai",
         "instruction": "Final polite check-in. Say we'll close out the request for now and they can reach out "
                        "any time. No pressure.",
         "template": "Hi {{name}},\n\nWe'll close out your request for now. If you'd like to schedule later, "
                     "just reply to this email.\n\nBest,\n{{practice_name}}"},
    ],
    "on_reply": [
        {"when": ["booked"], "do": ["stop", "set_status:booked"]},
        {"when": ["not_interested", "unsubscribe"], "do": ["stop", "set_status:closed"]},
        {"when": ["cancel"], "do": ["stop", "task:Patient wants to cancel - confirm and close"]},
        {"when": ["*"], "do": ["pause", "draft_reply", "task:Patient replied - review the AI draft"]},
    ],
}


EMERGENCY_INSTRUCTION = ("This patient reported a dental emergency. Reply briefly and urgently: ask them to call the "
                         "office right away so we can see them as soon as possible, and say that if they have swelling "
                         "affecting breathing or swallowing, a high fever, or bleeding that won't stop they should call "
                         "911 or go to the ER. Do not ask for preferred times.")
EMERGENCY_TEMPLATE = ("Hi {{name}},\n\nWe're sorry you're in pain. Please call our office right away so we can see you "
                      "as soon as possible.\n\nIf you have swelling that affects your breathing or swallowing, a high "
                      "fever, or bleeding that won't stop, call 911 or go to the nearest emergency room.\n\n"
                      "{{practice_name}}")


# ── Config ───────────────────────────────────────────────────────────────────


def get_cadence(tenant_id: int) -> dict:
    with connect() as c:
        r = row(c, "SELECT config FROM cadences WHERE tenant_id = ?", tenant_id)
    return json.loads(r["config"]) if r else copy.deepcopy(DEFAULT_CADENCE)


def save_cadence(tenant_id: int, cfg: dict) -> dict:
    cfg = validate(cfg)
    with connect() as c:
        if row(c, "SELECT id FROM cadences WHERE tenant_id = ?", tenant_id):
            c.execute("UPDATE cadences SET config = ?, updated_at = ? WHERE tenant_id = ?",
                      (json.dumps(cfg), now_iso(), tenant_id))
        else:
            insert(c, "cadences", tenant_id=tenant_id, config=json.dumps(cfg), updated_at=now_iso())
    return cfg


def validate(cfg: dict) -> dict:
    """Raise ValueError with a readable message for anything the engine can't run."""
    if not isinstance(cfg, dict):
        raise ValueError("cadence must be an object")
    steps = cfg.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    ids = []
    for i, st in enumerate(steps):
        sid = str(st.get("id") or "").strip()
        if not re.fullmatch(r"[a-z0-9_]{1,40}", sid):
            raise ValueError(f"step {i + 1}: id must be lowercase letters, digits or _")
        if sid in ids:
            raise ValueError(f"duplicate step id {sid}")
        ids.append(sid)
        try:
            if float(st.get("delay_hours", 0)) < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(f"step {sid}: delay_hours must be a number >= 0") from None
        if st.get("mode", "ai") not in ("ai", "template"):
            raise ValueError(f"step {sid}: mode must be 'ai' or 'template'")
        if st.get("mode") == "template" and not (st.get("template") or "").strip():
            raise ValueError(f"step {sid}: template mode needs a template")
    for i, rule in enumerate(cfg.get("on_reply") or []):
        when = rule.get("when")
        if not isinstance(when, list) or not when or any(w != "*" and w not in REPLY_INTENTS for w in when):
            raise ValueError(f"rule {i + 1}: 'when' must list reply types from {REPLY_INTENTS} or '*'")
        for act in rule.get("do") or []:
            name, _, arg = str(act).partition(":")
            if name in ("stop", "pause", "resume", "draft_reply") and not arg:
                continue
            if name == "skip" and arg in ids:
                continue
            if name == "set_status" and arg in LEAD_STATUSES:
                continue
            if name == "task" and arg.strip():
                continue
            raise ValueError(f"rule {i + 1}: unknown action '{act}'")
    return {"enabled": bool(cfg.get("enabled", True)), "steps": steps, "on_reply": cfg.get("on_reply") or []}


# ── Enrollment ───────────────────────────────────────────────────────────────


def get_enrollment(tenant_id: int, lead_id: int) -> dict | None:
    with connect() as c:
        r = row(c, "SELECT * FROM cadence_enrollments WHERE tenant_id = ? AND lead_id = ?", tenant_id, lead_id)
    if r:
        r["skipped"] = json.loads(r["skipped"] or "[]")
        step = _next_step(get_cadence(tenant_id), r)
        r["next_step"] = step[1] if step else None
        r["next_due_at"] = _due_at(r, step[1]).isoformat(timespec="seconds") if step else None
    return r


def enroll(tenant_id: int, lead_id: int, *, restart: bool = False) -> dict | None:
    from saas.repositories import get_lead
    lead = get_lead(lead_id)
    if not lead or lead["tenant_id"] != tenant_id or not lead.get("email"):
        return None
    if not get_cadence(tenant_id).get("enabled", True):
        return None
    now = now_iso()
    with connect() as c:
        existing = row(c, "SELECT id FROM cadence_enrollments WHERE lead_id = ?", lead_id)
        if existing and not restart:
            return get_enrollment(tenant_id, lead_id)
        if existing:
            c.execute("UPDATE cadence_enrollments SET status='active', step_index=0, skipped='[]', anchor_at=?, "
                      "reason='restarted', updated_at=? WHERE id = ?", (now, now, existing["id"]))
        else:
            insert(c, "cadence_enrollments", tenant_id=tenant_id, lead_id=lead_id, status="active", step_index=0,
                   skipped="[]", anchor_at=now, created_at=now, updated_at=now)
    return get_enrollment(tenant_id, lead_id)


def set_state(tenant_id: int, lead_id: int, status: str, reason: str = "") -> dict | None:
    if status not in ("active", "paused", "stopped"):
        raise ValueError("status must be active, paused or stopped")
    with connect() as c:
        c.execute("UPDATE cadence_enrollments SET status = ?, reason = ?, updated_at = ? WHERE tenant_id = ? AND lead_id = ?",
                  (status, reason, now_iso(), tenant_id, lead_id))
    if status != "active":
        _discard_pending(tenant_id, lead_id)
    return get_enrollment(tenant_id, lead_id)


def _next_step(cfg: dict, enr: dict) -> tuple[int, dict] | None:
    skipped = enr["skipped"] if isinstance(enr["skipped"], list) else json.loads(enr["skipped"] or "[]")
    for i in range(int(enr["step_index"]), len(cfg["steps"])):
        if cfg["steps"][i]["id"] not in skipped:
            return i, cfg["steps"][i]
    return None


def _due_at(enr: dict, step: dict) -> datetime:
    return datetime.fromisoformat(enr["anchor_at"]) + timedelta(hours=float(step.get("delay_hours", 0)))


def _discard_pending(tenant_id: int, lead_id: int, step_id: str | None = None) -> None:
    sql = ("UPDATE ai_drafts SET status = 'discarded', updated_at = ? WHERE tenant_id = ? AND lead_id = ? "
           "AND status = 'pending' AND cadence_step IS NOT NULL")
    args: list[Any] = [now_iso(), tenant_id, lead_id]
    if step_id:
        sql += " AND cadence_step = ?"
        args.append(step_id)
    with connect() as c:
        c.execute(sql, args)


# ── Scheduler ────────────────────────────────────────────────────────────────


def run_due(tenant_id: int | None = None, now: datetime | None = None) -> list[int]:
    """Create drafts for every step that is due. Returns the new draft ids."""
    now = now or datetime.now()
    sql = "SELECT * FROM cadence_enrollments WHERE status = 'active'"
    args: list[Any] = []
    if tenant_id is not None:
        sql += " AND tenant_id = ?"
        args.append(tenant_id)
    with connect() as c:
        enrollments = rows(c, sql, args)
    created = []
    configs: dict[int, dict] = {}
    for enr in enrollments:
        cfg = configs.setdefault(enr["tenant_id"], get_cadence(enr["tenant_id"]))
        if not cfg.get("enabled", True):
            continue
        nxt = _next_step(cfg, enr)
        if not nxt:
            _finish(enr["id"])
            continue
        _, step = nxt
        with connect() as c:
            waiting = row(c, "SELECT id FROM ai_drafts WHERE tenant_id = ? AND lead_id = ? AND status = 'pending' "
                             "AND cadence_step IS NOT NULL", enr["tenant_id"], enr["lead_id"])
        if waiting or _due_at(enr, step) > now:
            continue
        try:
            created.append(draft_for_step(enr["tenant_id"], enr["lead_id"], step))
        except Exception:
            log.exception("cadence draft failed tenant=%s lead=%s step=%s", enr["tenant_id"], enr["lead_id"], step["id"])
    return created


def fast_forward(tenant_id: int, hours: float) -> list[int]:
    """Demo only: move every active cadence clock back so the next steps come due, then draft them."""
    with connect() as c:
        for e in rows(c, "SELECT id, anchor_at FROM cadence_enrollments WHERE tenant_id = ? AND status = 'active'", tenant_id):
            earlier = (datetime.fromisoformat(e["anchor_at"]) - timedelta(hours=hours)).isoformat(timespec="seconds")
            c.execute("UPDATE cadence_enrollments SET anchor_at = ? WHERE id = ?", (earlier, e["id"]))
    return run_due(tenant_id)


def _finish(enrollment_id: int) -> None:
    with connect() as c:
        c.execute("UPDATE cadence_enrollments SET status = 'completed', updated_at = ? WHERE id = ?",
                  (now_iso(), enrollment_id))


def draft_for_step(tenant_id: int, lead_id: int, step: dict) -> int:
    from saas.repositories import get_lead
    lead = get_lead(lead_id)
    subject = "Your appointment request"
    body = None
    urgent_first = step["id"] == "first_reply" and lead.get("intent") == "emergency"
    if urgent_first:
        subject = "We got your message - please call us"
    if step.get("mode", "ai") == "ai":
        from saas import ai_engine
        instruction = EMERGENCY_INSTRUCTION if urgent_first else step.get("instruction", "")
        result = ai_engine.draft_reply(_history(tenant_id, lead), _patient(lead), _practice(tenant_id),
                                       instruction=instruction)
        if result.get("provider") not in (None, "disabled") and not str(result.get("provider")).startswith("failed"):
            body, subject = result.get("body"), result.get("subject") or subject
    if not body:  # template mode, or AI unavailable
        body = _fill(EMERGENCY_TEMPLATE if urgent_first else (step.get("template") or ""), lead, tenant_id)
    with connect() as c:
        did = insert(c, "ai_drafts", tenant_id=tenant_id, lead_id=lead_id, conversation_id=lead.get("conversation_id"),
                     subject=subject, body=body, status="pending", cadence_step=step["id"], to_email=lead.get("email"),
                     source="cadence", created_at=now_iso(), updated_at=now_iso())
    return did


def on_outbound(tenant_id: int, lead_id: int, cadence_step: str | None) -> None:
    """Any email to the patient resets the clock; a sent cadence draft also moves to the next step."""
    enr = get_enrollment(tenant_id, lead_id)
    if not enr:
        return
    cfg = get_cadence(tenant_id)
    idx = enr["step_index"]
    if cadence_step:
        ids = [s["id"] for s in cfg["steps"]]
        if cadence_step in ids:
            idx = ids.index(cadence_step) + 1
    status = enr["status"]
    if status == "active" and _next_step(cfg, {**enr, "step_index": idx}) is None:
        status = "completed"
    with connect() as c:
        c.execute("UPDATE cadence_enrollments SET step_index = ?, anchor_at = ?, status = ?, updated_at = ? WHERE id = ?",
                  (idx, now_iso(), status, now_iso(), enr["id"]))


def on_discard(tenant_id: int, lead_id: int, cadence_step: str | None) -> None:
    """Desk threw away a cadence draft: treat that step as skipped, keep the clock where it was."""
    enr = get_enrollment(tenant_id, lead_id)
    if not enr or not cadence_step:
        return
    skipped = sorted(set(enr["skipped"]) | {cadence_step})
    with connect() as c:
        c.execute("UPDATE cadence_enrollments SET skipped = ?, updated_at = ? WHERE id = ?",
                  (json.dumps(skipped), now_iso(), enr["id"]))


def on_reply(tenant_id: int, lead_id: int, message: dict) -> dict:
    """Classify a patient reply and run the first matching rule."""
    from saas.repositories import create_frontdesk_task, get_lead, update_lead

    classification = classify_reply(message.get("body") or "")
    with connect() as c:
        c.execute("UPDATE email_messages SET classification = ? WHERE id = ?",
                  (json.dumps(classification), message["id"]))
    intent = classification["intent"]
    cfg = get_cadence(tenant_id)
    rule = next((r for r in cfg.get("on_reply") or [] if "*" in r["when"] or intent in r["when"]), None)
    applied: list[str] = []
    if not rule:
        return {"intent": intent, "applied": applied}
    enr = get_enrollment(tenant_id, lead_id)
    for act in rule.get("do") or []:
        name, _, arg = act.partition(":")
        if name in ("stop", "pause", "resume") and enr:
            set_state(tenant_id, lead_id, {"stop": "stopped", "pause": "paused", "resume": "active"}[name],
                      reason=f"patient replied: {intent}")
        elif name == "skip" and enr:
            skipped = sorted(set(get_enrollment(tenant_id, lead_id)["skipped"]) | {arg})
            with connect() as c:
                c.execute("UPDATE cadence_enrollments SET skipped = ?, updated_at = ? WHERE id = ?",
                          (json.dumps(skipped), now_iso(), enr["id"]))
            _discard_pending(tenant_id, lead_id, arg)
        elif name == "set_status":
            update_lead(lead_id, status=arg)
        elif name == "task":
            create_frontdesk_task(tenant_id, title=arg, priority="high", lead_id=lead_id,
                                  description=classification.get("summary"))
        elif name == "draft_reply":
            _draft_reply_to(tenant_id, get_lead(lead_id), message)
        else:
            continue
        applied.append(act)
    return {"intent": intent, "applied": applied}


def _draft_reply_to(tenant_id: int, lead: dict, message: dict) -> int:
    from saas import ai_engine
    result = ai_engine.draft_reply(_history(tenant_id, lead), _patient(lead), _practice(tenant_id),
                                   instruction="Reply to the patient's most recent email. Answer what they asked; "
                                               "if they proposed times, say the front desk will confirm the exact "
                                               "slot. Never invent availability.")
    body = result.get("body") or ""
    if str(result.get("provider", "")).startswith("failed") or result.get("provider") == "disabled":
        body = f"Hi {lead.get('name') or 'there'},\n\nThanks for your reply. We'll get back to you shortly.\n\n" \
               f"Best,\n{_practice(tenant_id)['practice_name']}"
    with connect() as c:
        return insert(c, "ai_drafts", tenant_id=tenant_id, lead_id=lead["id"], conversation_id=lead.get("conversation_id"),
                      subject=message.get("subject") or "Re: your request", body=body, status="pending",
                      to_email=lead.get("email"), source="reply", created_at=now_iso(), updated_at=now_iso())


# ── Reply classification ─────────────────────────────────────────────────────

_RULES = [
    ("unsubscribe", r"\bunsubscribe\b|stop (emailing|contacting)|remove me|take me off"),
    ("not_interested", r"not interested|no thanks|no thank you|went (somewhere|elsewhere)|found another|don'?t need"),
    ("cancel", r"\bcancel"),
    ("reschedule", r"\breschedul|change (my|the) (appointment|time)|different (day|time)|move (my|the) appointment"),
    ("booked", r"\b(already )?(booked|scheduled)\b|i called|have an appointment|see you (on|then|monday|tuesday|"
               r"wednesday|thursday|friday)"),
    ("wants_appointment", r"\b(available|works for me|i can do|i'?m free|monday|tuesday|wednesday|thursday|friday|"
                          r"saturday|morning|afternoon|evening|\d{1,2}(:\d\d)?\s?(am|pm))\b"),
]


def classify_reply(text: str) -> dict:
    from saas import ai_engine
    result = ai_engine.classify_reply(text)
    if result and result.get("intent") in REPLY_INTENTS:
        return result
    lowered = text.lower()
    for intent, pattern in _RULES:
        if re.search(pattern, lowered):
            return {"intent": intent, "summary": text.strip()[:160], "provider": "rules"}
    return {"intent": "question" if "?" in text else "other", "summary": text.strip()[:160], "provider": "rules"}


# ── Context for drafts ───────────────────────────────────────────────────────


def _patient(lead: dict) -> dict:
    keys = ("name", "email", "phone", "service", "intent", "urgency", "preferred_date", "preferred_time",
            "insurance", "message", "status")
    return {k: lead.get(k) for k in keys}


def _practice(tenant_id: int) -> dict:
    from saas.repositories import get_tenant
    t = get_tenant(tenant_id)
    with connect() as c:
        s = row(c, "SELECT from_name, from_email FROM email_settings WHERE tenant_id = ?", tenant_id) or {}
    return {"practice_name": s.get("from_name") or (t.name if t else ""), "reply_email": s.get("from_email")}


def _history(tenant_id: int, lead: dict) -> str:
    lines = []
    if lead.get("conversation_id"):
        with connect() as c:
            for m in rows(c, "SELECT role, body FROM messages WHERE conversation_id = ? ORDER BY id",
                          lead["conversation_id"]):
                lines.append(f"[website chat] {'Patient' if m['role'] == 'user' else 'Concierge'}: {m['body']}")
    with connect() as c:
        for m in rows(c, "SELECT direction, body, sent_at FROM email_messages WHERE tenant_id = ? AND lead_id = ? "
                         "ORDER BY sent_at, id", tenant_id, lead["id"]):
            who = "Patient" if m["direction"] == "in" else "Clinic"
            lines.append(f"[email {m['sent_at']}] {who}: {m['body']}")
    return "\n".join(lines[-30:]) or (lead.get("message") or "")


def _fill(template: str, lead: dict, tenant_id: int) -> str:
    values = {**{k: v or "" for k, v in _patient(lead).items()}, **_practice(tenant_id)}
    values["name"] = (lead.get("name") or "there").split()[0] if lead.get("name") else "there"
    values["service"] = lead.get("service") or "your visit"
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(values.get(m.group(1), "")), template)
