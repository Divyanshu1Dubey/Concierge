"""Sync SQLite database tables and columns with current Django models."""
import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'heyjarvis.sqlite3'))
conn = sqlite3.connect(db_path)
cur = conn.cursor()

def add_col_if_missing(table, col, col_def):
    cur.execute(f"PRAGMA table_info({table})")
    existing = [c[1] for c in cur.fetchall()]
    if col not in existing:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
            print(f"Added {col} to {table}")
        except Exception as e:
            print(f"Could not add {col} to {table}: {e}")

try:
    # 1. practices_domain
    cur.execute("""
    CREATE TABLE IF NOT EXISTS "practices_domain" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "hostname" varchar(255) NOT NULL,
        "status" varchar(20) NOT NULL DEFAULT 'CONNECTED',
        "created_at" datetime NOT NULL,
        "updated_at" datetime NOT NULL,
        "practice_id" bigint NOT NULL REFERENCES "practices_practice" ("id")
    );
    """)

    # 2. practices_auditlog
    cur.execute("""
    CREATE TABLE IF NOT EXISTS "practices_auditlog" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "action" varchar(100) NOT NULL,
        "details" text NOT NULL DEFAULT '{}',
        "ip_address" varchar(39) NULL,
        "created_at" datetime NOT NULL,
        "actor_id" char(32) NULL REFERENCES "users_user" ("id"),
        "practice_id" bigint NOT NULL REFERENCES "practices_practice" ("id")
    );
    """)

    # 3. practices_emailtemplate
    cur.execute("""
    CREATE TABLE IF NOT EXISTS "practices_emailtemplate" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "template_type" varchar(50) NOT NULL,
        "subject" varchar(255) NOT NULL,
        "body" text NOT NULL,
        "is_active" bool NOT NULL DEFAULT 1,
        "created_at" datetime NOT NULL,
        "updated_at" datetime NOT NULL,
        "practice_id" bigint NOT NULL REFERENCES "practices_practice" ("id")
    );
    """)

    # 4. conversations_conversation
    add_col_if_missing('conversations_conversation', 'practice_id', 'bigint NULL REFERENCES practices_practice(id)')
    add_col_if_missing('conversations_conversation', 'state', "varchar(35) DEFAULT 'STARTED'")
    add_col_if_missing('conversations_conversation', 'session_id', "varchar(100) DEFAULT ''")
    add_col_if_missing('conversations_conversation', 'service_requested', "varchar(100) DEFAULT ''")
    add_col_if_missing('conversations_conversation', 'preferred_date', "varchar(100) DEFAULT ''")
    add_col_if_missing('conversations_conversation', 'preferred_time', "varchar(100) DEFAULT ''")
    add_col_if_missing('conversations_conversation', 'urgency', "varchar(20) DEFAULT 'NORMAL'")
    add_col_if_missing('conversations_conversation', 'lead_status', "varchar(20) DEFAULT 'NEW'")
    add_col_if_missing('conversations_conversation', 'source_url', "varchar(200) DEFAULT ''")
    add_col_if_missing('conversations_conversation', 'internal_notes', "text DEFAULT '[]'")
    add_col_if_missing('conversations_conversation', 'response_draft', "text DEFAULT ''")
    add_col_if_missing('conversations_conversation', 'response_sent_at', "datetime NULL")

    # 5. appointments_appointment
    add_col_if_missing('appointments_appointment', 'practice_id', 'bigint NULL REFERENCES practices_practice(id)')
    add_col_if_missing('appointments_appointment', 'service_name', "varchar(200) DEFAULT ''")
    add_col_if_missing('appointments_appointment', 'intent', "varchar(50) DEFAULT 'appointment'")
    add_col_if_missing('appointments_appointment', 'preferred_date', "varchar(100) DEFAULT ''")
    add_col_if_missing('appointments_appointment', 'preferred_time', "varchar(100) DEFAULT ''")
    add_col_if_missing('appointments_appointment', 'urgency', "varchar(20) DEFAULT 'NORMAL'")
    add_col_if_missing('appointments_appointment', 'priority', "varchar(20) DEFAULT 'NORMAL'")
    add_col_if_missing('appointments_appointment', 'message', "text DEFAULT ''")
    add_col_if_missing('appointments_appointment', 'ai_summary', "text DEFAULT ''")
    add_col_if_missing('appointments_appointment', 'source_website', "varchar(255) DEFAULT ''")
    add_col_if_missing('appointments_appointment', 'internal_notes', "text DEFAULT '[]'")
    add_col_if_missing('appointments_appointment', 'response_draft', "text DEFAULT ''")
    add_col_if_missing('appointments_appointment', 'response_sent_at', "datetime NULL")

    # 6. practices_practicesettings
    add_col_if_missing('practices_practicesettings', 'notification_mode', "varchar(20) DEFAULT 'MANAGED_EMAIL'")
    add_col_if_missing('practices_practicesettings', 'widget_title', "varchar(100) DEFAULT 'HeyJarvis Concierge'")
    add_col_if_missing('practices_practicesettings', 'widget_subtitle', "varchar(150) DEFAULT 'How can we help you today?'")
    add_col_if_missing('practices_practicesettings', 'widget_primary_color', "varchar(10) DEFAULT '#0d9488'")
    add_col_if_missing('practices_practicesettings', 'widget_position', "varchar(10) DEFAULT 'right'")
    add_col_if_missing('practices_practicesettings', 'widget_auto_open', "bool DEFAULT 0")
    add_col_if_missing('practices_practicesettings', 'widget_auto_open_delay_sec', "integer DEFAULT 5")
    add_col_if_missing('practices_practicesettings', 'notify_on_emergency', "bool DEFAULT 1")
    add_col_if_missing('practices_practicesettings', 'notify_on_appointment', "bool DEFAULT 1")
    add_col_if_missing('practices_practicesettings', 'notify_on_question', "bool DEFAULT 1")
    add_col_if_missing('practices_practicesettings', 'notify_on_reschedule', "bool DEFAULT 1")
    add_col_if_missing('practices_practicesettings', 'notify_on_cancel', "bool DEFAULT 1")
    add_col_if_missing('practices_practicesettings', 'notify_on_handoff', "bool DEFAULT 1")

    # 7. practices_bookingrules
    add_col_if_missing('practices_bookingrules', 'emergency_message', "text DEFAULT 'If you are experiencing severe pain, uncontrolled bleeding, or trauma, please call our emergency line immediately.'")
    add_col_if_missing('practices_bookingrules', 'after_hours_message', "text DEFAULT 'Our office is currently closed. Please leave your details and preferred time, and our front desk will coordinate your appointment first thing next business morning.'")

    # 8. practices_emailprovider
    add_col_if_missing('practices_emailprovider', 'reply_to', "varchar(254) DEFAULT ''")
    add_col_if_missing('practices_emailprovider', 'last_tested_at', "datetime NULL")
    add_col_if_missing('practices_emailprovider', 'last_test_status', "varchar(20) DEFAULT ''")
    add_col_if_missing('practices_emailprovider', 'last_test_error', "text DEFAULT ''")

    # 9. practices_practice
    add_col_if_missing('practices_practice', 'subscription_status', "varchar(20) DEFAULT 'active'")

    conn.commit()
    print("Schema sync completed successfully!")
except Exception as e:
    conn.rollback()
    print(f"Error during schema sync: {e}")
finally:
    conn.close()
