"""
Lock the built-in demo accounts (admin@/doctor@/desk@raleighdentistry.com, ...).

Use this on any deployment where demo logins were ever enabled: their passwords
were well known. Dry run by default; nothing changes without --confirm.

    python manage.py lock_demo_accounts                          # show what would change
    python manage.py lock_demo_accounts --confirm                # unusable passwords + revoke sessions
    python manage.py lock_demo_accounts --confirm --deactivate   # also disable the accounts

Practice data (requests, conversations, settings) is not touched.
"""
from django.core.management.base import BaseCommand

from apps.users.models import User
from apps.users.seed_data import DEMO_ACCOUNTS


class Command(BaseCommand):
    help = 'Disable password login for the built-in demo accounts (dry run unless --confirm).'

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true', help='Apply the changes.')
        parser.add_argument('--deactivate', action='store_true',
                            help='Also mark the accounts inactive (blocks existing access tokens immediately).')

    def handle(self, *args, **opts):
        users = list(User.objects.filter(email__in=list(DEMO_ACCOUNTS)))
        if not users:
            self.stdout.write('No demo accounts found.')
            return
        for user in users:
            state = 'active' if user.is_active else 'inactive'
            login = 'password login ON' if user.has_usable_password() else 'password login off'
            self.stdout.write(f'{user.email}: {state}, {login}')
        if not opts['confirm']:
            self.stdout.write('Dry run only. Re-run with --confirm to lock these accounts.')
            return

        try:
            from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        except Exception:  # blacklist app not installed
            OutstandingToken = None
        revoked = 0
        for user in users:
            user.set_unusable_password()
            fields = ['password']
            if opts['deactivate']:
                user.is_active = False
                fields.append('is_active')
            user.save(update_fields=fields)
            if OutstandingToken is not None:
                for token in OutstandingToken.objects.filter(user=user):
                    _, created = BlacklistedToken.objects.get_or_create(token=token)
                    revoked += int(created)
        self.stdout.write(self.style.SUCCESS(
            f'Locked {len(users)} demo account(s); revoked {revoked} refresh token(s)'
            + ('; accounts deactivated.' if opts['deactivate'] else '.')
        ))
