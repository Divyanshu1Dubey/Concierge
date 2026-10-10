"""
Data retention: delete patient conversations, requests and email threads older than N days.

    python manage.py purge_old_data --days 2555            # dry run (default): counts only
    python manage.py purge_old_data --days 2555 --confirm  # actually delete

DATA_RETENTION_DAYS can provide the default. Audit logs are kept.
"""
import os
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = 'Delete patient data older than the retention period (dry run unless --confirm).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=int(os.environ.get('DATA_RETENTION_DAYS', 0) or 0))
        parser.add_argument('--practice', help='Limit to one practice slug')
        parser.add_argument('--confirm', action='store_true', help='Actually delete (otherwise dry run)')

    def handle(self, *args, **opts):
        from apps.appointments.models import Appointment
        from apps.conversations.models import Conversation
        from apps.emails.models import EmailThread
        from apps.practices.models import Practice

        days = opts['days']
        if days < 30:
            raise CommandError('Provide --days (minimum 30) or set DATA_RETENTION_DAYS.')
        cutoff = timezone.now() - timedelta(days=days)
        scope = {}
        if opts.get('practice'):
            practice = Practice.objects.filter(slug=opts['practice']).first()
            if not practice:
                raise CommandError(f"No practice with slug {opts['practice']!r}")
            scope = {'practice': practice}

        querysets = {
            'appointment requests': Appointment.objects.filter(created_at__lt=cutoff, **scope),
            'conversations': Conversation.objects.filter(last_activity_at__lt=cutoff, **scope),
            'email threads': EmailThread.objects.filter(last_message_at__lt=cutoff, **scope),
        }
        for label, qs in querysets.items():
            self.stdout.write(f"{label}: {qs.count()} older than {days} days")
        if not opts['confirm']:
            self.stdout.write(self.style.WARNING('Dry run only. Re-run with --confirm to delete.'))
            return
        with transaction.atomic():
            for label, qs in querysets.items():
                deleted, _ = qs.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted {label} (rows incl. related: {deleted})"))
