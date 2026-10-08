"""
Management command to seed the database with Raleigh Comprehensive & Cosmetic Dentistry.
"""
from django.core.management.base import BaseCommand
from apps.practices.models import Practice, BookingRules, PracticeSettings
from apps.users.models import User


class Command(BaseCommand):
    help = "Seed database with Raleigh Comprehensive & Cosmetic Dentistry"

    def handle(self, *args, **options):
        self.stdout.write("Seeding Raleigh Comprehensive & Cosmetic Dentistry...")

        # Create Practice
        practice, created = Practice.objects.get_or_create(
            slug="raleigh-comprehensive",
            defaults={
                "name": "Raleigh Comprehensive & Cosmetic Dentistry",
                "email": "frontdesk@raleighcomprehensive.com",
                "phone": "(919) 555-0142",
                "address": "123 Oakwood Ave, Raleigh, NC 27601",
                "timezone": "America/New_York",
                "website": "https://raleighcomprehensive.com",
                "active": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"  Created practice: {practice.name}"))
        else:
            self.stdout.write(f"  Practice already exists: {practice.name}")

        # Create Booking Rules
        rules, created = BookingRules.objects.get_or_create(
            practice=practice,
            defaults={
                "new_patient_duration": 90,
                "doctor_duration": 30,
                "hygiene_duration": 60,
                "emergency_duration": 60,
                "confirmation_hours": 48,
                "no_show_fee": 65.00,
                "financing_options": ["Cherry", "CareCredit"],
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("  Created booking rules"))

        # Create Practice Settings
        settings_obj, created = PracticeSettings.objects.get_or_create(
            practice=practice,
            defaults={
                "email_from_name": "Raleigh Comprehensive & Cosmetic Dentistry",
                "email_from_address": "frontdesk@raleighcomprehensive.com",
                "email_provider": "smtp",
                "smtp_host": "",
                "smtp_port": 587,
                "smtp_use_tls": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("  Created practice settings"))

        # Create Owner user (password: raleigh2024!)
        owner, created = User.objects.get_or_create(
            email="admin@raleighcomprehensive.com",
            defaults={
                "first_name": "Office",
                "last_name": "Manager",
                "role": "OWNER",
                "practice": practice,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            owner.set_password("raleigh2024!")
            owner.save()
            self.stdout.write(
                self.style.SUCCESS(
                    "  Created owner: admin@raleighcomprehensive.com / raleigh2024!"
                )
            )
        else:
            self.stdout.write("  Owner already exists")

        # Create Front Desk user (password: desk2024!)
        front_desk, created = User.objects.get_or_create(
            email="desk@raleighcomprehensive.com",
            defaults={
                "first_name": "Front",
                "last_name": "Desk",
                "role": "FRONT_DESK",
                "practice": practice,
                "is_staff": True,
            },
        )
        if created:
            front_desk.set_password("desk2024!")
            front_desk.save()
            self.stdout.write(
                self.style.SUCCESS(
                    "  Created front desk: desk@raleighcomprehensive.com / desk2024!"
                )
            )
        else:
            self.stdout.write("  Front desk user already exists")

        self.stdout.write(self.style.SUCCESS("\nSeeding complete!"))
        self.stdout.write("\nCredentials:")
        self.stdout.write("  Owner:   admin@raleighcomprehensive.com / raleigh2024!")
        self.stdout.write("  Front Desk: desk@raleighcomprehensive.com / desk2024!")
