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
    thread: Optional[EmailThread] = None,
) -> dict:
    """Send an outbound email on behalf of a tenant practice."""
    if not practice:
        return {'success': False, 'error': 'No practice provided'}

    # 1. Resolve Provider
    provider = practice.email_providers.filter(is_active=True).first()
    from_name = (provider.from_name if provider and provider.from_name else practice.name) or "HeyJarvis Concierge"
    from_email = (provider.from_email if provider and provider.from_email else practice.email) or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@heyjarvis.ai')
    effective_reply_to = reply_to or (provider.reply_to if provider and provider.reply_to else practice.email)
    uses_custom_smtp = bool(provider and provider.provider_type == 'smtp' and provider.smtp_host)
    if not uses_custom_smtp:
        # Platform ("managed") mail must be sent from the platform's own mailbox: mail servers reject or
        # spam-filter messages whose From address belongs to a different domain (SPF/DMARC). The practice
        # name is shown as the sender and patient replies still go to the practice (Reply-To).
        from email.utils import parseaddr
        platform_address = parseaddr(getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '')[1] or getattr(settings, 'EMAIL_HOST_USER', '')
        if platform_address:
            from_email = platform_address

    # 2. Find or create email thread (callers may pass the request's existing thread)
    patient_name = appointment.patient_name if appointment else ""
    if thread is None:
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

    if not body_html:
        try:
            from .branded import render_branded_message
            body_html = render_branded_message(practice, body)
        except Exception:
            logger.warning("Branded email rendering failed (practice=%s); sending plain text", practice.id)
            body_html = None

    # The Message-ID goes on the actual email so patient replies (In-Reply-To/References)
    # can be matched back to this thread.
    from email.utils import make_msgid
    message_id = make_msgid(domain=f"{practice.slug or 'practice'}.heyjarvis.ai")

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
            msg['Message-ID'] = message_id
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
            headers = {'Message-ID': message_id}
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
            if body_html:
                msg.attach_alternative(body_html, 'text/html')
            msg.send(fail_silently=False)

        # 5. Success update
        email_record.status = Email.STATUS_SENT
        email_record.sent_at = timezone.now()
        email_record.provider_message_id = message_id
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
        reason = describe_send_error(e)
        email_record.status = Email.STATUS_FAILED
        email_record.error_message = reason[:300]
        email_record.save(update_fields=['status', 'error_message'])
        return {
            'success': False,
            'status': 'failed',
            'error': reason,
            'error_type': type(e).__name__,
            'provider': email_record.provider,
        }


def describe_send_error(exc) -> str:
    """Plain-language reason a send failed, written for front-desk staff (no technical details)."""
    import smtplib
    import socket
    import ssl
    import urllib.error
    from .backends import EmailAPIError
    if isinstance(exc, EmailAPIError):
        if exc.status in (401, 403):
            return "The email service rejected its API key. A practice administrator or your agency should check the email service settings."
        if exc.status == 422:
            return "The email service refused the sender address. The sending domain must be verified with the email service."
        if exc.status == 429:
            return "The email service is limiting how fast emails are sent. Please try again in a minute."
        return "The email service could not send this email. Please try again in a few minutes."
    if isinstance(exc, urllib.error.URLError):
        return "Could not reach the email service. Please try again in a few minutes."
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "The email account rejected the login. A practice administrator should check the username and app password in Email settings."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "The mail server refused the sender address. Send from the address of the email account itself."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The patient's email address was rejected. Check it for typos and try again."
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return "The mail server closed the connection. A practice administrator should check the port and SSL/TLS setting in Email settings."
    if isinstance(exc, smtplib.SMTPDataError):
        return "The mail server refused this message. Try again later, or contact your email provider."
    if isinstance(exc, ssl.SSLError):
        return "A secure connection to the mail server failed. Port 465 needs SSL; port 587 needs TLS."
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "The mail server did not respond in time. Please try again in a few minutes."
    if isinstance(exc, (ConnectionRefusedError, socket.gaierror)):
        return "Could not connect to the mail server. Email may not be set up yet; a practice administrator can check Email settings."
    if isinstance(exc, smtplib.SMTPException):
        return "The mail server could not send this email. Please try again; if it keeps failing, a practice administrator can check Email settings."
    return "The email could not be sent. Please try again; if it keeps failing, a practice administrator can check Email settings."



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
        intent = appointment.intent or ''
        if is_emergency:
            route = 'emergency'
        elif intent == 'handoff':
            route = 'handoff'
        elif intent in ('new_patient', 'cleaning', 'appointment', 'reschedule', 'cancel'):
            route = 'appointment'
        else:
            route = 'general'
        recipient = emails_cfg.get(route) or emails_cfg.get('general') or practice.email
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


def queue_practice_notification(appointment) -> None:
    """
    Notify the practice after the current transaction commits, in a background thread
    when EMAIL_ASYNC is on, so slow SMTP never delays the patient's chat reply.
    """
    from django.db import transaction

    appointment_id = appointment.id

    def _send():
        from django.db import close_old_connections
        from apps.appointments.models import Appointment
        try:
            appt = Appointment.objects.select_related('practice').filter(id=appointment_id).first()
            if appt:
                notify_practice_of_request(appt)
        finally:
            close_old_connections()

    if getattr(settings, 'EMAIL_ASYNC', False):
        import threading

        transaction.on_commit(lambda: threading.Thread(target=_send, daemon=True, name='practice-notify').start())
    else:
        transaction.on_commit(lambda: notify_practice_of_request(appointment))
