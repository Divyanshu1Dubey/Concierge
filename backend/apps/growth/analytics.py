"""Conversion analytics computed only from records HeyJarvis stores. Missing data is reported as None."""
from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median

from django.utils import timezone

from .models import FollowUpTask, GrowthSettings, InquiryAttribution

CHANNEL_LABELS = dict(InquiryAttribution.CHANNEL_CHOICES)
CONTACTED = ('contacted', 'confirmed', 'completed', 'no_show')


def _minutes(a, b):
    return (b - a).total_seconds() / 60


def funnel(practice, start, end) -> dict:
    from apps.appointments.models import Appointment, AppointmentOffer
    from apps.conversations.models import Conversation
    from apps.conversations.state_machine import office_open_at

    convs = Conversation.objects.filter(practice=practice, started_at__gte=start, started_at__lt=end)
    conversations = convs.count()
    engaged = convs.filter(messages__sender='user').distinct().count()
    appts = list(Appointment.objects.filter(practice=practice, created_at__gte=start, created_at__lt=end)
                 .exclude(status='spam')
                 .values('id', 'status', 'created_at', 'response_sent_at', 'confirmed_at', 'conversation_id'))
    ids = [a['id'] for a in appts]
    offered_ids = set(AppointmentOffer.objects.filter(appointment_id__in=ids).values_list('appointment_id', flat=True))
    confirmed_ids = set(AppointmentOffer.objects.filter(appointment_id__in=ids, status=AppointmentOffer.STATUS_CONFIRMED)
                        .values_list('appointment_id', flat=True))
    requests = len(appts)
    contacted = sum(1 for a in appts if a['response_sent_at'] or a['status'] in CONTACTED)
    offered = len(offered_ids)
    confirmed = sum(1 for a in appts if a['id'] in confirmed_ids or a['status'] in ('confirmed', 'completed'))
    completed = sum(1 for a in appts if a['status'] == 'completed')
    waits = [_minutes(a['created_at'], a['response_sent_at']) for a in appts if a['response_sent_at']]
    hours_known = office_open_at(practice) is not None
    after_hours = sum(1 for a in appts if office_open_at(practice, a['created_at']) is False) if hours_known else None

    def rate(n, d):
        return round(100 * n / d) if d else None

    return {
        'conversations': conversations,
        'engaged_conversations': engaged,
        'requests': requests,
        'contacted': contacted,
        'offered_time': offered,
        'confirmed': confirmed,
        'completed': completed,
        'request_rate': rate(requests, engaged),
        'contact_rate': rate(contacted, requests),
        'confirm_rate': rate(confirmed, requests),
        'median_first_reply_minutes': round(median(waits)) if waits else None,
        'replied_within_1h': rate(sum(1 for w in waits if w <= 60), len(waits)) if waits else None,
        'after_hours_requests': after_hours,
    }


def channels(practice, start, end) -> list:
    """Requests and confirmations per source channel (conversations without attribution count as unknown)."""
    from apps.appointments.models import Appointment
    rows = defaultdict(lambda: {'conversations': 0, 'requests': 0, 'confirmed': 0})
    for att in InquiryAttribution.objects.filter(practice=practice, created_at__gte=start, created_at__lt=end):
        rows[att.channel]['conversations'] += 1
    appts = (Appointment.objects.filter(practice=practice, created_at__gte=start, created_at__lt=end)
             .exclude(status='spam').select_related('conversation__attribution'))
    for a in appts:
        att = getattr(a.conversation, 'attribution', None) if a.conversation_id else None
        key = att.channel if att else ('direct' if a.conversation_id else 'untracked')
        rows[key]['requests'] += 1
        if a.status in ('confirmed', 'completed'):
            rows[key]['confirmed'] += 1
    out = []
    for key, v in rows.items():
        label = CHANNEL_LABELS.get(key) or ('Not tracked (before source tracking or manual entry)' if key == 'untracked' else key)
        out.append({'channel': key, 'label': label, **v})
    out.sort(key=lambda r: (-r['requests'], -r['conversations']))
    return out


def top_pages(practice, start, end, limit=5) -> list:
    counts = Counter(InquiryAttribution.objects.filter(practice=practice, created_at__gte=start, created_at__lt=end)
                     .values_list('landing_path', flat=True))
    return [{'path': p or '/', 'conversations': n} for p, n in counts.most_common(limit)]


def campaigns(practice, start, end, limit=8) -> list:
    counts = Counter(InquiryAttribution.objects.filter(practice=practice, created_at__gte=start, created_at__lt=end)
                     .exclude(utm_campaign='').values_list('utm_source', 'utm_campaign'))
    return [{'source': s or '-', 'campaign': c, 'conversations': n} for (s, c), n in counts.most_common(limit)]


def weekly_trend(practice, weeks=8, now=None) -> list:
    from apps.appointments.models import Appointment
    now = now or timezone.now()
    out = []
    for i in range(weeks - 1, -1, -1):
        end = now - timedelta(days=7 * i)
        start = end - timedelta(days=7)
        qs = Appointment.objects.filter(practice=practice, created_at__gte=start, created_at__lt=end).exclude(status='spam')
        out.append({
            'week_ending': end.date().isoformat(),
            'requests': qs.count(),
            'confirmed': qs.filter(status__in=('confirmed', 'completed')).count(),
        })
    return out


def follow_up_summary(practice, start, end) -> dict:
    tasks = FollowUpTask.objects.filter(practice=practice)
    return {
        'open': tasks.filter(status=FollowUpTask.STATUS_OPEN).count(),
        'sent_in_period': tasks.filter(status=FollowUpTask.STATUS_SENT, completed_at__gte=start, completed_at__lt=end).count(),
        'done_in_period': tasks.filter(status=FollowUpTask.STATUS_DONE, completed_at__gte=start, completed_at__lt=end).count(),
    }


def value_estimate(practice, completed: int):
    """Only when the practice entered an average visit value; always labelled as an estimate."""
    gs = GrowthSettings.for_practice(practice)
    if gs.average_visit_value is None:
        return None
    return {'completed_visits': completed, 'average_visit_value': float(gs.average_visit_value),
            'estimated_value': round(float(gs.average_visit_value) * completed, 2),
            'note': 'Estimate = completed visits recorded in HeyJarvis x the average visit value you entered.'}


def overview(practice, days=30, now=None) -> dict:
    now = now or timezone.now()
    start = now - timedelta(days=days)
    prev_start = start - timedelta(days=days)
    current = funnel(practice, start, now)
    previous = funnel(practice, prev_start, start)
    return {
        'period_days': days,
        'funnel': current,
        'previous': {k: previous[k] for k in ('conversations', 'requests', 'confirmed', 'median_first_reply_minutes')},
        'channels': channels(practice, start, now),
        'top_pages': top_pages(practice, start, now),
        'campaigns': campaigns(practice, start, now),
        'trend': weekly_trend(practice, now=now),
        'follow_ups': follow_up_summary(practice, start, now),
        'value_estimate': value_estimate(practice, current['completed']),
        'unavailable': [
            'Booked visits and revenue from your practice-management system (not connected).',
            'Phone calls (HeyJarvis only sees website chats and emails).',
        ],
    }
