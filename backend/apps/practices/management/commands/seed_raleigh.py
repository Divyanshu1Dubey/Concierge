"""
Management command to seed the database with Raleigh Comprehensive Dentistry and default users.
"""
from django.core.management.base import BaseCommand
from apps.users.seed_data import seed_all_demo_data, demo_accounts_enabled


class Command(BaseCommand):
    help = "Seed database with Raleigh Dentistry practices and demo users for all roles"

    def handle(self, *args, **options):
        if not demo_accounts_enabled():
            # Production boots run this command; never create demo practices there.
            self.stdout.write("Demo mode is off (ENABLE_DEMO_ACCOUNTS=false): skipping demo practices and accounts.")
            return
        self.stdout.write("Seeding Raleigh Comprehensive Dentistry & Default Accounts...")
        accounts = seed_all_demo_data()
        for acc in accounts:
            self.stdout.write(self.style.SUCCESS(f"  Ensured {acc['role']}: {acc['email']}"))
        self.stdout.write(self.style.SUCCESS("\nDatabase seeding completed successfully!"))
