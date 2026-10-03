"""Builds the patient-facing reply that lands in the desk's Drafts folder.

The desk's whole job: replace the >>> ... <<< slot with a day and time, then
hit send. The booking hint lives *inside* that slot, so it disappears the
moment they type the time and never reaches the patient.
"""

from __future__ import annotations

from .config import Config
from .models import BookingPlan, Draft, RequestType, Triage

SLOT_OPEN, SLOT_CLOSE = ">>> ", " <<<"


def slot(hint: str) -> str:
    return f"{SLOT_OPEN}TYPE DAY & TIME HERE | {hint}{SLOT_CLOSE}"


def compose(triage: Triage, plan: BookingPlan, cfg: Config) -> Draft:
    c, s = cfg.clinic, cfg.schedule
    if triage.preferred_times:
        plan = plan.model_copy(update={"desk_hint": f"{plan.desk_hint} | pt prefers: {triage.preferred_times}"})
    name = first_name(triage.patient_name)
    t = triage.request_type

    policy = (
        f"We'll send you a confirmation {s.confirm_hours_before} hours before your visit. "
        f"If you need to change it, please let us know as early as you can; "
        f"there is a ${s.broken_appointment_fee} fee for missed or broken appointments."
    )
    financing = f"We offer financing through {_join(s.financing)} if that would help."

    lines: list[str] = [f"Hi {name},", ""]
    match t:
        case RequestType.NEW_PATIENT:
            subject = f"Your new-patient visit at {c.name}"
            lines += [
                f"Thanks for reaching out, and welcome! We'd love to see you for your first visit with {c.doctor}.",
                "",
                f"We have you scheduled for {slot(plan.desk_hint)}.",
                "",
                f"Please plan for about {plan.minutes} minutes. Your first visit includes an exam with "
                f"{c.doctor} and a cleaning.",
                "",
                policy,
            ]
        case RequestType.EMERGENCY:
            subject = f"Getting you seen: {c.name}"
            lines += [
                "We're sorry you're dealing with this. We want to get you in quickly.",
                "",
                f"We can see you {slot(plan.desk_hint)}.",
                "",
                f"Please plan for about {plan.minutes} minutes. If there's time, {c.doctor} may be able "
                "to treat the problem during the same visit.",
                "",
                cfg.safety.emergency_warning,
            ]
        case RequestType.EXISTING_PATIENT:
            subject = f"Your appointment at {c.name}"
            lines += [
                "Thanks for getting in touch. It's good to hear from you.",
                "",
                f"We have you scheduled for {slot(plan.desk_hint)}.",
                "",
                policy,
            ]
        case RequestType.RESCHEDULE:
            subject = f"Your rescheduled appointment at {c.name}"
            lines += [
                "No problem, we've moved your appointment.",
                "",
                f"Your new time is {slot(plan.desk_hint)}.",
                "",
                policy,
            ]
        case RequestType.CANCEL:
            subject = f"Your appointment at {c.name}"
            lines += [
                "We've received your cancellation request.",
                "",
                f"If you'd like to rebook, we have an opening on {slot(plan.desk_hint)}.",
            ]
        case RequestType.QUESTION:
            subject = f"Re: your message to {c.name}"
            lines += [
                "Thanks for your message.",
                "",
                f"{SLOT_OPEN}TYPE ANSWER HERE | {plan.desk_hint}{SLOT_CLOSE}",
            ]

    if triage.asked_about_cost_or_financing and t is not RequestType.EMERGENCY:
        lines += ["", financing]
    lines += ["", f"If you have any questions, call us at {c.phone}.", "", c.signature]

    return Draft(to=triage.patient_email, subject=subject, body="\n".join(lines), triage=triage, plan=plan)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" or {items[-1]}"


def first_name(full: str | None) -> str:
    """'KASHISH SHRIVASTAV' -> 'Kashish', 'maria lopez' -> 'Maria'; keeps mixed case like 'DeShawn'."""
    first = (full or "").strip().split(" ")[0]
    if not first:
        return "there"
    return first.capitalize() if first.isupper() or first.islower() else first


def has_slot(body: str) -> bool:
    return SLOT_OPEN in body and SLOT_CLOSE in body


def fill_slot(body: str, text: str) -> str:
    """Replaces the >>> ... <<< slot (booking hint included) with `text`."""
    start = body.find(SLOT_OPEN)
    end = body.find(SLOT_CLOSE, start)
    if start == -1 or end == -1:
        return body
    return body[:start] + text + body[end + len(SLOT_CLOSE):]
