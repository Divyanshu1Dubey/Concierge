"""Phase 6: no published credentials, safe demo seeding, compromised-account rotation."""
import io
import pathlib
import re

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.practices.models import Practice
from apps.users.models import User

ROOT = pathlib.Path(__file__).resolve().parents[2]


class CredentialExposureTests(TestCase):
    def test_no_password_literals_in_login_page_or_seeds(self):
        login = (ROOT / 'frontend/src/components/auth/LoginPage.tsx').read_text(encoding='utf-8')
        self.assertNotRegex(login, r"password:\s*'")
        self.assertNotIn('divyanshu@heyjarvis.ai', login)
        self.assertIn('import.meta.env.DEV', login)
        seed = (ROOT / 'backend/apps/users/management/commands/seed_production_logins.py').read_text(encoding='utf-8')
        self.assertIsNone(re.search(r"'password'\s*:\s*'", seed))

    def test_seed_does_nothing_outside_demo_mode(self):
        call_command('seed_production_logins', stdout=io.StringIO())
        self.assertFalse(Practice.objects.filter(slug='heyjarvis-demo-dental').exists())
        self.assertFalse(User.objects.filter(email__in=['doctor@heyjarvis-demo.com', 'divyanshu@heyjarvis.ai']).exists())

    @override_settings(DEMO_ACCOUNTS_ENABLED=True, DEMO_ACCOUNT_PASSWORD='')
    def test_demo_seed_without_password_creates_unusable_logins_and_no_agency_admin(self):
        call_command('seed_production_logins', stdout=io.StringIO())
        doc = User.objects.get(email='doctor@heyjarvis-demo.com')
        self.assertFalse(doc.has_usable_password())
        self.assertFalse(User.objects.filter(email='divyanshu@heyjarvis.ai').exists())
        self.assertFalse(User.objects.filter(is_superuser=True).exists())

    @override_settings(DEMO_ACCOUNTS_ENABLED=True, DEMO_ACCOUNT_PASSWORD='')
    def test_restart_does_not_overwrite_a_rotated_password(self):
        call_command('seed_production_logins', stdout=io.StringIO())
        doc = User.objects.get(email='doctor@heyjarvis-demo.com')
        doc.set_password('Privately-Rotated-Passphrase-9')
        doc.save()
        call_command('seed_production_logins', stdout=io.StringIO())  # what start.sh runs on every boot
        doc.refresh_from_db()
        self.assertTrue(doc.check_password('Privately-Rotated-Passphrase-9'))

    @override_settings(DEMO_ACCOUNTS_ENABLED=True, DEMO_ACCOUNT_PASSWORD='Private-Demo-Passphrase-42')
    def test_private_demo_password_from_environment(self):
        call_command('seed_production_logins', stdout=io.StringIO())
        self.assertTrue(User.objects.get(email='frontdesk@heyjarvis-demo.com').check_password('Private-Demo-Passphrase-42'))

    def test_lock_command_covers_published_accounts(self):
        User.objects.create_user(username='divyanshu@heyjarvis.ai', email='divyanshu@heyjarvis.ai',
                                 password='Was-Public-Passphrase-1', role='AGENCY_ADMIN', is_superuser=True)
        User.objects.create_user(username='keep@agency.test', email='keep@agency.test',
                                 password='Real-Admin-Passphrase-77', role='AGENCY_ADMIN')
        out = io.StringIO()
        call_command('lock_demo_accounts', stdout=out)  # dry run lists it
        self.assertIn('divyanshu@heyjarvis.ai', out.getvalue())
        self.assertTrue(User.objects.get(email='divyanshu@heyjarvis.ai').has_usable_password())
        call_command('lock_demo_accounts', '--confirm', '--deactivate', stdout=io.StringIO())
        locked = User.objects.get(email='divyanshu@heyjarvis.ai')
        self.assertFalse(locked.has_usable_password())
        self.assertFalse(locked.is_active)
        self.assertTrue(User.objects.get(email='keep@agency.test').check_password('Real-Admin-Passphrase-77'))