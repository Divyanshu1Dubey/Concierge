"""
Create a consistent backup of the database.

SQLite: copies the live database with the sqlite3 online-backup API into ./backups/.
PostgreSQL: prints the pg_dump command to run (use your host's managed backups too).

    python manage.py backup_db [--dir PATH] [--keep 14]
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Back up the database (SQLite file copy; instructions for PostgreSQL).'

    def add_arguments(self, parser):
        parser.add_argument('--dir', default=str(Path(settings.BASE_DIR) / 'backups'))
        parser.add_argument('--keep', type=int, default=14, help='How many SQLite backups to keep')

    def handle(self, *args, **opts):
        db = settings.DATABASES['default']
        engine = db['ENGINE']
        if 'sqlite3' in engine:
            source = Path(db['NAME'])
            if not source.exists():
                raise CommandError(f'Database file not found: {source}')
            out_dir = Path(opts['dir'])
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / f"{source.stem}-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
            src = sqlite3.connect(str(source))
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
                # A WAL-mode source yields a WAL-mode copy; store backups as a single
                # self-contained file so they can be copied/restored without sidecars.
                dst.execute('PRAGMA journal_mode=DELETE')
                check = dst.execute('PRAGMA integrity_check').fetchone()[0]
            finally:
                dst.close()
                src.close()
            if check != 'ok':
                raise CommandError(f'Backup integrity check failed: {check}')
            backups = sorted(out_dir.glob(f"{source.stem}-*.sqlite3"))
            for old in backups[:-opts['keep']] if opts['keep'] > 0 else []:
                old.unlink()
            self.stdout.write(self.style.SUCCESS(f'Backup written and verified: {target}'))
        elif 'postgresql' in engine:
            self.stdout.write('PostgreSQL detected. Run (with your DATABASE_URL):')
            self.stdout.write('  pg_dump --format=custom --no-owner "$DATABASE_URL" > heyjarvis-$(date +%Y%m%d).dump')
            self.stdout.write('Restore: pg_restore --clean --no-owner -d "$DATABASE_URL" heyjarvis-YYYYMMDD.dump')
        else:
            raise CommandError(f'Unsupported database engine: {engine}')
