"""SaaS database layer with SQLite, migrations, and multi-tenant tables."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from saas.config import get_settings

_lock = threading.Lock()

def _get_settings():
    return get_settings()

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    plan TEXT NOT NULL DEFAULT 'trial',
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT,
    hashed_password TEXT,
    role TEXT NOT NULL DEFAULT 'owner',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    UNIQUE(tenant_id, email),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(tenant_id, user_id)
);
CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    domain TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    UNIQUE(tenant_id, domain)
);
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    public_key TEXT NOT NULL UNIQUE,
    secret_key_hash TEXT NOT NULL,
    last_used_at TEXT,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS widget_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL UNIQUE,
    config TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS email_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'default',
    smtp_host TEXT,
    smtp_port INTEGER,
    smtp_user TEXT,
    smtp_password_enc TEXT,
    smtp_security TEXT DEFAULT 'tls',
    from_name TEXT,
    from_email TEXT,
    reply_to TEXT,
    front_desk_email TEXT,
    backup_email TEXT,
    delivery_mode TEXT NOT NULL DEFAULT 'email_draft',
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS business_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL UNIQUE,
    rules TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    visitor_id TEXT,
    page_url TEXT,
    referrer TEXT,
    user_agent TEXT,
    status TEXT NOT NULL DEFAULT 'started',
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
CREATE TABLE IF NOT EXISTS conversation_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    field_key TEXT NOT NULL,
    field_value TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    UNIQUE(conversation_id, field_key)
);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    conversation_id INTEGER,
    name TEXT,
    email TEXT,
    phone TEXT,
    intent TEXT,
    service TEXT,
    urgency TEXT,
    preferred_date TEXT,
    preferred_time TEXT,
    insurance TEXT,
    financing TEXT,
    message TEXT,
    conversation_summary TEXT,
    source TEXT,
    page_url TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    lead_id INTEGER,
    conversation_id INTEGER,
    channel TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    payload TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    event TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    actor_user_id INTEGER,
    action TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tenant_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL UNIQUE,
    flags TEXT NOT NULL DEFAULT '{}',
    ai_instructions TEXT,
    hours TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS email_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    intent TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS integration_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL UNIQUE,
    webhook_url TEXT,
    webhook_secret_enc TEXT,
    crm_provider TEXT,
    crm_config_enc TEXT,
    sms_provider TEXT,
    sms_config_enc TEXT,
    calendar_provider TEXT,
    calendar_config_enc TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS rate_limit_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    window_start TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    UNIQUE(key, window_start)
);
CREATE INDEX IF NOT EXISTS idx_leads_tenant ON leads(tenant_id);
CREATE INDEX IF NOT EXISTS idx_conversations_tenant ON conversations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_analytics_tenant ON analytics_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_public ON api_keys(public_key);
CREATE INDEX IF NOT EXISTS idx_domains_domain ON domains(domain);
CREATE INDEX IF NOT EXISTS idx_notifications_tenant ON notifications(tenant_id);
"""


def db_path() -> Path:
    return Path(_get_settings().database_url)


_ready: set[str] = set()


def reset_schema_cache() -> None:
    _ready.clear()


@contextmanager
def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if str(path) not in _ready:
                conn.executescript(SCHEMA)
                _ready.add(str(path))
            yield conn
        finally:
            conn.commit()
            conn.close()


def reset_database() -> None:
    path = db_path()
    _ready.discard(str(path))
    if path.exists():
        path.unlink()
    if path.exists():
        path.unlink()


def migrate() -> None:
    """Additive migration: add new columns to existing tables if missing."""
    with connect() as c:
        # email_settings: new columns
        for col in ["smtp_security", "front_desk_email", "backup_email", "delivery_mode"]:
            try:
                c.execute(f"ALTER TABLE email_settings ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
        # integration_settings table
        try:
            c.execute("""CREATE TABLE IF NOT EXISTS integration_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL UNIQUE,
                webhook_url TEXT,
                webhook_secret_enc TEXT,
                crm_provider TEXT,
                crm_config_enc TEXT,
                sms_provider TEXT,
                sms_config_enc TEXT,
                calendar_provider TEXT,
                calendar_config_enc TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )""")
        except sqlite3.OperationalError:
            pass
        # rate_limit_entries table
        try:
            c.execute("""CREATE TABLE IF NOT EXISTS rate_limit_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                window_start TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                UNIQUE(key, window_start)
            )""")
        except sqlite3.OperationalError:
            pass


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


def row(conn, sql: str, *args) -> dict | None:
    found = rows(conn, sql, *args)
    return found[0] if found else None
