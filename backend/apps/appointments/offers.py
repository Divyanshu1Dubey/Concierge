"""
Appointment confirmation requests ("offers").

The front desk proposes a concrete date/time; the patient receives a practice-branded email
and answers on a Concierge page (never by merely opening a link, so email scanners that
prefetch links cannot confirm anything). Concierge records the answer and updates the
request; it does not book anything in an external scheduling system.
"""
import hashlib
import logging
import re
import secrets
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Appointment, AppointmentOffer

logger = logging.getLogger(__name__)

HEX_COLOR = re.compile(r'^#(?:[0-9a-fA-F]{3}){1,2}$')
CLOSED_STATUSES = {'cancelled', 'completed', 'no_show', 'spam'}
DEFAULT_COLOR = '#1f4d3a'


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def practice_tz(practice):
    try:
        return ZoneInfo(practice.timezone or 'UTC')
    except Exception:
        return ZoneInfo('UTC')


def branding(practice) -> dict:
    """Practice identity for emails/pages, using only what the practice configured."""
    ps = getattr(practice, 'settings', None)
    color = (getattr(ps, 'widget_primary_color', '') or '').strip()
    if not HEX_COLOR.match(color):
        color = DEFAULT_COLOR
    full = color if len(color) == 7 else '#' + ''.join(c * 2 for c in color[1:])
    r, g, b = (int(full[i:i + 2], 16) for i in (1, 3, 5))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    logo = (practice.logo_url or '').strip()
    parts = [practice.address, practice.city, ' '.join(p for p in [practice.state, practice.zip_code] if p)]
    address = ', '.join(p.strip() for p in parts if p and p.strip())
    provider = practice.email_providers.filter(is_active=True).first()
    contact_email = (provider.reply_to if provider and provider.reply_to else '') or practice.email or ''
    return {
        'name': practice.name,
        'initial': (practice.name or '?').strip()[:1].upper(),
        'logo_url': logo if logo.startswith('https://') or logo.startswith('http://') else '',
        'color': full,
        'button_text_color': '#111111' if luminance > 0.62 else '#ffffff',
        'phone': practice.phone or '',
        'email': contact_email,
        'address': address,
        'website': practice.website or '',
        'timezone': practice.timezone or '',
    }


def display_date(d) -> str:
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.year}"


def tz_label(practice, d) -> str:
    """Short local zone name for that date (e.g. EDT), falling back to the configured name."""
    try:
        label = datetime.combine(d, time(12, 0), tzinfo=practice_tz(practice)).strftime('%Z')
    except Exception:
        label = ''
    return label if label and not label.startswith(('+', '-')) else (practice.timezone or '')


def create_offer(appointment: Appointment, offered_date, offered_time: str, user):
    """Create a pending offer and return (offer, raw_token). The raw token is never stored."""
    token = secrets.token_urlsafe(32)
    tz = practice_tz(appointment.practice)
    expires = datetime.combine(offered_date + timedelta(days=1), time.min, tzinfo=tz)
    offer = AppointmentOffer.objects.create(
        appointment=appointment, practice=appointment.practice, offered_date=offered_date,
        offered_time=offered_time.strip()[:50], token_hash=hash_token(token), created_by=user,
        expires_at=expires,
    )
    return offer, token


def activate_offer(offer: AppointmentOffer) -> None:
    """After the email was sent: older offers for the request stop working."""
    (AppointmentOffer.objects.filter(appointment=offer.appointment)
     .exclude(pk=offer.pk)
     .exclude(status=AppointmentOffer.STATUS_SUPERSEDED)
     .update(status=AppointmentOffer.STATUS_SUPERSEDED))


def offer_link(request, token: str) -> str:
    from apps.users.account_emails import _public_base
    return f"{_public_base(request)}/appointment/{token}"


def render_offer_email(appointment: Appointment, offered_date, offered_time: str, staff_message: str, link: str) -> tuple:
    """Return (html, text_suffix) for the branded confirmation email."""
    brand = branding(appointment.practice)
    first_name = (appointment.patient_name or '').strip().split(' ')[0] if appointment.patient_name else ''
    context = {
        'brand': brand,
        'first_name': first_name,
        'message': staff_message.strip(),
        'date_display': display_date(offered_date),
        'time_display': offered_time,
        'tz_label': tz_label(appointment.practice, offered_date),
        'service': appointment.service_name or (appointment.service.name if appointment.service_id else ''),
        'link': link,
        'reference': appointment.confirmation_code,
    }
    html = render_to_string('appointments/email/appointment_offer.html', context)
    text_suffix = (
        "\n\n----\n"
        f"Appointment: {context['date_display']} at {offered_time}\n"
        f"Please confirm or request a different time here:\n{link}\n"
    )
    return html, text_suffix


def offer_state(offer: AppointmentOffer) -> str:
    """What the patient may do now: pending | confirmed | reschedule_requested | superseded | expired | closed."""
    appt = offer.appointment
    if not offer.practice.active or appt.status in CLOSED_STATUSES:
        return 'closed'
    if offer.status == AppointmentOffer.STATUS_SUPERSEDED:
        return 'superseded'
    if offer.status == AppointmentOffer.STATUS_PENDING and timezone.now() >= offer.expires_at:
        return 'expired'
    return offer.status


