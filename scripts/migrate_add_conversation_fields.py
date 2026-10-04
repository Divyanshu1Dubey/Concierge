"""Migration: add conversation_fields table for persisting extracted fields."""
import sqlite3
from pathlib import Path

from saas.database import db_path

path = db_path()
conn = sqlite3.connect(path)
try:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            field_key TEXT NOT NULL,
            field_value TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id),
            UNIQUE(conversation_id, field_key)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_fields_conv ON conversation_fields(conversation_id)")
    conn.commit()
    print("Migration applied: conversation_fields table ready")
finally:
    conn.close()
