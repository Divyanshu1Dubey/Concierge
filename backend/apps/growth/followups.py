"""
The follow-up queue: finds patients who are waiting (no reply, unconfirmed visit time, asked for another
time) and turns them into tasks with a drafted message. Drafts are only sent when a staff member approves.

Scans are idempotent: each situation has a stable dedupe key, so running the scheduler twice never
creates duplicate tasks or duplicate alerts. Tasks close themselves when the situation is resolved.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import FollowUpTask, GrowthSettings

logger = logging.getLogger(__name__)

OPEN_STATES = (FollowUpTask.STATUS_OPEN, FollowUpTask.STATUS_SNOOZED)
CLOSED_APPOINTMENT_STATUSES = ('cancelled', 'completed', 'no_show', 'spam')


def first_name(name: str) -> str:
    name = (name or '').strip()
    return name.split(' ')[0] if name else ''


def dashboard_link(path: str) -> str:
    base = (getattr(settings, 'FRONTEND_URL', '') or getattr(settings, 'APP_PUBLIC_URL', '')).rstrip('/')
    return f"{base}{path}" if base else path


def staff_recipients(practice) -> list:
    """Front-desk addresses for operational alerts: routing emails first, then the practice email."""
    ps = getattr(practice, 'settings', None)
    cfg = (ps.notification_emails if ps is not None else None) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    found = []
    for addr in (cfg.get('appointment'), cfg.get('general'), practice.email):
        addr = (addr or '').strip()
        if addr and addr.lower() not in [a.lower() for a in found]:
            found.append(addr)
    return found[:3]


def known_keys(practice, prefix: str) -> set:
    """Dedupe keys that already exist for this practice (one query instead of one per candidate)."""
    return set(FollowUpTask.objects.filter(practice=practice, dedupe_key__startswith=prefix).values_list('dedupe_key', flat=True))


def ensure_task(practice, dedupe_key: str, known: set = None, **fields):
    """Create the task for this situation once. Returns (task, created).
    ``known`` (from known_keys) lets bulk scans skip the existence query for keys already handled."""
    if known is not None and dedupe_key in known:
        return None, False
    existing = FollowUpTask.objects.filter(practice=practice, dedupe_key=dedupe_key).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            task = FollowUpTask.objects.create(practice=practice, dedupe_key=dedupe_key, **fields)
        if known is not None:
            known.add(dedupe_key)
        return task, True
    except IntegrityError:  # a concurrent scan created it first
        return FollowUpTask.objects.get(practice=practice, dedupe_key=dedupe_key), False


def resolve_task(task, note: str):
    task.status = FollowUpTask.STATUS_DONE
    task.completed_at = timezone.now()
    task.result_note = note[:300]
    task.save(update_fields=['status', 'completed_at', 'result_note', 'updated_at'])


# ── Prioritisation ────────────────────────────────────────────────────────────────────────────

KIND_WEIGHT = {
    FollowUpTask.KIND_PATIENT_REPLIED: 40, FollowUpTask.KIND_RESCHEDULE: 35, FollowUpTask.KIND_WAITING_REPLY: 30,
    FollowUpTask.KIND_UNCONFIRMED: 20, FollowUpTask.KIND_MANUAL: 15, FollowUpTask.KIND_RECALL: 8,
    FollowUpTask.KIND_REACTIVATION: 5, FollowUpTask.KIND_REVIEW: 3, FollowUpTask.KIND_REVIEW_REPLY: 12,
}


def priority(task, now=None) -> dict:
    """Explainable score: who should the front desk contact first? Returns {'score', 'level', 'reasons'}."""
    now = now or timezone.now()
    score = KIND_WEIGHT.get(task.kind, 10)
    reasons = []
    appt = task.appointment if task.appointment_id else None
    if appt is not None:
        urgency = (appt.urgency or appt.priority or '').upper()
        if appt.intent == 'emergency' or urgency == 'URGENT':
            score += 50
            reasons.append('urgent request')
        elif urgency == 'HIGH':
            score += 20
            reasons.append('high priority')
        if appt.intent == 'new_patient':
            score += 10
            reasons.append('new patient')
    if task.kind not in FollowUpTask.OUTREACH_KINDS:
        hours = max(0.0, (now - (task.created_at or now)).total_seconds() / 3600)
        if hours >= 24:
            score += 20
            reasons.append(f'waiting {int(hours // 24)} day{"s" if hours >= 48 else ""}')
        elif hours >= 4:
            score += 10
    level = 'high' if score >= 60 else 'normal' if score >= 20 else 'low'
    return {'score': score, 'level': level, 'reasons': reasons}


# ── Drafts (deterministic templates; staff can edit or ask AI to improve) ─────────────────────

def _service_phrase(appt) -> str:
    svc = (appt.service_name or '').strip()
    if not svc or svc.lower() in ('appointment request', 'appointment'):
        return 'your appointment request'
    return f'your {svc.lower()} request'


def draft_waiting_reply(appt) -> tuple:
    practice = appt.practice
    name = first_name(appt.patient_name)
    pref = ' '.join(t for t in (appt.preferred_date, appt.preferred_time) if t).strip()
    subject = f"Your request with {practice.name}"
    body = (
        f"Hi{(' ' + name) if name else ''},\n\n"
        f"Thank you for reaching out to {practice.name} about {_service_phrase(appt)}. "
        + (f"You mentioned {pref} works for you. " if pref else '')
        + "We'd be happy to find a time that suits you. Could you reply with two or three days and times that work best?\n\n"
        + (f"If it's easier, you can also call us at {practice.phone}.\n\n" if practice.phone else '')
        + f"Warm regards,\n{practice.name}"
    )
    return subject, body


def draft_confirmation_nudge(offer) -> tuple:
    from apps.appointments.offers import display_date
    appt = offer.appointment
    practice = offer.practice
    name = first_name(appt.patient_name)
    subject = f"Reminder: please confirm your visit with {practice.name}"
    body = (
        f"Hi{(' ' + name) if name else ''},\n\n"
        f"We're holding {display_date(offer.offered_date)} at {offer.offered_time} for you. "
        "Please use the button below to confirm, or let us know if another time would be better.\n\n"
        f"Thank you,\n{practice.name}"
    )
    return subject, body


# ── Scans ─────────────────────────────────────────────────────────────────────────────────────

def scan_waiting_replies(practice, gs: GrowthSettings, now) -> dict:
    from apps.appointments.models import Appointment
    created = resolved = 0
    if gs.waiting_alerts_enabled:
        cutoff = now - timedelta(hours=max(1, gs.waiting_alert_hours))
        waiting = (Appointment.objects.filter(practice=practice, status='pending', response_sent_at__isnull=True,
                                              created_at__lt=cutoff)
                   .order_by('created_at')[:200])
        known = known_keys(practice, 'waiting:')
        for appt in waiting:
            if f"waiting:{appt.id}" in known:
                continue
            subject, body = draft_waiting_reply(appt)
            hours = int((now - appt.created_at).total_seconds() // 3600)
            _, was_created = ensure_task(
                practice, f"waiting:{appt.id}", known=known, kind=FollowUpTask.KIND_WAITING_REPLY, appointment=appt,
                patient_name=appt.patient_name, patient_email=appt.patient_email, patient_phone=appt.patient_phone,
                title=f"{appt.patient_name or 'A patient'} is waiting for a reply",
                reason=f"Request received {hours} hour{'s' if hours != 1 else ''} ago and nobody has replied yet.",
                channel='email' if appt.patient_email else 'phone',
                draft_subject=subject if appt.patient_email else '', draft_body=body if appt.patient_email else '',
                draft_source='template', due_at=now,
            )
            created += was_created
    # Close waiting tasks once the patient has been answered or the request was closed.
    for task in FollowUpTask.objects.filter(practice=practice, kind=FollowUpTask.KIND_WAITING_REPLY,
                                            status__in=OPEN_STATES).select_related('appointment'):
        appt = task.appointment
        if appt is None or appt.response_sent_at or appt.status != 'pending':
            resolve_task(task, 'Resolved: the patient was answered or the request was closed.')
            resolved += 1
    return {'created': created, 'resolved': resolved}


def _latest_replies_map(practice, appointment_ids) -> dict:
    """{appointment_id(str): (kind, id, when, preview)} for the newest inbound email/text, in two queries."""
    from apps.emails.models import Email
    from .models import SmsMessage
    ids = [str(i) for i in appointment_ids]
    out = {}
    if not ids:
        return out
    for e in (Email.objects.filter(thread__practice=practice, direction=Email.DIRECTION_INCOMING,
                                   thread__metadata__appointment_id__in=ids)
              .values('id', 'created_at', 'body', 'thread__metadata').order_by('created_at')):
        key = str((e['thread__metadata'] or {}).get('appointment_id'))
        out[key] = ('email', str(e['id']), e['created_at'], e['body'])
    for s in (SmsMessage.objects.filter(practice=practice, direction='in', appointment_id__in=appointment_ids)
              .values('id', 'created_at', 'body', 'appointment_id').order_by('created_at')):
        key = str(s['appointment_id'])
        if key not in out or s['created_at'] > out[key][2]:
            out[key] = ('sms', str(s['id']), s['created_at'], s['body'])
    return out


def scan_patient_replies(practice, gs: GrowthSettings, now) -> dict:
    """A patient answered us (email or text) and nobody has replied since."""
    from apps.appointments.models import Appointment
    created = resolved = 0
    if gs.waiting_alerts_enabled:
        cutoff = now - timedelta(hours=max(1, gs.waiting_alert_hours))
        candidates = list(Appointment.objects.filter(practice=practice, response_sent_at__isnull=False)
                          .exclude(status__in=CLOSED_APPOINTMENT_STATUSES + ('confirmed',)).order_by('-updated_at')[:300])
        replies = _latest_replies_map(practice, [a.id for a in candidates])
        known = known_keys(practice, 'replied:')
        for appt in candidates:
            latest = replies.get(str(appt.id))
            if not latest or latest[2] <= appt.response_sent_at or latest[2] > cutoff:
                continue
            kind, rid, when, preview = latest
            hours = int((now - when).total_seconds() // 3600)
            name = first_name(appt.patient_name)
            subject = f"Re: your request with {practice.name}"
            body = (f"Hi{(' ' + name) if name else ''},\n\nThank you for getting back to us. \n\n"
                    f"Warm regards,\n{practice.name}")
            _, was_created = ensure_task(
                practice, f"replied:{kind}:{rid}", known=known, kind=FollowUpTask.KIND_PATIENT_REPLIED, appointment=appt,
                patient_name=appt.patient_name, patient_email=appt.patient_email, patient_phone=appt.patient_phone,
                title=f"{appt.patient_name or 'A patient'} replied and is waiting",
                reason=f"Replied by {'text' if kind == 'sms' else 'email'} {hours} hour{'s' if hours != 1 else ''} ago: "
                       f"\"{(preview or '').strip()[:140]}\"",
                channel='sms' if kind == 'sms' and appt.patient_phone else ('email' if appt.patient_email else 'phone'),
                draft_subject=subject if appt.patient_email else '', draft_body=body, draft_source='template', due_at=now,
            )
            created += was_created
    open_tasks = list(FollowUpTask.objects.filter(practice=practice, kind=FollowUpTask.KIND_PATIENT_REPLIED,
                                                  status__in=OPEN_STATES).select_related('appointment'))
    open_replies = _latest_replies_map(practice, [t.appointment_id for t in open_tasks if t.appointment_id])
    for task in open_tasks:
        appt = task.appointment
        latest = open_replies.get(str(appt.id)) if appt else None
        answered = appt is None or appt.status in CLOSED_APPOINTMENT_STATUSES or (
            latest and appt.response_sent_at and appt.response_sent_at >= latest[2])
        if answered:
            resolve_task(task, 'Resolved: the patient was answered or the request was closed.')
            resolved += 1
    return {'created': created, 'resolved': resolved}


def scan_unconfirmed_offers(practice, gs: GrowthSettings, now) -> dict:
    from apps.appointments.models import AppointmentOffer
    created = resolved = 0
    if gs.confirmation_nudges_enabled:
        cutoff = now - timedelta(hours=max(1, gs.confirmation_nudge_hours))
        offers = (AppointmentOffer.objects.filter(practice=practice, status=AppointmentOffer.STATUS_PENDING,
                                                  created_at__lt=cutoff, expires_at__gt=now)
                  .exclude(appointment__status__in=CLOSED_APPOINTMENT_STATUSES)
                  .select_related('appointment')[:200])
        known = known_keys(practice, 'unconfirmed:')
        for offer in offers:
            if f"unconfirmed:{offer.id}" in known:
                continue
            appt = offer.appointment
            subject, body = draft_confirmation_nudge(offer)
            _, was_created = ensure_task(
                practice, f"unconfirmed:{offer.id}", known=known, kind=FollowUpTask.KIND_UNCONFIRMED, appointment=appt,
                patient_name=appt.patient_name, patient_email=appt.patient_email, patient_phone=appt.patient_phone,
                title=f"{appt.patient_name or 'A patient'} has not confirmed their visit",
                reason=f"Asked to confirm {offer.offered_date:%b %d} at {offer.offered_time}; no answer yet.",
                channel='email', draft_subject=subject, draft_body=body, draft_source='template', due_at=now,
            )
            created += was_created
    open_tasks = list(FollowUpTask.objects.filter(practice=practice, kind=FollowUpTask.KIND_UNCONFIRMED,
                                                  status__in=OPEN_STATES))
    offers_by_id = {str(o.id): o for o in AppointmentOffer.objects.filter(
        id__in=[t.dedupe_key.split(':', 1)[1] for t in open_tasks]).select_related('appointment')}
    for task in open_tasks:
        offer = offers_by_id.get(task.dedupe_key.split(':', 1)[1])
        if (offer is None or offer.status != AppointmentOffer.STATUS_PENDING or offer.expires_at <= now
                or offer.appointment.status in CLOSED_APPOINTMENT_STATUSES):
            resolve_task(task, 'Resolved: the patient answered, the time changed or the offer expired.')
            resolved += 1
    return {'created': created, 'resolved': resolved}


def scan_reschedule_requests(practice, now) -> dict:
    from apps.appointments.models import AppointmentOffer
    created = resolved = 0
    offers = (AppointmentOffer.objects.filter(practice=practice, status=AppointmentOffer.STATUS_RESCHEDULE)
              .exclude(appointment__status__in=CLOSED_APPOINTMENT_STATUSES).select_related('appointment')[:200])
    known = known_keys(practice, 'reschedule:')
    for offer in offers:
        if f"reschedule:{offer.id}" in known:
            continue
        appt = offer.appointment
        note = f' Their note: "{offer.patient_note[:120]}"' if offer.patient_note else ''
        _, was_created = ensure_task(
            practice, f"reschedule:{offer.id}", known=known, kind=FollowUpTask.KIND_RESCHEDULE, appointment=appt,
            patient_name=appt.patient_name, patient_email=appt.patient_email, patient_phone=appt.patient_phone,
            title=f"{appt.patient_name or 'A patient'} asked for a different time",
            reason=f"Could not make {offer.offered_date:%b %d} at {offer.offered_time}.{note}",
            channel='email', due_at=offer.responded_at or now,
        )
        created += was_created
    open_tasks = list(FollowUpTask.objects.filter(practice=practice, kind=FollowUpTask.KIND_RESCHEDULE,
                                                  status__in=OPEN_STATES))
    offers_by_id = {str(o.id): o for o in AppointmentOffer.objects.filter(
        id__in=[t.dedupe_key.split(':', 1)[1] for t in open_tasks]).select_related('appointment')}
    for task in open_tasks:
        offer = offers_by_id.get(task.dedupe_key.split(':', 1)[1])
        if offer is None or offer.status != AppointmentOffer.STATUS_RESCHEDULE or \
                offer.appointment.status in CLOSED_APPOINTMENT_STATUSES:
            resolve_task(task, 'Resolved: a new time was proposed or the request was closed.')
            resolved += 1
    return {'created': created, 'resolved': resolved}


def wake_snoozed(practice, now) -> int:
    return FollowUpTask.objects.filter(practice=practice, status=FollowUpTask.STATUS_SNOOZED,
                                       snoozed_until__lte=now).update(status=FollowUpTask.STATUS_OPEN, due_at=now)


def send_waiting_alerts(practice, now) -> int:
    """One digest email to the front desk listing newly overdue patients (each patient is alerted once)."""
    pending = list(FollowUpTask.objects.filter(
        practice=practice, status=FollowUpTask.STATUS_OPEN, alert_sent_at__isnull=True,
        kind__in=(FollowUpTask.KIND_WAITING_REPLY, FollowUpTask.KIND_PATIENT_REPLIED, FollowUpTask.KIND_RESCHEDULE,
                  FollowUpTask.KIND_UNCONFIRMED),
    ).order_by('created_at')[:25])
    if not pending:
        return 0
    recipients = staff_recipients(practice)
    if not recipients:
        return 0
    lines = []
    for t in pending:
        lines.append(f"- {first_name(t.patient_name) or 'Patient'}: {t.get_kind_display()} ({t.reason})")
    subject = f"{len(pending)} patient{'s' if len(pending) != 1 else ''} need{'s' if len(pending) == 1 else ''} a follow-up - {practice.name}"
    body = (
        "These patients are waiting on your team:\n\n" + '\n'.join(lines) +
        f"\n\nOpen the follow-up list (replies are drafted for you to review):\n{dashboard_link('/dashboard/follow-ups')}\n\n"
        "You can change when these alerts are sent in Growth settings."
    )
    try:
        send_mail(subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), recipients, fail_silently=False)
    except Exception as exc:
        logger.warning("Follow-up alert failed (practice=%s): %s", practice.id, type(exc).__name__)
        return 0
    FollowUpTask.objects.filter(id__in=[t.id for t in pending]).update(alert_sent_at=now)
    return len(pending)


def scan_practice(practice, now=None) -> dict:
    now = now or timezone.now()
    gs = GrowthSettings.for_practice(practice)
    result = {
        'woken': wake_snoozed(practice, now),
        'waiting': scan_waiting_replies(practice, gs, now),
        'replied': scan_patient_replies(practice, gs, now),
        'unconfirmed': scan_unconfirmed_offers(practice, gs, now),
        'reschedule': scan_reschedule_requests(practice, now),
    }
    result['alerted'] = send_waiting_alerts(practice, now) if gs.waiting_alerts_enabled else 0
    return result


# ── Approve & send ────────────────────────────────────────────────────────────────────────────

class SendError(Exception):
    pass


def _request_thread(practice, appt):
    from apps.emails.models import Email, EmailThread
    thread = (EmailThread.objects.filter(practice=practice, metadata__appointment_id=str(appt.id))
              .order_by('-last_message_at').first())
    last_reply = (Email.objects.filter(thread=thread, direction=Email.DIRECTION_INCOMING)
                  .exclude(provider_message_id='').order_by('-created_at').first()) if thread else None
    return thread, last_reply


def send_task_message(task: FollowUpTask, user, subject: str, body: str, channel: str = 'email') -> dict:
    """
    Send the staff-approved message for a task. Raises SendError with a plain-language reason.
    Outreach (recall, reactivation, reviews) always respects opt-outs and carries an unsubscribe link.
    """
    from .consent import is_opted_out, unsubscribe_link
    practice = task.practice
    body = (body or '').strip()
    subject = (subject or '').strip()[:200]
    if task.status not in OPEN_STATES:
        raise SendError('This follow-up is already closed.')
    if not body:
        raise SendError('Write a message before sending.')
    is_outreach = task.kind in FollowUpTask.OUTREACH_KINDS

    if task.kind == FollowUpTask.KIND_REVIEW_REPLY:
        from .integrations import IntegrationError, gbp_reply
        review_name = task.dedupe_key.split(':', 1)[1]
        try:
            gbp_reply(practice, review_name, body)
        except IntegrationError as exc:
            raise SendError(str(exc))
        _mark_sent(task, user, 'Reply published on Google.')
        return {'channel': 'google'}

    if channel == 'sms':
        from .sms import send_sms, SmsError
        if not task.patient_phone:
            raise SendError('This patient has no phone number on file.')
        try:
            msg = send_sms(practice, task.patient_phone, body, user=user, appointment=task.appointment,
                           outreach=is_outreach)
        except SmsError as exc:
            raise SendError(str(exc))
        _mark_sent(task, user, f'Text message sent to {task.patient_phone}.')
        return {'channel': 'sms', 'id': str(msg.id)}

    if channel != 'email':
        raise SendError('Choose email or text message.')
    to_email = (task.patient_email or '').strip()
    if not to_email:
        raise SendError('This patient has no email address on file.')
    if not subject:
        raise SendError('Add a subject line.')
    if is_outreach and is_opted_out(practice, 'email', to_email):
        raise SendError('This patient has opted out of outreach emails.')

    from apps.emails.services import send_practice_email
    appt = task.appointment
    thread, last_reply = _request_thread(practice, appt) if appt else (None, None)
    body_text, body_html, offer = body, None, None

    if task.kind == FollowUpTask.KIND_UNCONFIRMED and appt:
        # Re-issue the confirmation link for the same time (the old link is replaced once this sends).
        from apps.appointments.models import AppointmentOffer
        from apps.appointments.offers import create_offer, render_offer_email
        from apps.users.account_emails import _public_base
        old = AppointmentOffer.objects.filter(id=task.dedupe_key.split(':', 1)[1]).first()
        if old is None or old.status != AppointmentOffer.STATUS_PENDING:
            raise SendError('This visit time is no longer awaiting confirmation.')
        offer, token = create_offer(appt, old.offered_date, old.offered_time, user)
        link = f"{_public_base(None)}/appointment/{token}"
        body_html, suffix = render_offer_email(appt, old.offered_date, old.offered_time, body, link)
        body_text = body + suffix
    elif is_outreach:
        body_text = body + f"\n\n----\nTo stop receiving these emails from {practice.name}: {unsubscribe_link(practice, to_email)}"

    result = send_practice_email(
        practice=practice, to_email=to_email, subject=subject, body=body_text, body_html=body_html,
        appointment=appt, thread=thread, in_reply_to=last_reply.provider_message_id if last_reply else None,
    )
    if not result.get('success'):
        if offer is not None:
            offer.delete()
        raise SendError(result.get('error') or 'The email could not be sent.')

    if offer is not None:
        from apps.appointments.offers import activate_offer
        activate_offer(offer)
        # The new offer gets its own task only if it also goes unanswered.
    if appt and task.kind in (FollowUpTask.KIND_WAITING_REPLY, FollowUpTask.KIND_PATIENT_REPLIED):
        appt.status = 'contacted'
        appt.response_draft = body
        appt.response_sent_at = timezone.now()
        appt.save(update_fields=['status', 'response_draft', 'response_sent_at'])
    _mark_sent(task, user, f'Email sent to {to_email}.' + (f" ({result['warning']})" if result.get('warning') else ''))
    return {'channel': 'email', 'warning': result.get('warning', '')}


def _mark_sent(task, user, note):
    task.status = FollowUpTask.STATUS_SENT
    task.completed_by = user
    task.completed_at = timezone.now()
    task.result_note = note[:300]
    task.save(update_fields=['status', 'completed_by', 'completed_at', 'result_note', 'draft_subject',
                             'draft_body', 'updated_at'])


def scan_google_reviews(practice, now=None) -> dict:
    """Unanswered Google reviews become follow-ups with a drafted reply (published only when staff send it)."""
    from .integrations import IntegrationError, draft_review_reply, gbp_reviews
    from .models import Integration
    now = now or timezone.now()
    integ = Integration.objects.filter(practice=practice, kind='google_business', status='connected').first()
    if not integ or not (integ.config or {}).get('location'):
        return {'skipped': 'not connected'}
    try:
        data = gbp_reviews(practice)
    except IntegrationError as exc:
        return {'error': str(exc)[:200]}
    created = resolved = 0
    known = known_keys(practice, 'gbpreview:')
    unanswered = {r['name'] for r in data['reviews'] if not r.get('reply')}
    for r in data['reviews']:
        if r.get('reply') or not r.get('name'):
            continue
        key = f"gbpreview:{r['name']}"
        if key in known:
            continue
        stars = r.get('rating') or 0
        _, made = ensure_task(
            practice, key, known=known, kind=FollowUpTask.KIND_REVIEW_REPLY, channel='google',
            patient_name=(r.get('reviewer') or 'A Google user')[:200],
            title=f"Reply to a {stars}-star Google review" if stars else 'Reply to a Google review',
            reason=(f'"{(r.get("comment") or "").strip()[:180]}"' if r.get('comment') else 'Rating only, no comment.')
                   + ' Replies are public: do not confirm the person is a patient or mention treatment.',
            draft_body=draft_review_reply(practice, r), draft_source='template', due_at=now,
        )
        created += made
    for task in FollowUpTask.objects.filter(practice=practice, kind=FollowUpTask.KIND_REVIEW_REPLY, status__in=OPEN_STATES):
        name = task.dedupe_key.split(':', 1)[1]
        if name not in unanswered and any(r['name'] == name for r in data['reviews']):
            resolve_task(task, 'Resolved: the review already has a reply.')
            resolved += 1
    return {'created': created, 'resolved': resolved}
