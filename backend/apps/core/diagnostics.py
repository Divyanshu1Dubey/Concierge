"""
Production-readiness diagnostics for agency admins.

Each check returns {'key', 'label', 'status': ok|warn|fail|info, 'detail', 'fix'}. Checks only read
configuration and the database; no secret value is ever included in the output.
"""
import os
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone


def _check(key, label, status, detail, fix=''):
    return {'key': key, 'label': label, 'status': status, 'detail': detail, 'fix': fix if status != 'ok' else ''}


def check_database():
    out = []
    try:
        with connection.cursor() as c:
            c.execute('SELECT 1')
        out.append(_check('database', 'Database reachable', 'ok', f"{connection.vendor} database responds."))
    except Exception as exc:
        return [_check('database', 'Database reachable', 'fail', f'Database error ({type(exc).__name__}).',
                       'Check SQLITE_PATH and that the volume is mounted.')]
    try:
        from django.db.migrations.executor import MigrationExecutor
        ex = MigrationExecutor(connection)
        pending = ex.migration_plan(ex.loader.graph.leaf_nodes())
        out.append(_check('migrations', 'Database schema up to date', 'fail' if pending else 'ok',
                          f'{len(pending)} migration(s) not applied.' if pending else 'All migrations applied.',
                          'Run python manage.py migrate (after a verified backup).'))
    except Exception as exc:
        out.append(_check('migrations', 'Database schema up to date', 'warn', f'Could not inspect migrations ({type(exc).__name__}).'))
    if connection.vendor == 'sqlite':
        path = Path(str(settings.DATABASES['default']['NAME']))
        try:
            usage = shutil.disk_usage(path.parent)
            free_mb = usage.free // (1024 * 1024)
            size_mb = round(path.stat().st_size / (1024 * 1024), 1) if path.exists() else 0
            status = 'fail' if free_mb < 200 else 'warn' if free_mb < 1024 else 'ok'
            out.append(_check('disk', 'Free disk space for the database', status,
                              f'{free_mb:,} MB free; database is {size_mb} MB.',
                              'Increase the volume size before backups or writes start failing.'))
            writable = os.access(path.parent, os.W_OK)
            out.append(_check('db_writable', 'Database folder is writable', 'ok' if writable else 'fail',
                              'Writable.' if writable else 'The database folder is read-only.',
                              'Mount the data volume read-write.'))
        except OSError as exc:
            out.append(_check('disk', 'Free disk space for the database', 'warn', f'Could not read disk usage ({type(exc).__name__}).'))
    return out


def check_security():
    out = []
    key = getattr(settings, 'SECRET_KEY', '') or ''
    weak = len(key) < 32 or key.startswith('django-insecure') or 'change' in key.lower() or 'default' in key.lower()
    out.append(_check('secret_key', 'Strong secret key', 'fail' if weak else 'ok',
                      'The secret key is short or a placeholder.' if weak else 'Secret key is long and not a placeholder.',
                      'Set DJANGO_SECRET_KEY to a random value of at least 50 characters. Note: changing it requires reconnecting integrations.'))
    out.append(_check('debug', 'Debug mode off', 'fail' if settings.DEBUG else 'ok',
                      'DEBUG is on: error pages can reveal internals.' if settings.DEBUG else 'DEBUG is off.',
                      'Set DJANGO_DEBUG=false in production.'))
    public = getattr(settings, 'APP_PUBLIC_URL', '') or ''
    out.append(_check('public_url', 'Public address configured (HTTPS)', 'ok' if public.startswith('https://') else 'warn',
                      f'APP_PUBLIC_URL is {public}.' if public else 'APP_PUBLIC_URL is not set; email links fall back to the request host.',
                      'Set APP_PUBLIC_URL=https://your-domain so links in emails and OAuth callbacks are correct.'))
    backend = settings.CACHES['default']['BACKEND']
    per_process = 'locmem' in backend
    out.append(_check('shared_cache', 'Rate limits shared across server workers', 'warn' if (per_process and not settings.DEBUG) else 'ok',
                      'The cache is per worker process, so login rate limits and short locks apply per worker '
                      '(about 3x looser with the default 3 workers).' if per_process else 'Cache is shared by all workers.',
                      'Set CACHE_BACKEND=database (uses the existing SQLite file) or REDIS_URL.'))
    local_ok = bool(getattr(settings, 'WIDGET_ALLOW_LOCAL_ORIGINS', True))
    out.append(_check('widget_origins', 'Widget domain list is strict', 'warn' if (local_ok and not settings.DEBUG) else 'ok',
                      "Widget requests from local files, sandboxed iframes and localhost skip each practice's allowed domains."
                      if local_ok else "Only each practice's allowed domains (and this server) can use the widget.",
                      'Set WIDGET_ALLOW_LOCAL_ORIGINS=false once demo pages are served from a real domain.'))
    demo_on = bool(getattr(settings, 'DEMO_ACCOUNTS_ENABLED', False))
    out.append(_check('demo_mode', 'Demo accounts disabled', 'warn' if demo_on else 'ok',
                      'ENABLE_DEMO_ACCOUNTS is on.' if demo_on else 'Demo account seeding is off.',
                      'Set ENABLE_DEMO_ACCOUNTS=false in production.'))
    try:
        from apps.users.management.commands.seed_production_logins import EXPOSED_ACCOUNTS
        from apps.users.models import User
        risky = [u.email for u in User.objects.filter(email__in=EXPOSED_ACCOUNTS, is_active=True) if u.has_usable_password()]
        out.append(_check('exposed_accounts', 'Previously published demo logins locked', 'fail' if risky else 'ok',
                          f'{len(risky)} account(s) whose credentials were once public are still active with a password.' if risky
                          else 'No previously published login is active with a password.',
                          'Run: python manage.py lock_demo_accounts --confirm --deactivate (then create fresh admin access).'))
    except Exception:
        pass
    return out


