"""
Management command to seed production demo accounts and practice for HeyJarvis Concierge.
Ensures:
- Practice: 'heyjarvis-demo-dental' (HeyJarvis Demo Dental)
- Agency Admin: divyanshu@heyjarvis.ai / avisirheyjarvis2026
- Practice Admin: doctor@heyjarvis-demo.com / DemoDoctor#2026
- Front Desk: frontdesk@heyjarvis-demo.com / DemoFrontDesk#2026
"""
from django.core.management.base import BaseCommand
from apps.practices.models import Practice, BookingRules, PracticeSettings, Domain
from apps.users.models import User

ACCOUNTS_DATA = [
    {
        'email': 'divyanshu@heyjarvis.ai',
        'password': 'avisirheyjarvis2026',
        'role': 'AGENCY_ADMIN',
        'first_name': 'Divyanshu',
        'last_name': 'Admin',
        'superuser': True,
        'practice_slug': None,
    },
    {
        'email': 'doctor@heyjarvis-demo.com',
        'password': 'DemoDoctor#2026',
        'role': 'PRACTICE_ADMIN',
        'first_name': 'Demo',
        'last_name': 'Doctor',
        'superuser': False,
        'practice_slug': 'heyjarvis-demo-dental',
    },
    {
        'email': 'frontdesk@heyjarvis-demo.com',
        'password': 'DemoFrontDesk#2026',
        'role': 'FRONT_DESK',
        'first_name': 'Demo',
        'last_name': 'FrontDesk',
        'superuser': False,
        'practice_slug': 'heyjarvis-demo-dental',
    },
]


def seed_production_accounts(stdout=None):
    practice, _ = Practice.objects.get_or_create(
        slug="heyjarvis-demo-dental",
        defaults=dict(
            name="HeyJarvis Demo Dental",
            email="divyanshu@heyjarvis.ai",
            phone="(919) 555-0100",
            address="123 Demo Street",
            city="Raleigh",
            state="NC",
            zip_code="27601",
            timezone="America/New_York",
            website="https://web-production-41fc3c.up.railway.app",
        ),
    )
    practice.active = True
    practice.save()

    BookingRules.objects.get_or_create(practice=practice)
    PracticeSettings.objects.get_or_create(
        practice=practice,
        defaults={
            'default_from_name': practice.name,
            'default_from_email': practice.email,
        }
    )

    # Ensure allowed domains for widget verification
    allowed_domains = ['web-production-41fc3c.up.railway.app', 'localhost', '127.0.0.1']
    for domain_name in allowed_domains:
        Domain.objects.get_or_create(
            practice=practice,
            hostname=domain_name,
            defaults={'status': 'CONNECTED'}
        )

    for item in ACCOUNTS_DATA:
        p = practice if item['practice_slug'] else None
        u = User.objects.filter(email__iexact=item['email']).first() or User(email=item['email'], username=item['email'])
        u.first_name = item['first_name']
        u.last_name = item['last_name']
        u.role = item['role']
        u.practice = p
        u.is_active = True
        u.is_superuser = item['superuser']
        u.is_staff = item['superuser']
        u.set_password(item['password'])
        u.save()
        if stdout:
            stdout.write(f"  OK {item['role']} {item['email']}")


class Command(BaseCommand):
    help = "Seed production demo accounts and practice for HeyJarvis Demo Dental"

    def handle(self, *args, **options):
        self.stdout.write("Seeding HeyJarvis Demo Dental and production test accounts...")
        seed_production_accounts(self.stdout)
        self.stdout.write(self.style.SUCCESS("Production demo accounts verified successfully!"))
