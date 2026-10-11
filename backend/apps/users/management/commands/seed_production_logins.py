"""
Seed the "HeyJarvis Demo Dental" practice and its demo staff accounts - demo mode only.

Runs only when ENABLE_DEMO_ACCOUNTS=true. No password is stored in code: demo accounts get
DEMO_ACCOUNT_PASSWORD when it is set (keep it private), otherwise new accounts get an unusable
password and existing passwords are left unchanged. The agency administrator is never created
here; use `python manage.py create_agency_admin --email ...` (one-time set-password link).
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from apps.practices.models import Practice, BookingRules, PracticeSettings, Domain
from apps.users.models import User

# Accounts whose earlier passwords were published; `lock_demo_accounts` disables them.
EXPOSED_ACCOUNTS = ['divyanshu@heyjarvis.ai', 'doctor@heyjarvis-demo.com', 'frontdesk@heyjarvis-demo.com']

ACCOUNTS_DATA = [
    {
        'email': 'doctor@heyjarvis-demo.com',
        'role': 'PRACTICE_ADMIN',
        'first_name': 'Demo',
        'last_name': 'Doctor',
    },
    {
        'email': 'frontdesk@heyjarvis-demo.com',
        'role': 'FRONT_DESK',
        'first_name': 'Demo',
        'last_name': 'FrontDesk',
    },
]


def seed_production_accounts(stdout=None):
    if not getattr(settings, 'DEMO_ACCOUNTS_ENABLED', False):
        if stdout:
            stdout.write("Demo mode is off (ENABLE_DEMO_ACCOUNTS=false): nothing seeded.")
        return
    practice, _ = Practice.objects.get_or_create(
        slug="heyjarvis-demo-dental",
        defaults=dict(
            name="HeyJarvis Demo Dental",
            email="demo@heyjarvis-demo.com",
            phone="(919) 555-0100",
            address="123 Demo Street",
            city="Raleigh",
            state="NC",
            zip_code="27601",
            timezone="America/New_York",
        ),
    )
    BookingRules.objects.get_or_create(practice=practice)
    PracticeSettings.objects.get_or_create(practice=practice)
    for domain_name in ['localhost', '127.0.0.1']:
        Domain.objects.get_or_create(practice=practice, hostname=domain_name, defaults={'status': 'CONNECTED'})

    password = getattr(settings, 'DEMO_ACCOUNT_PASSWORD', '') or ''
    for item in ACCOUNTS_DATA:
        u = User.objects.filter(email__iexact=item['email']).first()
        created = u is None
        if created:
            u = User(email=item['email'], username=item['email'], first_name=item['first_name'],
                     last_name=item['last_name'], role=item['role'], practice=practice, is_active=True)
        if password:
            u.set_password(password)
        elif created:
            u.set_unusable_password()
        u.save()
        if stdout:
            note = '' if (password or not created) else ' (no password set)'
            stdout.write(f"  OK {item['role']} {item['email']}{note}")


class Command(BaseCommand):
    help = "Seed the HeyJarvis Demo Dental practice and demo staff accounts (demo mode only)"

    def handle(self, *args, **options):
        seed_production_accounts(self.stdout)
