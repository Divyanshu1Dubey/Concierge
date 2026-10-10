"""Email service implementation for HeyJarvis Concierge.
Handles sending emails via HeyJarvis Managed Email, Custom SMTP, or Gmail,
with credential encryption and full message threading.
"""
import logging
from typing import Optional
from django.conf import settings
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives, send_mail
from .models import EmailThread, Email
from apps.practices.models import Practice, EmailProvider
from apps.core.security import decrypt_secret

logger = logging.getLogger(__name__)


def send_practice_email(
    practice: Practice,
    to_email: str,
    subject: str,
    body: str,
    body_html: Optional[str] = None,
    reply_to: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    appointment = None,
) -> dict:
    """Send an outbound email on behalf of a tenant practice."""
    if not practice:
        return {'success': False, 'error': 'No practice provided'}

    # 1. Resolve Provider
    provider = practice.email_providers.filter(is_active=True).first()
    from_name = (provider.from_name if provider and provider.from_name else practice.name) or "HeyJarvis Concierge"
    from_email = (provider.from_email if provider and provider.from_email else practice.email) or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@heyjarvis.ai')
    effective_reply_to = reply_to or (provider.reply_to if provider and provider.reply_to else practice.email)

    # 2. Find or create email thread
    patient_name = appointment.patient_name if appointment else ""
    thread, _ = EmailThread.objects.get_or_create(
        practice=practice,
        patient_email=to_email,
        subject=subject,
        defaults={
            'patient_name': patient_name,
            'metadata': {
                'practice_id': str(practice.id),
                'appointment_id': str(appointment.id) if appointment else None,
            }
        }
    )

    # 3. Create outbound Email record
    email_record = Email.objects.create(
        thread=thread,
        direction=Email.DIRECTION_OUTGOING,
        status=Email.STATUS_SENDING,
        from_email=from_email,
        to_email=to_email,
        subject=subject,
        body=body,
        body_html=body_html or "",
        provider=(provider.provider_type if provider else 'managed'),
        is_staff_reply=appointment is not None,
    )

    # 4. Attempt delivery
    sender_header = f"{from_name} <{from_email}>" if from_name else from_email
    try:
        if provider and provider.provider_type == 'smtp' and provider.smtp_host:
            # Custom SMTP
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = sender_header
            msg['To'] = to_email
            if effective_reply_to:
                msg['Reply-To'] = effective_reply_to
            if in_reply_to:
                msg['In-Reply-To'] = in_reply_to
                msg['References'] = in_reply_to

            msg.attach(MIMEText(body, 'plain'))
            if body_html:
                msg.attach(MIMEText(body_html, 'html'))

            pwd = provider.get_smtp_password()
            port = provider.smtp_port or 587
            if provider.smtp_use_ssl:
                server = smtplib.SMTP_SSL(provider.smtp_host, port, timeout=12)
            else:
                server = smtplib.SMTP(provider.smtp_host, port, timeout=12)
                if provider.smtp_use_tls:
                    server.starttls()

            if provider.smtp_username and pwd:
                server.login(provider.smtp_username, pwd)

            server.sendmail(from_email, [to_email], msg.as_string())
            server.quit()
        else:
            # Managed Email (Django backend - console in dev, SMTP/SES in prod)
            headers = {}
            if in_reply_to:
                headers['In-Reply-To'] = in_reply_to
                headers['References'] = in_reply_to

            msg = EmailMultiAlternatives(
                subject=subject,
                body=body,
                from_email=sender_header,
                to=[to_email],
                reply_to=[effective_reply_to] if effective_reply_to else None,
                headers=headers,
            )
            msg.send(fail_silently=False)

        # 5. Success update
        email_record.status = Email.STATUS_SENT
        email_record.sent_at = timezone.now()
        import uuid as _uuid
        email_record.provider_message_id = f"<{_uuid.uuid4().hex}@{practice.slug}.heyjarvis.ai>"
        email_record.save(update_fields=['status', 'sent_at', 'provider_message_id'])

        thread.last_message_at = timezone.now()
        thread.save(update_fields=['last_message_at'])

        is_console = 'console' in str(getattr(settings, 'EMAIL_BACKEND', '')).lower()
        mode_used = 'smtp' if (provider and provider.provider_type == 'smtp') else ('console' if is_console else 'smtp')
        warning_msg = 'Development Mode (Console Backend): Email logged to server console. To deliver live emails to patient inboxes, add SMTP credentials in Settings > Email Delivery or .env.' if is_console and not (provider and provider.provider_type == 'smtp') else None

        return {
            'success': True,
            'message_id': email_record.provider_message_id,
            'status': 'sent',
            'provider': email_record.provider,
            'mode': mode_used,
            'warning': warning_msg,
        }

    except Exception as e:
        # Log the failure class only: messages from SMTP servers can echo addresses/credentials.
        logger.error("Failed to send practice email (practice=%s): %s", practice.id, type(e).__name__)
        email_record.status = Email.STATUS_FAILED
        email_record.save(update_fields=['status'])
        return {
            'success': False,
            'status': 'failed',
            'error': 'Email delivery failed. Check the email provider settings and try again.',
            'error_type': type(e).__name__,
            'provider': email_record.provider,
        }


