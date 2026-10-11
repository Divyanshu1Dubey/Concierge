"""
Scheduled jobs. A Railway cron service (or any scheduler) calls POST /api/v1/growth/cron/run/ with the
X-Cron-Secret header every 10-15 minutes; locally, `python manage.py run_scheduled_jobs` does the same.

Each job runs at most once per time window: the JobRun.run_key is unique, so overlapping or repeated
calls are skipped rather than doing the work twice. Per-practice failures are isolated and recorded.
"""
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import JobRun

logger = logging.getLogger(__name__)


def _window(now, minutes):
    floored = now.replace(second=0, microsecond=0, minute=(now.minute // minutes) * minutes) if minutes < 60 else \
        now.replace(second=0, microsecond=0, minute=0)
    if minutes >= 1440:
        floored = floored.replace(hour=0)
    return floored.strftime('%Y%m%d%H%M')


def _active_practices():
    from apps.practices.models import Practice
    return Practice.objects.filter(active=True).order_by('id')


def job_replies(now):
    from apps.emails.inbound import fetch_replies, inbound_mailbox_configured
    if not inbound_mailbox_configured():
        return {'configured': False}
    result = fetch_replies()
    result.pop('practice_ids', None)
    return result


def job_followups(now):
    from .followups import scan_practice
    out = {'practices': 0, 'created': 0, 'alerted': 0, 'errors': 0}
    for practice in _active_practices():
        try:
            r = scan_practice(practice, now)
            out['practices'] += 1
            out['created'] += sum(r[k]['created'] for k in ('waiting', 'replied', 'unconfirmed', 'reschedule'))
            out['alerted'] += r['alerted']
        except Exception as exc:
            out['errors'] += 1
            logger.exception("Follow-up scan failed for practice %s: %s", practice.id, type(exc).__name__)
    return out


def job_outreach(now):
    from .outreach import scan_outreach
    out = {'recall': 0, 'reactivation': 0, 'review': 0, 'errors': 0}
    for practice in _active_practices():
        try:
            r = scan_outreach(practice, now)
            for k in ('recall', 'reactivation', 'review'):
                out[k] += r[k]
        except Exception as exc:
            out['errors'] += 1
            logger.exception("Outreach scan failed for practice %s: %s", practice.id, type(exc).__name__)
    return out


def job_google_reviews(now):
    from .followups import scan_google_reviews
    from .models import Integration
    out = {'practices': 0, 'created': 0, 'errors': 0}
    ids = Integration.objects.filter(kind='google_business', status='connected', practice__active=True).values_list('practice_id', flat=True)
    for practice in _active_practices().filter(id__in=list(ids)):
        try:
            r = scan_google_reviews(practice, now)
        except Exception as exc:
            logger.exception("Review scan failed for practice %s: %s", practice.id, type(exc).__name__)
            out['errors'] += 1
            continue
        out['practices'] += 1
        out['created'] += r.get('created', 0)
        out['errors'] += 1 if r.get('error') else 0
    return out


def job_briefings(now):
    from .briefing import send_briefing
    out = {'sent': 0, 'failed': 0}
    for practice in _active_practices():
        try:
            r = send_briefing(practice, now)
        except Exception as exc:
            logger.exception("Briefing failed for practice %s: %s", practice.id, type(exc).__name__)
            r = {'status': 'failed'}
        if r['status'] in ('sent', 'failed'):
            out[r['status']] += 1
    return out


def job_visibility(now):
    """Monthly re-check of practice websites, a few per day, so fix lists stay current."""
    from .models import VisibilityReport
    from .visibility import run_check
    checked = 0
    for practice in _active_practices().exclude(website=''):
        last = VisibilityReport.objects.filter(practice=practice).first()
        if last and last.created_at > now - timedelta(days=30):
            continue
        try:
            run_check(practice, practice.website)
            checked += 1
        except Exception as exc:
            logger.warning("Scheduled website check failed for practice %s: %s", practice.id, type(exc).__name__)
        if checked >= 5:
            break
    return {'checked': checked}


def job_backup(now):
    db = settings.DATABASES['default']
    if 'sqlite3' not in db['ENGINE']:
        return {'skipped': 'not sqlite'}
    from django.core.management import call_command
    from apps.core.backups import backup_dir, list_backups, verify_backup
    target = str(backup_dir())
    call_command('backup_db', dir=target, keep=int(getattr(settings, 'BACKUP_KEEP', 7)))
    newest = list_backups(target)[-1]
    check = verify_backup(newest)
    if not check['ok']:
        raise RuntimeError(f"backup written but failed verification: {check.get('error') or check.get('integrity')}")
    return {'file': newest.name, 'verified': True, 'size': check['size'], 'counts': check['counts']}


def job_cleanup(now):
    deleted, _ = JobRun.objects.filter(started_at__lt=now - timedelta(days=30)).delete()
    return {'deleted_job_runs': deleted}


# name -> (function, window minutes)
JOBS = {
    'replies': (job_replies, 10),
    'followups': (job_followups, 15),
    'outreach': (job_outreach, 60),
    'google_reviews': (job_google_reviews, 60),
    'briefings': (job_briefings, 60),
    'visibility': (job_visibility, 1440),
    'backup': (job_backup, 1440),
    'cleanup': (job_cleanup, 1440),
}


def run_job(name, now=None, force=False) -> dict:
    func, minutes = JOBS[name]
    now = now or timezone.now()
    key = f"{name}:{_window(now, minutes)}" + (f":manual:{now.timestamp()}" if force else '')
    try:
        with transaction.atomic():
            run = JobRun.objects.create(job=name, run_key=key[:160], started_at=now)
    except IntegrityError:
        return {'job': name, 'status': 'skipped', 'reason': 'already ran in this window'}
    try:
        result = func(now) or {}
        run.status, run.result = 'ok', result
    except Exception as exc:
        logger.exception("Scheduled job %s failed", name)
        run.status, run.error = 'failed', f'{type(exc).__name__}: {str(exc)[:200]}'
        result = {}
    run.finished_at = timezone.now()
    run.save(update_fields=['status', 'result', 'error', 'finished_at'])
    return {'job': name, 'status': run.status, 'result': result, 'error': run.error}


def run_due_jobs(now=None, only=None, force=False) -> list:
    names = [n for n in JOBS if not only or n in only]
    return [run_job(n, now, force) for n in names]


def scheduler_status() -> dict:
    last = JobRun.objects.order_by('-started_at').first()
    per_job = {}
    for name in JOBS:
        r = JobRun.objects.filter(job=name).order_by('-started_at').first()
        per_job[name] = {'last_run': r.started_at.isoformat() if r else None, 'status': r.status if r else None,
                         'error': r.error if r else ''}
    healthy = bool(last and last.started_at > timezone.now() - timedelta(minutes=45))
    return {'healthy': healthy, 'last_run': last.started_at.isoformat() if last else None,
            'cron_secret_set': bool(getattr(settings, 'CRON_SECRET', '')), 'jobs': per_job}
