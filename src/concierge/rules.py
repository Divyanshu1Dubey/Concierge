"""The clinic's booking rules, as plain code. No LLM involved here."""

from __future__ import annotations

from .config import Config
from .models import BookingPlan, RequestType, Triage


def plan_booking(triage: Triage, cfg: Config) -> BookingPlan:
    appts = cfg.appointments
    match triage.request_type:
        case RequestType.NEW_PATIENT:
            np = appts.new_patient
            return BookingPlan(
                minutes=np.minutes,
                desk_hint=(
                    f"NEW PT {np.minutes} min: {np.doctor_minutes} Dr + {np.hygiene_minutes} Hyg. "
                    f"No hygiene slot -> full {np.minutes} with Dr in column {np.fallback_doctor_column}"
                ),
            )
        case RequestType.EMERGENCY:
            em = appts.emergency
            hint = f"EMERGENCY {em.minutes} min"
            if em.same_day_when_room:
                hint += ", TODAY if there is room (same-day treatment OK)"
            return BookingPlan(minutes=em.minutes, desk_hint=hint, same_day=em.same_day_when_room)
        case RequestType.EXISTING_PATIENT:
            minutes = appts.existing_patient.minutes or None
            length = f"{minutes} min" if minutes else "length per desk"
            return BookingPlan(minutes=minutes, desk_hint=f"EXISTING PT, {length}: {triage.reason}")
        case RequestType.RESCHEDULE:
            return BookingPlan(minutes=None, desk_hint="RESCHEDULE: keep original length, new time")
        case RequestType.CANCEL:
            return BookingPlan(minutes=None, desk_hint="CANCEL: offer a new time or delete this line")
        case RequestType.QUESTION:
            return BookingPlan(minutes=None, desk_hint="QUESTION: answer here, offer a visit if relevant")
