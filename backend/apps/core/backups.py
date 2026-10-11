"""
Backup verification and restore drills for the SQLite database.

A backup only counts as a recovery mechanism once it has been opened and checked. ``verify_backup``
opens a backup read-only and confirms integrity and the presence of the core tables; ``restore_drill``
copies a backup to a temporary file (never over the live database), migrates that copy to the current
schema in a separate process and runs Django's system check against it.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from django.conf import settings

CORE_TABLES = ('practices_practice', 'users_user', 'appointments_appointment', 'conversations_conversation',
               'django_migrations')


def backup_dir() -> Path:
    db = settings.DATABASES['default']
    configured = getattr(settings, 'BACKUP_DIR', '')
    if configured:
        return Path(configured)
    return Path(str(db['NAME'])).parent / 'backups'


def list_backups(directory=None) -> list:
    d = Path(directory) if directory else backup_dir()
    if not d.exists():
        return []
    return sorted(d.glob('*.sqlite3'), key=lambda p: p.stat().st_mtime)


def verify_backup(path) -> dict:
    """Open read-only; return {'ok', 'integrity', 'tables', 'counts', 'migrations', 'size', 'age_hours', 'error'}."""
    path = Path(path)
    out = {'path': path.name, 'ok': False, 'integrity': None, 'counts': {}, 'error': ''}
    if not path.exists():
        out['error'] = 'Backup file not found.'
        return out
    out['size'] = path.stat().st_size
    out['age_hours'] = round((time.time() - path.stat().st_mtime) / 3600, 1)
    try:
        conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
    except sqlite3.Error as exc:
        out['error'] = f'Cannot open backup ({type(exc).__name__}).'
        return out
    try:
        out['integrity'] = conn.execute('PRAGMA integrity_check').fetchone()[0]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        out['tables'] = len(tables)
        missing = [t for t in CORE_TABLES if t not in tables]
        if missing:
            out['error'] = 'Missing core tables: ' + ', '.join(missing)
        for t in CORE_TABLES:
            if t in tables:
                out['counts'][t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        if 'django_migrations' in tables:
            out['migrations'] = conn.execute('SELECT COUNT(*) FROM django_migrations').fetchone()[0]
        out['ok'] = out['integrity'] == 'ok' and not missing
    except sqlite3.DatabaseError as exc:
        out['error'] = f'Backup is not a readable database ({type(exc).__name__}).'
    finally:
        conn.close()
    return out


def restore_drill(path=None, migrate=True, timeout=300) -> dict:
    """Restore a backup into a temporary database and prove it works. The live database is never touched."""
    backups = list_backups()
    source = Path(path) if path else (backups[-1] if backups else None)
    if source is None:
        return {'ok': False, 'error': 'No backups found.', 'steps': []}
    steps = []
    verified = verify_backup(source)
    steps.append({'step': 'verify', 'ok': verified['ok'], 'detail': verified.get('error') or f"integrity {verified['integrity']}"})
    if not verified['ok']:
        return {'ok': False, 'source': source.name, 'steps': steps, 'verify': verified}
    live = Path(str(settings.DATABASES['default']['NAME'])).resolve()
    tmpdir = tempfile.mkdtemp(prefix='restore-drill-')
    target = Path(tmpdir) / 'restored.sqlite3'
    try:
        if target.resolve() == live:
            raise RuntimeError('refusing to restore over the live database')
        src = sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True)
        dst = sqlite3.connect(str(target))
        src.backup(dst)
        src.close()
        dst.close()
        steps.append({'step': 'restore_to_temp', 'ok': True, 'detail': 'copied with the online backup API'})
        if migrate:
            env = dict(os.environ, SQLITE_PATH=str(target), DJANGO_SETTINGS_MODULE='config.settings')
            manage = Path(settings.BASE_DIR) / 'manage.py'
            if not manage.exists():
                manage = Path(settings.BASE_DIR) / 'backend' / 'manage.py'
            for name, cmd in (('migrate', ['migrate', '--noinput']), ('check', ['check'])):
                proc = subprocess.run([sys.executable, str(manage)] + cmd, cwd=str(manage.parent), env=env,
                                      capture_output=True, text=True, timeout=timeout)
                steps.append({'step': name, 'ok': proc.returncode == 0,
                              'detail': (proc.stdout + proc.stderr).strip().splitlines()[-1][:200] if (proc.stdout + proc.stderr).strip() else ''})
                if proc.returncode != 0:
                    break
        after = verify_backup(target)
        steps.append({'step': 'verify_restored', 'ok': after['ok'], 'detail': f"{after.get('migrations')} migrations recorded"})
        return {'ok': all(s['ok'] for s in steps), 'source': source.name, 'steps': steps,
                'counts': after.get('counts', {})}
    except Exception as exc:
        steps.append({'step': 'error', 'ok': False, 'detail': f'{type(exc).__name__}: {str(exc)[:160]}'})
        return {'ok': False, 'source': source.name, 'steps': steps}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
