"""
Repair schema drift: some older SQLite databases were created with
appointments_appointment.service_id as NOT NULL, while the model (and migration
history) define it as nullable. Requests from practices without services then
fail to save. On SQLite, when the column is NOT NULL, rebuild the table with
Django's schema editor (rows are copied); everywhere else this is a no-op.
"""
from django.db import migrations


def repair_service_column(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'sqlite':
        return
    Appointment = apps.get_model('appointments', 'Appointment')
    table = Appointment._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f'PRAGMA table_info("{table}")')
        columns = {row[1]: row for row in cursor.fetchall()}
    column = columns.get('service_id')
    if not column or column[3] != 1:  # already nullable
        return
    # Recreate the table from the (correct) model definition, copying all rows -
    # the same procedure Django's SQLite backend uses for any column change.
    schema_editor._remake_table(Appointment)


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0003_appointment_ai_summary_appointment_intent_and_more'),
    ]

    operations = [
        migrations.RunPython(repair_service_column, migrations.RunPython.noop),
    ]
