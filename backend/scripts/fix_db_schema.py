"""Fix database schema for practices and users in heyjarvis.sqlite3."""
import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'heyjarvis.sqlite3'))
print(f"Connecting to database: {db_path}")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    # 1. Create practices tables if not exist
    cur.execute("""
    CREATE TABLE IF NOT EXISTS "practices_practice" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "name" varchar(255) NOT NULL,
        "slug" varchar(255) NOT NULL UNIQUE,
        "email" varchar(254) NOT NULL,
        "phone" varchar(20) NOT NULL,
        "address" text NOT NULL,
        "city" varchar(100) NOT NULL,
        "state" varchar(2) NOT NULL,
        "zip_code" varchar(10) NOT NULL,
        "timezone" varchar(50) NOT NULL,
        "website" varchar(200) NOT NULL,
        "logo_url" varchar(200) NOT NULL,
        "active" bool NOT NULL,
        "api_key" varchar(64) NOT NULL UNIQUE,
        "created_at" datetime NOT NULL,
        "updated_at" datetime NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS "practices_emailprovider" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "provider_type" varchar(20) NOT NULL,
        "is_active" bool NOT NULL,
        "is_default" bool NOT NULL,
        "from_name" varchar(255) NOT NULL,
        "from_email" varchar(254) NOT NULL,
        "gmail_token" text NOT NULL,
        "gmail_refresh_token" text NOT NULL,
        "gmail_token_expiry" datetime NULL,
        "smtp_host" varchar(255) NOT NULL,
        "smtp_port" integer unsigned NULL,
        "smtp_username" varchar(255) NOT NULL,
        "smtp_password" text NOT NULL,
        "smtp_use_tls" bool NOT NULL,
        "smtp_use_ssl" bool NOT NULL,
        "created_at" datetime NOT NULL,
        "updated_at" datetime NOT NULL,
        "practice_id" bigint NOT NULL REFERENCES "practices_practice" ("id")
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS "practices_bookingrules" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "new_patient_duration" integer unsigned NOT NULL,
        "doctor_duration" integer unsigned NOT NULL,
        "hygiene_duration" integer unsigned NOT NULL,
        "emergency_duration" integer unsigned NOT NULL,
        "confirmation_hours" integer unsigned NOT NULL,
        "no_show_fee" decimal NOT NULL,
        "financing_options" text NOT NULL,
        "business_hours" text NOT NULL,
        "created_at" datetime NOT NULL,
        "updated_at" datetime NOT NULL,
        "practice_id" bigint NOT NULL UNIQUE REFERENCES "practices_practice" ("id")
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS "practices_practicesettings" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "ai_enabled" bool NOT NULL,
        "ai_greeting_message" text NOT NULL,
        "ai_collects_phone" bool NOT NULL,
        "default_from_name" varchar(255) NOT NULL,
        "default_from_email" varchar(254) NOT NULL,
        "email_signature" text NOT NULL,
        "notify_on_new_request" bool NOT NULL,
        "notify_on_patient_reply" bool NOT NULL,
        "notification_emails" text NOT NULL,
        "follow_up_enabled" bool NOT NULL,
        "follow_up_intervals" text NOT NULL,
        "created_at" datetime NOT NULL,
        "updated_at" datetime NOT NULL,
        "practice_id" bigint NOT NULL UNIQUE REFERENCES "practices_practice" ("id")
    );
    """)
    print("Practices tables created or verified.")

    # 2. Check and fix users_user columns
    cur.execute("PRAGMA table_info(users_user)")
    cols = [col[1] for col in cur.fetchall()]
    print(f"Current users_user columns: {cols}")

    if 'google_id' not in cols:
        cur.execute("ALTER TABLE users_user ADD COLUMN google_id varchar(255) DEFAULT ''")
        print("Added google_id column.")
    if 'role' not in cols:
        cur.execute("ALTER TABLE users_user ADD COLUMN role varchar(20) DEFAULT 'FRONT_DESK'")
        if 'user_type' in cols:
            cur.execute("UPDATE users_user SET role = UPPER(user_type) WHERE user_type IS NOT NULL")
        print("Added role column and populated from user_type.")
    if 'practice_id' not in cols:
        cur.execute("ALTER TABLE users_user ADD COLUMN practice_id bigint NULL REFERENCES practices_practice(id)")
        print("Added practice_id column.")

    conn.commit()
    print("Database schema successfully updated!")
except Exception as e:
    conn.rollback()
    print(f"Error updating schema: {e}")
finally:
    conn.close()
