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
    name: str = "My Clinic"
    doctor: str = "Dr. Name"
    phone: str = ""
    front_desk_email: str = ""
    signature: str = ""


class Schedule(BaseModel):
    doctor_columns: int = 2
    hygiene_columns: int = 1
    confirm_hours_before: int = 48
    broken_appointment_fee: int = 0
    financing: list[str] = []


class NewPatient(BaseModel):
    minutes: int = 90
    doctor_minutes: int = 30
    hygiene_minutes: int = 60
    fallback_doctor_column: int = 2


class Emergency(BaseModel):
    minutes: int = 60
    same_day_when_room: bool = True


class ExistingPatient(BaseModel):
    minutes: int = 60
    column: str = "hygiene"


class Hours(BaseModel):
    timezone: str = "America/New_York"
    days: list[str] = ["mon", "tue", "wed", "thu", "fri"]
    open: str = "08:00"
    close: str = "17:00"
    lunch: list[str] = []
    slot_step_minutes: int = 30
    search_days: int = 14


class Appointments(BaseModel):
    new_patient: NewPatient = NewPatient()
    emergency: Emergency = Emergency()
    existing_patient: ExistingPatient = ExistingPatient()


class Safety(BaseModel):
    emergency_warning: str = ""


class Config(BaseModel):
    clinic: Clinic = Clinic()
    schedule: Schedule = Schedule()
    appointments: Appointments = Appointments()
    hours: Hours = Hours()
    safety: Safety = Safety()


def _load_from_toml(path: Path) -> dict:
    """Load raw dict from TOML file."""
    with path.open("rb") as f:
        return tomllib.load(f)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> Config:
    resolved = Path(path or os.environ.get("CONCIERGE_CONFIG") or DEFAULT_PATH)

    # Start with empty defaults
    raw: dict = {}

    # Load from TOML file if it exists
    if resolved.exists():
        try:
            raw = _load_from_toml(resolved)
        except Exception:
            raw = {}
    else:
        # Config file missing — check for example/template
        example = resolved.parent / (resolved.stem + ".toml.example")
        if example.exists():
            try:
                raw = _load_from_toml(example)
            except Exception:
                raw = {}

    # Environment variable overrides (CONCIERGE_CLINIC__NAME, etc.)
    env_overrides: dict = {}
    prefix = "CONCIERGE_"
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        # Strip prefix and split by double-underscore for nesting
        keys = env_key[len(prefix):].lower().split("__")
        current = env_overrides
        for k in keys[:-1]:
            current = current.setdefault(k, {})
        current[keys[-1]] = env_val

    if env_overrides:
        raw = _deep_merge(raw, env_overrides)

    return Config.model_validate(raw)
