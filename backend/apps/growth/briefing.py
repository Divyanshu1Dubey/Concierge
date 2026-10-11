"""
The weekly practice briefing: a short email to the doctor / practice admins with last week's numbers,
what is waiting, and up to three recommended actions. Staff-only; patients are referred to by first name.
"""
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from . import analytics
from .followups import dashboard_link
from .models import BriefingLog, FollowUpTask, GrowthSettings, VisibilityReport

logger = logging.getLogger(__name__)
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _tz(practice):
    try:
        return ZoneInfo(practice.timezone or 'America/New_York')
    except Exception:
        return ZoneInfo('America/New_York')


def recipients(practice, gs=None) -> list:
    from apps.core.permissions import PRACTICE_ADMIN_ROLES
    from apps.users.models import User
    gs = gs or GrowthSettings.for_practice(practice)
    chosen = [e for e in (gs.briefing_recipients or []) if isinstance(e, str) and '@' in e]
    if chosen:
        return chosen[:5]
    admins = list(User.objects.filter(practice=practice, is_active=True, role__in=PRACTICE_ADMIN_ROLES)
                  .exclude(email='').values_list('email', flat=True)[:5])
    return admins or ([practice.email] if practice.email else [])


def build(practice, now=None) -> dict:
    """Numbers for the 7 days before ``now`` plus recommendations. Pure read; safe to call for previews."""
    from apps.emails.models import Email
    from apps.practices.models import KnowledgeEntry, UnansweredQuestion

    now = now or timezone.now()
    start = now - timedelta(days=7)
    f = analytics.funnel(practice, start, now)
    prev = analytics.funnel(practice, start - timedelta(days=7), start)
    open_tasks = FollowUpTask.objects.filter(practice=practice, status=FollowUpTask.STATUS_OPEN)
    waiting = open_tasks.filter(kind=FollowUpTask.KIND_WAITING_REPLY).count()
    unanswered = UnansweredQuestion.objects.filter(practice=practice, status='open').count()
    failed_emails = Email.objects.filter(thread__practice=practice, direction=Email.DIRECTION_OUTGOING,
                                         status=Email.STATUS_FAILED, created_at__gte=start).count()
    knowledge = KnowledgeEntry.objects.filter(practice=practice, is_active=True).count()
    last_check = VisibilityReport.objects.filter(practice=practice, status='ok').first()
    channels = [c for c in analytics.channels(practice, start, now) if c['requests'] or c['conversations']][:4]

    recs = []
    if open_tasks.exists():
        n = open_tasks.count()
        recs.append({'text': f"Work through {n} follow-up{'s' if n != 1 else ''}" +
                             (f", including {waiting} patient{'s' if waiting != 1 else ''} still waiting for a first reply" if waiting else '') + '.',
                     'link': dashboard_link('/dashboard/follow-ups')})
    if failed_emails:
        recs.append({'text': f"{failed_emails} email{'s' if failed_emails != 1 else ''} to patients failed to send. Check email delivery settings.",
                     'link': dashboard_link('/dashboard/email-settings')})
    if unanswered:
        recs.append({'text': f"Patients asked {unanswered} question{'s' if unanswered != 1 else ''} the concierge could not answer. Add answers so it can help next time.",
                     'link': dashboard_link('/dashboard/knowledge')})
    if f['median_first_reply_minutes'] is not None and f['median_first_reply_minutes'] > 240:
        hrs = round(f['median_first_reply_minutes'] / 60)
        recs.append({'text': f"Typical first reply took about {hrs} hours. Faster replies usually mean more confirmed visits; try the drafted replies in Follow-ups.",
                     'link': dashboard_link('/dashboard/follow-ups')})
    if f['after_hours_requests'] and f['requests'] and f['after_hours_requests'] / f['requests'] >= 0.3:
        recs.append({'text': f"{f['after_hours_requests']} of {f['requests']} requests arrived outside office hours. Check them first thing each morning.",
                     'link': dashboard_link('/dashboard/requests')})
    if knowledge < 3:
        recs.append({'text': 'Add your most common patient questions (insurance, parking, new patients) to Practice Knowledge.',
                     'link': dashboard_link('/dashboard/knowledge')})
    if last_check is None or last_check.created_at < now - timedelta(days=30):
        recs.append({'text': 'Run the website check to make sure your hours, phone and booking button are correct online.',
                     'link': dashboard_link('/dashboard/visibility')})
    if f['conversations'] == 0:
        recs.append({'text': 'No website chats this week. Confirm the chat is installed on your website.',
                     'link': dashboard_link('/dashboard/installation')})

    def delta(cur, old):
        if cur is None or old is None:
            return None
        return cur - old

    return {
        'practice': practice.name,
        'period_start': start.astimezone(_tz(practice)).date().isoformat(),
        'period_end': now.astimezone(_tz(practice)).date().isoformat(),
        'numbers': {
            'conversations': f['conversations'],
            'requests': f['requests'],
            'requests_change': delta(f['requests'], prev['requests']),
            'contacted': f['contacted'],
            'confirmed': f['confirmed'],
            'confirmed_change': delta(f['confirmed'], prev['confirmed']),
            'median_first_reply_minutes': f['median_first_reply_minutes'],
            'after_hours_requests': f['after_hours_requests'],
        },
        'waiting': {'open_follow_ups': open_tasks.count(), 'waiting_first_reply': waiting,
                    'unanswered_questions': unanswered, 'failed_emails': failed_emails},
        'channels': [{'label': c['label'], 'requests': c['requests'], 'conversations': c['conversations']} for c in channels],
        'recommendations': recs[:3],
        'dashboard_link': dashboard_link('/dashboard'),
    }