def check_messaging():
    out = []
    backend = getattr(settings, 'EMAIL_BACKEND', '')
    configured = bool(getattr(settings, 'EMAIL_CONFIGURED', False))
    via = 'Resend (HTTPS)' if 'Resend' in backend else ('SMTP' if 'smtp' in backend.lower() else backend.rsplit('.', 1)[-1])
    status = 'ok' if configured else 'fail'
    detail = f'Email is configured via {via}.' if configured else 'No email provider configured: patients and staff receive nothing.'
    fix = 'Set RESEND_API_KEY (verified domain) or SMTP credentials.'
    if configured and 'smtp' in backend.lower() and os.environ.get('RAILWAY_ENVIRONMENT'):
        status, detail = 'warn', 'SMTP on Railway: the Hobby plan blocks outbound SMTP, so sending may silently fail.'
        fix = 'Use RESEND_API_KEY (HTTPS) or a Railway plan that allows SMTP, then send a test email.'
    out.append(_check('email', 'Email sending', status, detail, fix))
    imap = bool(getattr(settings, 'IMAP_HOST', ''))
    out.append(_check('inbound', 'Patient reply collection', 'ok' if imap else 'warn',
                      'IMAP reply collection is configured.' if imap else 'Patient email replies are not collected.',
                      'Set IMAP_HOST / IMAP_USER / IMAP_PASSWORD for the reply mailbox.'))
    from apps.growth.sms import sms_status
    s = sms_status(None)
    sms_state = {'live': 'ok', 'console': 'warn' if not settings.DEBUG else 'info', 'off': 'info'}[s['mode']]
    out.append(_check('sms', 'Text messaging', sms_state, s['detail'],
                      'Remove SMS_BACKEND=console in production once Twilio is set up.' if s['mode'] == 'console'
                      else 'Optional: add Twilio credentials (and A2P 10DLC registration) to enable texting.'))
    return out


def check_scheduler():
    from apps.growth.jobs import JOBS, scheduler_status
    from apps.growth.models import JobRun
    out = []
    st = scheduler_status()
    secret = st['cron_secret_set']
    out.append(_check('cron_secret', 'Scheduler secret set', 'ok' if secret else 'fail',
                      'CRON_SECRET is set.' if secret else 'CRON_SECRET is empty, so the job endpoint is disabled.',
                      'Set CRON_SECRET to a long random value on the web service.'))
    last = st['last_run']
    out.append(_check('scheduler', 'Scheduled jobs running', 'ok' if st['healthy'] else 'fail',
                      f'Last run {last[:16].replace("T", " ")} UTC.' if last else 'Jobs have never run.',
                      'Add a cron service calling POST /api/v1/growth/cron/run/ with X-Cron-Secret every 10 minutes.'))
    failed = (JobRun.objects.filter(status='failed', started_at__gte=timezone.now() - timedelta(hours=24))
              .values_list('job', flat=True))
    failed = sorted(set(failed))
    out.append(_check('job_failures', 'No job failures in the last 24 hours', 'warn' if failed else 'ok',
                      ('Failed: ' + ', '.join(failed)) if failed else 'No failures recorded.',
                      'Open the job history below for the error message.'))
    return out


