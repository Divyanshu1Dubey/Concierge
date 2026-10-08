"""
Management command to seed the database with Raleigh Comprehensive Dentistry and default users.
"""
from django.core.management.base import BaseCommand
from apps.users.seed_data import seed_all_demo_data


class Command(BaseCommand):
    help = "Seed database with Raleigh Dentistry practices and demo users for all roles"

    def handle(self, *args, **options):
        self.stdout.write("Seeding Raleigh Comprehensive Dentistry & Default Accounts...")
        accounts = seed_all_demo_data()
        for acc in accounts:
            self.stdout.write(self.style.SUCCESS(f"  Ensured {acc['role']}: {acc['email']} / {acc['password']}"))
        self.stdout.write(self.style.SUCCESS("\nDatabase seeding completed successfully!"))