def render(payload: dict) -> tuple:
    html = render_to_string('growth/briefing_email.html', {'b': payload})
    n = payload['numbers']
    lines = [
        f"{payload['practice']} - week of {payload['period_start']} to {payload['period_end']}", '',
        f"Website chats: {n['conversations']}",
        f"Appointment requests: {n['requests']}",
        f"Contacted: {n['contacted']}   Confirmed: {n['confirmed']}",
    ]
    if n['median_first_reply_minutes'] is not None:
        lines.append(f"Typical first reply: {n['median_first_reply_minutes']} minutes")
    if n['after_hours_requests'] is not None:
        lines.append(f"Requests outside office hours: {n['after_hours_requests']}")
    lines += ['', 'Waiting on your team:',
              f"  Follow-ups: {payload['waiting']['open_follow_ups']}",
              f"  Unanswered patient questions: {payload['waiting']['unanswered_questions']}"]
    if payload['recommendations']:
        lines += ['', 'This week:'] + [f"  - {r['text']} {r['link']}" for r in payload['recommendations']]
    lines += ['', f"Open the dashboard: {payload['dashboard_link']}"]
    return html, '\n'.join(lines)


def week_start_for(practice, now) -> 'datetime.date | None':
    """The local date of this week's briefing slot if it has arrived, else None."""
    gs = GrowthSettings.for_practice(practice)
    local = now.astimezone(_tz(practice))
    if local.weekday() != gs.briefing_weekday or local.hour < gs.briefing_hour:
        return None
    return local.date()


def send_briefing(practice, now=None, force_week=None) -> dict:
    """Send this week's briefing once. Returns {'status': sent|skipped|failed, ...}."""
    now = now or timezone.now()
    gs = GrowthSettings.for_practice(practice)
    if not gs.briefing_enabled and force_week is None:
        return {'status': 'skipped', 'reason': 'disabled'}
    week = force_week or week_start_for(practice, now)
    if week is None:
        return {'status': 'skipped', 'reason': 'not due'}
    to = recipients(practice, gs)
    if not to:
        return {'status': 'skipped', 'reason': 'no recipients'}
    log = BriefingLog.objects.filter(practice=practice, week_start=week).first()
    if log and log.status in ('sent', 'sending'):
        return {'status': 'skipped', 'reason': 'already sent'}
    if log is None:
        try:
            with transaction.atomic():
                log = BriefingLog.objects.create(practice=practice, week_start=week, status='sending', recipients=to)
        except IntegrityError:
            return {'status': 'skipped', 'reason': 'already sent'}
    else:
        log.status, log.recipients = 'sending', to
        log.save(update_fields=['status', 'recipients'])

    payload = build(practice, now)
    html, text = render(payload)
    subject = f"Your week at {practice.name}: {payload['numbers']['requests']} request{'s' if payload['numbers']['requests'] != 1 else ''}, {payload['waiting']['open_follow_ups']} to follow up"
    try:
        msg = EmailMultiAlternatives(subject, text, getattr(settings, 'DEFAULT_FROM_EMAIL', None), to)
        msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)
    except Exception as exc:
        log.status, log.error = 'failed', f'Email could not be sent ({type(exc).__name__}).'
        log.payload = payload
        log.save(update_fields=['status', 'error', 'payload'])
        logger.warning("Briefing failed (practice=%s): %s", practice.id, type(exc).__name__)
        return {'status': 'failed'}
    log.status, log.payload, log.error = 'sent', payload, ''
    log.save(update_fields=['status', 'payload', 'error'])
    return {'status': 'sent', 'recipients': len(to)}