def get_or_create_thread(patient_email: str, patient_name: str, subject: str, practice=None, appointment=None) -> EmailThread:
    """Get or create an email thread for a patient."""
    thread, _ = EmailThread.objects.get_or_create(
        practice=practice,
        patient_email=patient_email,
        subject=subject,
        defaults={
            'patient_name': patient_name,
            'metadata': {
                'practice_id': str(practice.id) if practice else None,
                'appointment_id': str(appointment.id) if appointment else None,
            }
        }
    )
    return thread


def create_email_record(thread: EmailThread, direction: str, from_email: str, to_email: str, subject: str, body: str, body_html: str = '', cc: str = '', is_ai_draft: bool = False) -> Email:
    """Create an email record in the database."""
    return Email.objects.create(
        thread=thread,
        direction=direction,
        status=Email.STATUS_DRAFT if direction == Email.DIRECTION_OUTGOING else Email.STATUS_SENT,
        from_email=from_email,
        to_email=to_email,
        cc=cc,
        subject=subject,
        body=body,
        body_html=body_html,
        is_ai_draft=is_ai_draft,
    )


def send_appointment_email(email_record: Email) -> Optional[str]:
    """Send an existing email record."""
    practice = email_record.thread.practice if email_record.thread else None
    if not practice:
        raise Exception('Email thread is not linked to a practice')

    res = send_practice_email(
        practice=practice,
        to_email=email_record.to_email,
        subject=email_record.subject,
        body=email_record.body,
        body_html=email_record.body_html,
    )
    if not res.get('success'):
        raise Exception(res.get('error', 'Delivery failed'))
    return res.get('message_id')


NOTIFY_FLAG_BY_INTENT = {
    'emergency': 'notify_on_emergency',
    'new_patient': 'notify_on_appointment',
    'cleaning': 'notify_on_appointment',
    'appointment': 'notify_on_appointment',
    'question': 'notify_on_question',
    'reschedule': 'notify_on_reschedule',
    'cancel': 'notify_on_cancel',
    'handoff': 'notify_on_handoff',
}


def notify_practice_of_request(appointment) -> bool:
    """
    Email the practice's front desk about a new patient request, honouring the
    practice's notification toggles. Sends only minimal details plus a dashboard
    link; never raises (patient-facing flows must not fail on notification errors).
    """
    practice = getattr(appointment, 'practice', None)
    if not practice:
        return False
    try:
        ps = getattr(practice, 'settings', None)
        if ps is not None:
            if not ps.notify_on_new_request:
                return False
            flag = NOTIFY_FLAG_BY_INTENT.get(appointment.intent or '')
            if flag and not getattr(ps, flag, True):
                return False
        emails_cfg = (ps.notification_emails if ps is not None else None) or {}
        if not isinstance(emails_cfg, dict):
            emails_cfg = {}
        is_emergency = appointment.intent == 'emergency' or appointment.urgency == 'URGENT'
        recipient = (emails_cfg.get('emergency') if is_emergency else None) or emails_cfg.get('general') or practice.email
        if not recipient:
            return False

        base = (getattr(settings, 'FRONTEND_URL', '') or getattr(settings, 'APP_PUBLIC_URL', '')).rstrip('/')
        link = f"{base}/dashboard/requests/{appointment.id}" if base else f"/dashboard/requests/{appointment.id}"
        label = (appointment.intent or 'appointment').replace('_', ' ').title()
        subject = f"{'URGENT: ' if is_emergency else ''}New {label} request ({appointment.confirmation_code})"
        body = (
            f"A new patient request was received via the HeyJarvis concierge.\n\n"
            f"Type: {label}\n"
            f"Patient: {appointment.patient_name or 'Not provided'}\n"
            f"Preferred: {appointment.preferred_date or 'Flexible'} {appointment.preferred_time or ''}\n"
            f"Reference: {appointment.confirmation_code}\n\n"
            f"Review and respond in the dashboard: {link}\n"
        )
        send_mail(subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [recipient], fail_silently=False)
        return True
    except Exception as e:
        logger.warning("Practice notification failed (practice=%s): %s", practice.id, type(e).__name__)
        return False
