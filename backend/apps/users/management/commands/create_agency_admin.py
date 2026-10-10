"""
Create (or re-invite) the agency administrator without any default password.

    python manage.py create_agency_admin --email you@agency.com --first-name Ana --last-name Lee

The account gets an unusable password and a one-time, expiring "set your password"
link. The link is emailed when SMTP is configured; otherwise (or with --print-link)
it is printed to this terminal only. Re-running never creates a duplicate: it
re-issues the link for the existing agency admin. An existing practice account is
never promoted unless --promote is given explicitly.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from apps.users.account_emails import send_set_password_email, set_password_link
from apps.users.models import User


class Command(BaseCommand):
    help = 'Create or re-invite the agency administrator via a one-time set-password link.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--first-name', default='')
        parser.add_argument('--last-name', default='')
        parser.add_argument('--promote', action='store_true',
                            help='Allow giving agency access to an existing non-agency account.')
        parser.add_argument('--print-link', action='store_true',
                            help='Print the one-time link here instead of emailing it.')

    def handle(self, *args, **opts):
        email = opts['email'].strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError(f'Invalid email address: {email}')

        user = User.objects.filter(email__iexact=email).first()
        if user and not user.is_agency_admin and not opts['promote']:
            raise CommandError(
                f'{email} already exists as a {user.role or "practice"} account. '
                'Re-run with --promote only if this person should have agency-wide access.'
            )
        created = user is None
        if created:
            user = User(email=email, username=email)
            user.set_unusable_password()
        user.first_name = opts['first_name'] or user.first_name
        user.last_name = opts['last_name'] or user.last_name
        user.role = 'AGENCY_ADMIN'
        user.is_active = True
        user.save()

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action} agency administrator {email}.'))

        base = (getattr(settings, 'FRONTEND_URL', '') or getattr(settings, 'APP_PUBLIC_URL', ''))
        if not base:
            self.stdout.write(self.style.WARNING(
                'APP_PUBLIC_URL is not set, so the link has no domain. Set it, then re-run this command.'))
        hours = int(getattr(settings, 'PASSWORD_RESET_TIMEOUT', 259200) // 3600)
        if not opts['print_link'] and getattr(settings, 'EMAIL_CONFIGURED', False):
            if send_set_password_email(user, None, invite=True):
                self.stdout.write(f'Invite email accepted by the mail server for {email} (link valid {hours}h). '
                                  'Check that it arrived; re-run with --print-link if it did not.')
                return
            self.stdout.write(self.style.WARNING('Sending the invite email failed; showing the link instead.'))
        self.stdout.write(f'One-time set-password link (valid {hours}h, single use, do not share or log it):')
        self.stdout.write(set_password_link(user, None, invite=True))
