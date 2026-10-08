"""
Management command to seed the database with Raleigh Comprehensive Dentistry and default users.
"""
from django.core.management.base import BaseCommand
from apps.practices.models import Practice, BookingRules, PracticeSettings
from apps.users.models import User


class Command(BaseCommand):
    help = "Seed database with Raleigh Dentistry practices and demo users for all roles"

    def handle(self, *args, **options):
        self.stdout.write("Seeding Raleigh Comprehensive Dentistry & Default Accounts...")

        # 1. Practice Setup
        practice, _ = Practice.objects.get_or_create(
            slug="raleigh-dentistry",
            defaults={
                "name": "Raleigh Comprehensive & Cosmetic Dentistry",
                "email": "frontdesk@raleighdentistry.com",
                "phone": "(919) 555-0142",
                "address": "123 Oakwood Ave, Raleigh, NC 27601",
                "timezone": "America/New_York",
                "website": "https://raleighdentistry.com",
                "active": True,
            },
        )

        # Also ensure raleigh-comprehensive slug alias points or exists
        alt_practice, _ = Practice.objects.get_or_create(
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

        for p in [practice, alt_practice]:
            BookingRules.objects.get_or_create(
                practice=p,
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
            PracticeSettings.objects.get_or_create(
                practice=p,
                defaults={
                    "email_from_name": "Raleigh Comprehensive Dentistry",
                    "email_from_address": "frontdesk@raleighdentistry.com",
                    "email_provider": "smtp",
                    "smtp_port": 587,
                    "smtp_use_tls": True,
                },
            )

        # 2. Users for all roles
        users_to_seed = [
            {
                "email": "admin@raleighdentistry.com",
                "first_name": "Agency",
                "last_name": "Admin",
                "role": "AGENCY_ADMIN",
                "is_staff": True,
                "is_superuser": True,
                "password": "Password123!",
                "practice": practice,
            },
            {
                "email": "doctor@raleighdentistry.com",
                "first_name": "Dr. Sarah",
                "last_name": "Brody",
                "role": "PRACTICE_ADMIN",
                "is_staff": True,
                "is_superuser": False,
                "password": "Password123!",
                "practice": practice,
            },
            {
                "email": "brody@raleighdentistry.com",
                "first_name": "Dr. Sarah",
                "last_name": "Brody",
                "role": "PRACTICE_ADMIN",
                "is_staff": True,
                "is_superuser": False,
                "password": "Password123!",
                "practice": practice,
            },
            {
                "email": "desk@raleighdentistry.com",
                "first_name": "Emma",
                "last_name": "Davis",
                "role": "FRONT_DESK",
                "is_staff": True,
                "is_superuser": False,
                "password": "Password123!",
                "practice": practice,
            },
            {
                "email": "admin@raleighcomprehensive.com",
                "first_name": "Office",
                "last_name": "Manager",
                "role": "OWNER",
                "is_staff": True,
                "is_superuser": True,
                "password": "raleigh2024!",
                "practice": alt_practice,
            },
            {
                "email": "desk@raleighcomprehensive.com",
                "first_name": "Front",
                "last_name": "Desk",
                "role": "FRONT_DESK",
                "is_staff": True,
                "is_superuser": False,
                "password": "desk2024!",
                "practice": alt_practice,
            },
        ]

        for u_data in users_to_seed:
            pwd = u_data.pop("password")
            email = u_data["email"]
            u_data["username"] = email
            user = User.objects.filter(email=email).first()
            if not user:
                user = User.objects.create(**u_data)
                created = True
            else:
                for k, v in u_data.items():
                    setattr(user, k, v)
                created = False
            user.set_password(pwd)
            user.save()
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"  {action} {u_data['role']}: {user.email} / {pwd}"))

        self.stdout.write(self.style.SUCCESS("\nDatabase seeding completed successfully!"))
