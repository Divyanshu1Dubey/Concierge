# Generated for automated production seeding of HeyJarvis Demo Dental & accounts
from django.db import migrations


def seed_production_logins(apps, schema_editor):
    try:
        from apps.users.management.commands.seed_production_logins import seed_production_accounts
        seed_production_accounts()
    except Exception as e:
        print(f"Warning during seed production logins migration: {e}")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_seed_demo_accounts"),
    ]

    operations = [
        migrations.RunPython(seed_production_logins, reverse_code=migrations.RunPython.noop),
    ]
