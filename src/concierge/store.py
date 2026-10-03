"""SQLite store for requests, AI trace events, and appointments.

Holds patient details (PHI): keep data/ off git, on an encrypted disk, and
behind auth before any non-local deployment.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    source TEXT, message TEXT, name TEXT, email TEXT, phone TEXT,
    request_type TEXT, triaged_by TEXT, model TEXT, preferred_times TEXT,
    minutes INTEGER, desk_hint TEXT, subject TEXT, body TEXT,
    status TEXT NOT NULL DEFAULT 'new',          -- new | booked | done
    delivered_ref TEXT, delivery_ok INTEGER,
    elapsed_ms INTEGER
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL, t_ms INTEGER NOT NULL,
    kind TEXT NOT NULL, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_req ON events(request_id);
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER, kind TEXT NOT NULL,
    patient_name TEXT, patient_email TEXT,
    start TEXT NOT NULL, end TEXT NOT NULL,
    segments TEXT NOT NULL,                      -- JSON [{column,start,end}]
    status TEXT NOT NULL DEFAULT 'booked',       -- booked | cancelled
    confirmation_ref TEXT, confirmed_at TEXT
);
CREATE INDEX IF NOT EXISTS appt_start ON appointments(start);
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, email TEXT, phone TEXT, phone_digits TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS patients_email ON patients(lower(email));
CREATE INDEX IF NOT EXISTS patients_phone ON patients(phone_digits);
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL, request_id INTEGER,
    channel TEXT NOT NULL,                       -- email | call | sms | note
    subject TEXT, body TEXT, ok INTEGER, ref TEXT, error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS contacts_patient ON contacts(patient_id);
"""

# Columns added after the first release, applied to existing databases.
MIGRATIONS = {
    "requests": {"patient_id": "INTEGER"},
    "appointments": {"patient_id": "INTEGER"},
}


def db_path() -> Path:
    return Path(os.environ.get("CONCIERGE_DB") or ROOT / "data" / "concierge.db")


_ready: set[str] = set()


def _migrate(conn) -> None:
    conn.executescript(SCHEMA)
    for table, cols in MIGRATIONS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, kind in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
    # Older requests had no patient record: create one for each.
    for r in conn.execute("SELECT id, name, email, phone FROM requests WHERE patient_id IS NULL").fetchall():
        pid = upsert_patient(conn, r["name"], r["email"], r["phone"])
        if pid:
            conn.execute("UPDATE requests SET patient_id = ? WHERE id = ?", (pid, r["id"]))
    conn.execute("UPDATE appointments SET patient_id = (SELECT patient_id FROM requests r "
                 "WHERE r.id = appointments.request_id) WHERE patient_id IS NULL AND request_id IS NOT NULL")


@contextmanager
def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            if str(path) not in _ready:
                _migrate(conn)
                _ready.add(str(path))
            yield conn
            conn.commit()
        finally:
            conn.close()


# --- patients -------------------------------------------------------------------

def phone_digits(phone: str | None) -> str | None:
    digits = "".join(ch for ch in phone or "" if ch.isdigit())
    return digits[-10:] if len(digits) >= 7 else None  # last 10: ignore +1 / leading 0


def upsert_patient(conn, name: str | None, email: str | None, phone: str | None, *,
                   overwrite: bool = True) -> int | None:
    """Finds the patient by email, else by phone; creates one if neither matches.
    overwrite=True: the latest form's name/phone win. False: only fill blanks
    (used for details the AI read out of the message text)."""
    email = (email or "").strip() or None
    phone = (phone or "").strip() or None
    name = (name or "").strip() or None
    digits = phone_digits(phone)
    if not (email or digits):
        return None
    row = None
    if email:
        row = conn.execute("SELECT * FROM patients WHERE lower(email) = lower(?)", (email,)).fetchone()
    if row is None and digits:
        row = conn.execute("SELECT * FROM patients WHERE phone_digits = ?", (digits,)).fetchone()
    now = now_iso()
    if row is None:
        return insert(conn, "patients", name=name, email=email, phone=phone, phone_digits=digits,
                      created_at=now, updated_at=now)
    changes = {}
    for col, val in (("name", name), ("email", email), ("phone", phone)):
        if val and (overwrite or not row[col]) and val != row[col]:
            changes[col] = val
    if "phone" in changes:
        changes["phone_digits"] = digits
    if changes:
        update(conn, "patients", row["id"], **changes, updated_at=now)
    return row["id"]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def insert(conn, table: str, **cols) -> int:
    keys = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    return conn.execute(f"INSERT INTO {table} ({keys}) VALUES ({marks})", list(cols.values())).lastrowid


def update(conn, table: str, row_id: int, **cols) -> None:
    sets = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*cols.values(), row_id])


def rows(conn, sql: str, *args) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args)]


def add_event(request_id: int, t_ms: int, kind: str, data: dict) -> None:
    with connect() as c:
        insert(c, "events", request_id=request_id, t_ms=t_ms, kind=kind, data=json.dumps(data))