def check_backups():
    from apps.core.backups import list_backups, verify_backup
    if connection.vendor != 'sqlite':
        return [_check('backups', 'Database backups', 'info', 'Not SQLite: use your database host\'s managed backups.')]
    backups = list_backups()
    if not backups:
        return [_check('backups', 'Recent verified backup', 'fail', 'No backups found.',
                       'Run python manage.py backup_db, and let the daily backup job run.')]
    newest = verify_backup(backups[-1])
    if not newest['ok']:
        return [_check('backups', 'Recent verified backup', 'fail', f"Newest backup failed verification: {newest.get('error') or newest.get('integrity')}",
                       'Create a new backup and run python manage.py restore_drill.')]
    age = newest['age_hours']
    status = 'ok' if age <= 30 else 'warn' if age <= 72 else 'fail'
    return [_check('backups', 'Recent verified backup', status,
                   f"{len(backups)} backup(s); newest is {age} h old and passes integrity checks.",
                   'The daily backup job is not running; check the scheduler.'),
            _check('backup_location', 'Backups stored outside the app image', 'info',
                   'Backups are written next to the database volume. Also copy them off the server periodically.')]


def check_integrations():
    from apps.growth.integrations import gbp_app_configured
    from apps.growth.visibility import pagespeed_enabled
    from apps.ai_service.engine import AIEngine
    out = []
    try:
        ai = AIEngine().available
    except Exception:
        ai = False
    out.append(_check('ai', 'AI assistant provider', 'ok' if ai else 'warn',
                      'An AI provider is configured.' if ai else 'No AI provider: the concierge uses rules only and AI drafts are off.',
                      'Set AI_PROVIDER and its API key.'))
    out.append(_check('pagespeed', 'Lighthouse scores in website checks', 'ok' if pagespeed_enabled() else 'info',
                      'PageSpeed is enabled.' if pagespeed_enabled() else 'Website checks run without Lighthouse scores.',
                      'Optional: add a free PAGESPEED_API_KEY.'))
    out.append(_check('google_business', 'Google Business Profile app', 'ok' if gbp_app_configured() else 'info',
                      'OAuth client configured.' if gbp_app_configured() else 'Waiting for Google API approval / OAuth client.',
                      'After Google approves API access, set GOOGLE_BUSINESS_CLIENT_ID / _SECRET.'))
    return out


def practice_readiness():
    """Per-practice setup gaps the agency should chase."""
    from apps.conversations.models import Conversation
    from apps.practices.models import KnowledgeEntry, Practice
    from apps.conversations.state_machine import office_open_at
    rows = []
    since = timezone.now() - timedelta(days=30)
    for p in Practice.objects.filter(active=True).order_by('name')[:200]:
        gaps = []
        if office_open_at(p) is None:
            gaps.append('office hours')
        if KnowledgeEntry.objects.filter(practice=p, is_active=True).count() < 3:
            gaps.append('patient answers')
        if not Conversation.objects.filter(practice=p, started_at__gte=since).exists():
            gaps.append('no website chats in 30 days')
        if not p.website:
            gaps.append('website address')
        rows.append({'id': str(p.id), 'name': p.name, 'gaps': gaps, 'ready': not gaps})
    return rows


def run_all() -> dict:
    sections = [
        ('Platform', check_database() + check_security()),
        ('Messaging', check_messaging()),
        ('Scheduler & backups', check_scheduler() + check_backups()),
        ('Integrations', check_integrations()),
    ]
    flat = [c for _, items in sections for c in items]
    counts = {s: sum(1 for c in flat if c['status'] == s) for s in ('fail', 'warn', 'ok', 'info')}
    return {
        'generated_at': timezone.now().isoformat(),
        'ready': counts['fail'] == 0,
        'counts': counts,
        'sections': [{'title': t, 'checks': items} for t, items in sections],
        'practices': practice_readiness(),
    }
