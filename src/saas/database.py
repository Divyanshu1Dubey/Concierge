"""SaaS database layer with SQLite, migrations, and multi-tenant tables."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from saas.config import get_settings
from saas.result import Result

_lock = threading.RLock()

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
CREATE TABLE IF NOT EXISTS frontdesk_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    lead_id INTEGER,
    conversation_id INTEGER,
    note TEXT NOT NULL,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
CREATE TABLE IF NOT EXISTS frontdesk_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    lead_id INTEGER,
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open',
    due_at TEXT,
    completed_at TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);
CREATE TABLE IF NOT EXISTS ai_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    lead_id INTEGER,
    conversation_id INTEGER,
    subject TEXT,
    body TEXT NOT NULL,
    html_body TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    sent_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
CREATE TABLE IF NOT EXISTS email_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    lead_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    message_id TEXT NOT NULL,
    in_reply_to TEXT,
    references_hdr TEXT,
    from_addr TEXT,
    to_addr TEXT,
    subject TEXT,
    body TEXT,
    draft_id INTEGER,
    cadence_step TEXT,
    source TEXT NOT NULL DEFAULT 'heyjarvis',
    classification TEXT,
    sent_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    UNIQUE(tenant_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_email_messages_lead ON email_messages(tenant_id, lead_id, sent_at);
CREATE TABLE IF NOT EXISTS login_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    used_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS cadences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL UNIQUE,
    config TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS cadence_enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    lead_id INTEGER NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    step_index INTEGER NOT NULL DEFAULT 0,
    skipped TEXT NOT NULL DEFAULT '[]',
    anchor_at TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (lead_id) REFERENCES leads(id)
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
    # The lock only guards one-time schema creation. Holding it for the whole
    # connection serialized every request and deadlocked nested connect() calls.
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        if str(path) not in _ready:
            with _lock:
                if str(path) not in _ready:
                    conn.executescript(SCHEMA)
                    _ensure_columns(conn)
                    _ready.add(str(path))
        yield conn
    finally:
        conn.commit()
        conn.close()


# Columns added after the first release. SQLite has no ADD COLUMN IF NOT EXISTS.
_ADDED_COLUMNS = {
    "email_settings": ["imap_host TEXT", "imap_port INTEGER", "imap_user TEXT", "imap_password_enc TEXT",
                       "imap_state TEXT", "sent_folder TEXT", "last_sync_at TEXT", "last_sync_error TEXT",
                       "auth_type TEXT", "oauth_refresh_enc TEXT", "mail_provider TEXT",
                       "append_sent INTEGER"],  # 1: HeyJarvis files sent mail in Sent, 0: server does, NULL: unknown
    "ai_drafts": ["cadence_step TEXT", "to_email TEXT", "source TEXT"],
    "conversations": ["access_token TEXT", "lead_id INTEGER"],
}


def _ensure_columns(conn) -> None:
    for table, cols in _ADDED_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col in cols:
            if col.split()[0] not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
    # At most one pending draft per cadence step and patient, even if two schedulers race.
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_one_pending_step ON ai_drafts(lead_id, cadence_step) "
                     "WHERE status = 'pending' AND cadence_step IS NOT NULL")
    except sqlite3.IntegrityError:
        pass  # existing duplicates (pre-index data); run_due's lock still prevents new ones


def reset_database() -> None:
    path = db_path()
    _ready.discard(str(path))
    if path.exists():
        path.unlink()
    if path.exists():
        path.unlink()


def migrate() -> None:
    """Additive migration: add new columns and tables to existing database if missing."""
    with connect() as c:
        # email_settings: new columns
        for col in ["smtp_security", "front_desk_email", "backup_email", "delivery_mode"]:
            try:
                c.execute(f"ALTER TABLE email_settings ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
        # leads: columns
        for col in ["source", "page_url", "conversation_summary", "metadata"]:
            try:
                c.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
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
        # frontdesk_notes
        try:
            c.execute("""CREATE TABLE IF NOT EXISTS frontdesk_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                lead_id INTEGER,
                conversation_id INTEGER,
                note TEXT NOT NULL,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (lead_id) REFERENCES leads(id),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )""")
        except sqlite3.OperationalError:
            pass
        # frontdesk_tasks
        try:
            c.execute("""CREATE TABLE IF NOT EXISTS frontdesk_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                lead_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT NOT NULL DEFAULT 'medium',
                status TEXT NOT NULL DEFAULT 'open',
                due_at TEXT,
                completed_at TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            )""")
        except sqlite3.OperationalError:
            pass
        # ai_drafts
        try:
            c.execute("""CREATE TABLE IF NOT EXISTS ai_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                lead_id INTEGER,
                conversation_id INTEGER,
                subject TEXT,
                body TEXT NOT NULL,
                html_body TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                sent_at TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (lead_id) REFERENCES leads(id),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )""")
        except sqlite3.OperationalError:
            pass


def utcnow() -> datetime:
    """Naive UTC 'now'. All stored timestamps are UTC; pages convert to the viewer's local time."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now_iso() -> str:
    return utcnow().isoformat(timespec="seconds")


def insert(conn, table: str, **cols) -> int:
    keys = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    return conn.execute(f"INSERT INTO {table} ({keys}) VALUES ({marks})", list(cols.values())).lastrowid


def update(conn, table: str, row_id: int, **cols) -> None:
    sets = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*cols.values(), row_id])


def _params(args: tuple) -> tuple:
    # Callers use both rows(c, sql, (a, b)) and rows(c, sql, a, b); accept either.
    if len(args) == 1 and isinstance(args[0], (tuple, list)):
        return tuple(args[0])
    return args


def rows(conn, sql: str, *args) -> list[Result]:
    return [Result(r) for r in conn.execute(sql, _params(args))]


def row(conn, sql: str, *args) -> Result | None:
    found = rows(conn, sql, *args)
    return found[0] if found else None
