"""Prove a backup can be restored: copy it to a temporary database, migrate it and run checks.

    python manage.py restore_drill [--file PATH] [--no-migrate]

Never writes to the live database.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.core.backups import restore_drill


class Command(BaseCommand):
    help = 'Restore the latest (or given) backup into a temporary database and verify it.'

    def add_arguments(self, parser):
        parser.add_argument('--file', help='Backup file to test (default: newest in the backup directory)')
        parser.add_argument('--no-migrate', action='store_true', help='Only verify and copy; skip migrate/check')

    def handle(self, *args, **opts):
        result = restore_drill(opts.get('file'), migrate=not opts['no_migrate'])
        for s in result.get('steps', []):
            self.stdout.write(f"{'OK  ' if s['ok'] else 'FAIL'} {s['step']}: {s['detail']}")
        if result.get('counts'):
            self.stdout.write('Rows: ' + ', '.join(f'{k}={v}' for k, v in result['counts'].items()))
        if not result['ok']:
            raise CommandError(result.get('error') or f"Restore drill failed for {result.get('source')}")
        self.stdout.write(self.style.SUCCESS(f"Restore drill passed for {result['source']}"))
