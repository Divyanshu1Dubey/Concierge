"""Data shapes that move through the pipeline."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RequestType(StrEnum):
    NEW_PATIENT = "new_patient"
    EMERGENCY = "emergency"
    EXISTING_PATIENT = "existing_patient"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    QUESTION = "question"


class PatientRequest(BaseModel):
    """Raw inbound request (website form, webhook, forwarded email)."""

    message: str = Field(min_length=1, max_length=10_000)
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str = "web_form"


class Triage(BaseModel):
    """What the patient wants, read from their message."""

    request_type: RequestType
    patient_name: str | None = None
    patient_email: str | None = None
    patient_phone: str | None = None
    preferred_times: str | None = Field(None, description="Patient's stated availability, verbatim-ish")
    reason: str = Field(description="One short line: what the visit is for")
    asked_about_cost_or_financing: bool = False
    triaged_by: str = "heuristic"
    model: str | None = None


class BookingPlan(BaseModel):
    """Booking-rule output: what the desk should book. Never shown to the patient."""

    minutes: int | None
    desk_hint: str
    same_day: bool = False


class Draft(BaseModel):
    to: str | None
    original_message: str | None = None
    subject: str
    body: str
    triage: Triage
    plan: BookingPlan
