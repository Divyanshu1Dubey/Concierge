import sqlite3
import datetime

conn = sqlite3.connect('../heyjarvis.sqlite3')
try:
    for app in ['practices', 'users']:
        conn.execute("INSERT OR IGNORE INTO django_migrations (app, name, applied) VALUES (?, '0001_initial', ?);", (app, datetime.datetime.now()))
    conn.commit()
    print("Fixed migration history.")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()

