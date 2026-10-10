"""
Repair schema drift: some older SQLite databases (e.g. ones built with
scripts/fix_db_schema.py) still have legacy practices_emailprovider columns
gmail_token / gmail_refresh_token declared NOT NULL without a default. The model
no longer has them, so every new EmailProvider insert fails (email settings and
"Send test email" return 500). On SQLite, when such columns exist, rebuild the
table from the model (model fields' rows are copied, the unused legacy columns
are dropped); everywhere else this is a no-op.
"""
from django.db import migrations

LEGACY_COLUMNS = ('gmail_token', 'gmail_refresh_token', 'gmail_token_expiry')


def repair_emailprovider_table(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'sqlite':
        return
    EmailProvider = apps.get_model('practices', 'EmailProvider')
    table = EmailProvider._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f'PRAGMA table_info("{table}")')
        columns = {row[1] for row in cursor.fetchall()}
    if not columns.intersection(LEGACY_COLUMNS):
        return
    schema_editor._remake_table(EmailProvider)


class Migration(migrations.Migration):

    dependencies = [
        ('practices', '0005_booking_rules_handoff_ai'),
    ]

    operations = [
        migrations.RunPython(repair_emailprovider_table, migrations.RunPython.noop),
    ]