def public_payload(offer: AppointmentOffer) -> dict:
    appt = offer.appointment
    brand = branding(offer.practice)
    return {
        'state': offer_state(offer),
        'practice': {k: brand[k] for k in ('name', 'initial', 'logo_url', 'color', 'button_text_color', 'phone', 'email', 'address', 'website')},
        'patient_first_name': (appt.patient_name or '').strip().split(' ')[0],
        'date': offer.offered_date.isoformat(),
        'date_display': display_date(offer.offered_date),
        'time': offer.offered_time,
        'timezone': tz_label(offer.practice, offer.offered_date),
        'service': appt.service_name or '',
        'reference': appt.confirmation_code,
        'responded_at': offer.responded_at,
    }


def staff_payload(offer: AppointmentOffer) -> dict:
    return {
        'id': str(offer.id), 'status': offer.status, 'state': offer_state(offer),
        'offered_date': offer.offered_date.isoformat(), 'date_display': display_date(offer.offered_date),
        'offered_time': offer.offered_time, 'patient_note': offer.patient_note,
        'created_at': offer.created_at, 'responded_at': offer.responded_at, 'expires_at': offer.expires_at,
        'sent_by': (offer.created_by.get_full_name() or offer.created_by.email) if offer.created_by else '',
    }


class OfferError(Exception):
    def __init__(self, state, message):
        super().__init__(message)
        self.state, self.message = state, message


STATE_MESSAGES = {
    'superseded': 'This time has been replaced by a newer one. Please use the most recent email from the practice.',
    'expired': 'This appointment time has passed or the link has expired. Please contact the practice.',
    'closed': 'This request is no longer active. Please contact the practice directly.',
}


def respond(token: str, action: str, note: str = '') -> tuple:
    """
    Apply the patient's answer. Returns (offer, changed). Repeating the same answer is a
    no-op (changed=False); invalid transitions raise OfferError.
    """
    with transaction.atomic():
        offer = (AppointmentOffer.objects.select_for_update()
                 .select_related('appointment', 'practice').get(token_hash=hash_token(token)))
        state = offer_state(offer)
        appt = offer.appointment
        now = timezone.now()
        if action == 'confirm':
            if state == AppointmentOffer.STATUS_CONFIRMED:
                return offer, False
            if state != AppointmentOffer.STATUS_PENDING:
                raise OfferError(state, STATE_MESSAGES.get(state, 'You already asked for a different time. The practice will contact you.'))
            offer.status = AppointmentOffer.STATUS_CONFIRMED
            appt.status = Appointment.STATUS_CONFIRMED
            appt.confirmed_at = now
            note_text = f"Patient confirmed {display_date(offer.offered_date)} at {offer.offered_time} from the email."
        elif action == 'reschedule':
            if state == AppointmentOffer.STATUS_RESCHEDULE:
                return offer, False
            if state not in (AppointmentOffer.STATUS_PENDING, AppointmentOffer.STATUS_CONFIRMED):
                raise OfferError(state, STATE_MESSAGES.get(state, 'This link can no longer be used.'))
            offer.status = AppointmentOffer.STATUS_RESCHEDULE
            offer.patient_note = (note or '').strip()[:1000]
            appt.status = Appointment.STATUS_PENDING
            appt.confirmed_at = None
            note_text = (f"Patient asked for a different time than {display_date(offer.offered_date)} at {offer.offered_time}."
                         + (f' Their note: "{offer.patient_note}"' if offer.patient_note else ''))
        else:
            raise OfferError('invalid', 'Unknown action.')
        offer.responded_at = now
        offer.save(update_fields=['status', 'patient_note', 'responded_at'])
        notes = list(appt.internal_notes or [])
        notes.append({'author': 'Concierge', 'text': note_text, 'created_at': now.isoformat()})
        appt.internal_notes = notes
        appt.save(update_fields=['status', 'confirmed_at', 'internal_notes'])
        offer_id = offer.id
        transaction.on_commit(lambda: notify_practice_of_response(offer_id))
    return offer, True


def notify_practice_of_response(offer_id) -> None:
    """Email the front desk about the patient's answer (honours the 'patient replies' toggle)."""
    from django.core.mail import send_mail
    offer = AppointmentOffer.objects.select_related('appointment', 'practice').filter(id=offer_id).first()
    if not offer or not getattr(settings, 'EMAIL_CONFIGURED', False):
        return
    practice, appt = offer.practice, offer.appointment
    ps = getattr(practice, 'settings', None)
    if ps is not None and not ps.notify_on_patient_reply:
        return
    cfg = (ps.notification_emails if ps is not None else None) or {}
    recipient = ((cfg.get('appointment') or cfg.get('general')) if isinstance(cfg, dict) else None) or practice.email
    if not recipient:
        return
    base = (getattr(settings, 'FRONTEND_URL', '') or getattr(settings, 'APP_PUBLIC_URL', '')).rstrip('/')
    what = 'confirmed' if offer.status == AppointmentOffer.STATUS_CONFIRMED else 'asked for a different time'
    try:
        send_mail(
            f"Patient {what} ({appt.confirmation_code})",
            f"The patient {what} for {display_date(offer.offered_date)} at {offer.offered_time}.\n\n"
            f"Review it in the dashboard: {base}/dashboard/requests/{appt.id}\n",
            settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False,
        )
    except Exception as exc:
        logger.warning("Offer response notification failed (practice=%s): %s", practice.id, type(exc).__name__)