"""
Management command to seed the database with Raleigh Comprehensive Dentistry and default users.
"""
from django.core.management.base import BaseCommand
from apps.users.seed_data import seed_all_demo_data, demo_accounts_enabled


class Command(BaseCommand):
    help = "Seed database with Raleigh Dentistry practices and demo users for all roles"

    def handle(self, *args, **options):
        self.stdout.write("Seeding Raleigh Comprehensive Dentistry & Default Accounts...")
        accounts = seed_all_demo_data()
        if not demo_accounts_enabled():
            self.stdout.write("  Demo accounts disabled (set ENABLE_DEMO_ACCOUNTS=true to provision them).")
        for acc in accounts:
            self.stdout.write(self.style.SUCCESS(f"  Ensured {acc['role']}: {acc['email']}"))
        self.stdout.write(self.style.SUCCESS("\nDatabase seeding completed successfully!"))
