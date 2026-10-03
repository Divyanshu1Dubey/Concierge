"""Concierge's own appointment book: column-aware slot suggestions,
bookings, and the 48h confirmation queue.

Columns come from config: `doctor_columns` doctor chairs (dr1, dr2, ...) and
`hygiene_columns` hygiene chairs (hyg1, ...). Rules from the one-pager:
  new patient  = 60 hygiene + 30 doctor (90 total); no hygiene slot ->
                 full 90 with the doctor on column `fallback_doctor_column`
  emergency    = 60 in any doctor column, same day when there is room
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import store
from .config import Config
from .models import RequestType

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass
class Segment:
    column: str
    start: datetime
    end: datetime

    def as_dict(self) -> dict:
        return {"column": self.column, "start": self.start.isoformat(), "end": self.end.isoformat()}


@dataclass
class Slot:
    start: datetime
    end: datetime
    segments: list[Segment]
    note: str

    def as_dict(self, today: date) -> dict:
        return {
            "start": self.start.isoformat(), "end": self.end.isoformat(),
            "label": fmt_when(self.start), "note": self.note,
            "same_day": self.start.date() == today,
            "segments": [s.as_dict() for s in self.segments],
        }


def tz(cfg: Config) -> ZoneInfo:
    return ZoneInfo(cfg.hours.timezone)


def now(cfg: Config) -> datetime:
    return datetime.now(tz(cfg))


def fmt_when(dt: datetime) -> str:
    return dt.strftime("%A, %b ") + str(dt.day) + dt.strftime(" at ") + dt.strftime("%I:%M %p").lstrip("0")


def columns(cfg: Config) -> dict[str, list[str]]:
    s = cfg.schedule
    return {
        "doctor": [f"dr{i + 1}" for i in range(s.doctor_columns)],
        "hygiene": [f"hyg{i + 1}" for i in range(s.hygiene_columns)],
    }


def _hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


# --- occupancy ----------------------------------------------------------------

def busy(cfg: Config, day: date) -> dict[str, list[tuple[datetime, datetime]]]:
    z = tz(cfg)
    start = datetime.combine(day, time(0), z)
    end = start + timedelta(days=1)
    out: dict[str, list] = {}
    with store.connect() as c:
        appts = store.rows(c, "SELECT segments FROM appointments WHERE status = 'booked' AND start < ? AND end > ?",
                           end.isoformat(), start.isoformat())
    for a in appts:
        for seg in json.loads(a["segments"]):
            out.setdefault(seg["column"], []).append(
                (datetime.fromisoformat(seg["start"]), datetime.fromisoformat(seg["end"])))
    lunch = cfg.hours.lunch
    if len(lunch) == 2:
        block = (datetime.combine(day, _hm(lunch[0]), z), datetime.combine(day, _hm(lunch[1]), z))
        for col in sum(columns(cfg).values(), []):
            out.setdefault(col, []).append(block)
    return out


def _free(occ: dict, column: str, start: datetime, end: datetime) -> bool:
    return all(end <= s or start >= e for s, e in occ.get(column, []))


def _first_free(occ: dict, cols: list[str], start: datetime, end: datetime) -> str | None:
    return next((c for c in cols if _free(occ, c, start, end)), None)


# --- suggestions ----------------------------------------------------------------

def _fit(kind: RequestType, start: datetime, occ: dict, cfg: Config, minutes: int | None) -> Slot | None:
    cols = columns(cfg)
    a = cfg.appointments
    if kind is RequestType.NEW_PATIENT:
        np = a.new_patient
        hyg_end = start + timedelta(minutes=np.hygiene_minutes)
        end = hyg_end + timedelta(minutes=np.doctor_minutes)
        hyg = _first_free(occ, cols["hygiene"], start, hyg_end)
        dr = _first_free(occ, cols["doctor"], hyg_end, end)
        if hyg and dr:
            return Slot(start, end, [Segment(hyg, start, hyg_end), Segment(dr, hyg_end, end)],
                        f"{np.hygiene_minutes} hygiene ({hyg}) + {np.doctor_minutes} doctor ({dr})")
        fb = f"dr{np.fallback_doctor_column}"
        end = start + timedelta(minutes=np.minutes)
        if fb in cols["doctor"] and _free(occ, fb, start, end):
            return Slot(start, end, [Segment(fb, start, end)], f"hygiene full: {np.minutes} with doctor on {fb}")
        return None
    if kind is RequestType.EMERGENCY:
        end = start + timedelta(minutes=a.emergency.minutes)
        dr = _first_free(occ, cols["doctor"], start, end)
        return Slot(start, end, [Segment(dr, start, end)], f"{a.emergency.minutes} min emergency ({dr})") if dr else None
    # existing patient / reschedule
    length = minutes or a.existing_patient.minutes or 60
    end = start + timedelta(minutes=length)
    preferred = cols.get(a.existing_patient.column, []) + [c for k, v in cols.items()
                                                         if k != a.existing_patient.column for c in v]
    col = _first_free(occ, preferred, start, end)
    return Slot(start, end, [Segment(col, start, end)], f"{length} min ({col})") if col else None


_DAY_WORDS = {d: i for i, d in enumerate(DAYS)}


def _preference_filter(pref: str | None, cfg: Config):
    """Turns 'Tue mornings', 'weekday afternoons', 'today', 'next week' into a predicate."""
    if not pref:
        return None
    p = pref.lower()
    days = {i for name, i in _DAY_WORDS.items() if re.search(rf"\b{name}", p)}
    if "weekend" in p:
        days |= {5, 6}
    part = "am" if "morning" in p else "pm" if ("afternoon" in p or "evening" in p) else None
    today = now(cfg).date()
    on = today if "today" in p else today + timedelta(days=1) if "tomorrow" in p else None
    next_week = "next week" in p
    if not (days or part or on or next_week):
        return None

    def ok(dt: datetime) -> bool:
        if days and dt.weekday() not in days:
            return False
        if part == "am" and dt.hour >= 12 or part == "pm" and dt.hour < 12:
            return False
        if on and dt.date() != on:
            return False
        if next_week:
            monday = today + timedelta(days=7 - today.weekday())
            if not monday <= dt.date() < monday + timedelta(days=7):
                return False
        return True
    return ok


def suggest(cfg: Config, kind: RequestType, preferred: str | None = None,
            minutes: int | None = None, limit: int = 6) -> dict:
    if kind in (RequestType.CANCEL, RequestType.QUESTION):
        return {"slots": [], "note": None}
    h = cfg.hours
    z = tz(cfg)
    step = timedelta(minutes=h.slot_step_minutes)
    t_now = now(cfg)
    open_days = {_DAY_WORDS[d] for d in h.days}
    pref_ok = _preference_filter(preferred, cfg)

    def scan(match) -> list[Slot]:
        found: list[Slot] = []
        for offset in range(h.search_days):
            day = t_now.date() + timedelta(days=offset)
            if day.weekday() not in open_days:
                continue
            occ = busy(cfg, day)
            t = datetime.combine(day, _hm(h.open), z)
            close = datetime.combine(day, _hm(h.close), z)
            per_day = 0
            while t < close:
                if t > t_now + timedelta(minutes=15) and (match is None or match(t)):
                    slot = _fit(kind, t, occ, cfg, minutes)
                    if slot and slot.end <= close:
                        found.append(slot)
                        per_day += 1
                        if len(found) >= limit:
                            return found
                        if per_day >= 3:  # spread suggestions across days
                            break
                t += step
            if kind is RequestType.EMERGENCY and found and offset == 0:
                return found  # same-day room exists: show only today
        return found

    slots = scan(pref_ok)
    note = None
    if pref_ok and not slots:
        slots = scan(None)
        note = f"Nothing open matching “{preferred}”; showing the next openings."
    if kind is RequestType.EMERGENCY and slots and slots[0].start.date() != t_now.date():
        note = "No same-day room left today; earliest openings shown."
    return {"slots": [s.as_dict(t_now.date()) for s in slots], "note": note}


# --- bookings -------------------------------------------------------------------

def book(cfg: Config, request_id: int | None, kind: str, slot: dict, name: str | None, email: str | None,
         patient_id: int | None = None) -> int:
    """Re-checks the slot is still free, then stores it. Raises ValueError if taken."""
    start = datetime.fromisoformat(slot["start"])
    for seg in slot["segments"]:
        s, e = datetime.fromisoformat(seg["start"]), datetime.fromisoformat(seg["end"])
        if not _free(busy(cfg, s.date()), seg["column"], s, e):
            raise ValueError(f"{seg['column']} is no longer free at {fmt_when(s)}")
    with store.connect() as c:
        return store.insert(c, "appointments", request_id=request_id, patient_id=patient_id, kind=kind,
                            patient_name=name,
                            patient_email=email, start=slot["start"], end=slot["end"],
                            segments=json.dumps(slot["segments"]), status="booked")


def upcoming_for(cfg: Config, email: str | None) -> list[dict]:
    if not email:
        return []
    with store.connect() as c:
        return store.rows(c, "SELECT * FROM appointments WHERE status = 'booked' AND lower(patient_email) = lower(?) "
                             "AND end > ? ORDER BY start", email, now(cfg).isoformat())


def cancel(appt_id: int) -> None:
    with store.connect() as c:
        store.update(c, "appointments", appt_id, status="cancelled")


def day_view(cfg: Config, day: date) -> dict:
    z = tz(cfg)
    start = datetime.combine(day, time(0), z)
    with store.connect() as c:
        appts = store.rows(c, "SELECT * FROM appointments WHERE status = 'booked' AND start >= ? AND start < ? "
                              "ORDER BY start", start.isoformat(), (start + timedelta(days=1)).isoformat())
    for a in appts:
        a["segments"] = json.loads(a["segments"])
    cols = columns(cfg)
    return {"date": day.isoformat(), "open": cfg.hours.open, "close": cfg.hours.close,
            "lunch": cfg.hours.lunch, "columns": cols["doctor"] + cols["hygiene"], "appointments": appts}


# --- 48h confirmations ------------------------------------------------------------

def confirmations_due(cfg: Config) -> list[dict]:
    t = now(cfg)
    horizon = t + timedelta(hours=cfg.schedule.confirm_hours_before)
    with store.connect() as c:
        return store.rows(c, "SELECT * FROM appointments WHERE status = 'booked' AND confirmed_at IS NULL "
                             "AND start > ? AND start <= ? ORDER BY start", t.isoformat(), horizon.isoformat())


def confirmation_email(cfg: Config, appt: dict) -> tuple[str, str]:
    c, s = cfg.clinic, cfg.schedule
    from .compose import first_name

    first = first_name(appt.get("patient_name"))
    when = fmt_when(datetime.fromisoformat(appt["start"]))
    subject = f"Confirming your visit on {when}"
    body = "\n".join([
        f"Hi {first},", "",
        f"This is a reminder of your appointment at {c.name} on {when}.", "",
        "Please reply to this email to confirm, or let us know as soon as you can if you need to change it. "
        f"There is a ${s.broken_appointment_fee} fee for missed or broken appointments.", "",
        f"If you have any questions, call us at {c.phone}.", "", c.signature,
    ])
    return subject, body
