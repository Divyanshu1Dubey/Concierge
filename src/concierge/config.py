"""Loads config/concierge.toml into typed settings."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "config" / "concierge.toml"

# Real environment variables win over .env.
load_dotenv(ROOT / ".env", override=False)


class Clinic(BaseModel):
    name: str
    doctor: str
    phone: str
    front_desk_email: str
    signature: str


class Schedule(BaseModel):
    doctor_columns: int
    hygiene_columns: int
    confirm_hours_before: int
    broken_appointment_fee: int
    financing: list[str]


class NewPatient(BaseModel):
    minutes: int
    doctor_minutes: int
    hygiene_minutes: int
    fallback_doctor_column: int


class Emergency(BaseModel):
    minutes: int
    same_day_when_room: bool


class ExistingPatient(BaseModel):
    minutes: int
    column: str = "hygiene"


class Hours(BaseModel):
    timezone: str
    days: list[str]
    open: str
    close: str
    lunch: list[str] = []
    slot_step_minutes: int = 30
    search_days: int = 14


class Appointments(BaseModel):
    new_patient: NewPatient
    emergency: Emergency
    existing_patient: ExistingPatient


class Safety(BaseModel):
    emergency_warning: str


class Config(BaseModel):
    clinic: Clinic
    schedule: Schedule
    appointments: Appointments
    hours: Hours
    safety: Safety


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path or os.environ.get("CONCIERGE_CONFIG") or DEFAULT_PATH)
    with path.open("rb") as f:
        return Config.model_validate(tomllib.load(f))
