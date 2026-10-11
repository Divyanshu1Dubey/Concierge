"""
Text messaging through Twilio's REST API (no SDK needed), with a console backend for local testing.

Configuration (first match wins):
  1. The practice's own Twilio integration (Integrations page: account SID, auth token, sending number).
  2. Platform-wide TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER environment variables.
  3. SMS_BACKEND=console (development only): messages are logged and recorded, never delivered.

Every send checks the patient's SMS opt-out (STOP) first. US delivery from a 10-digit number also needs
A2P 10DLC brand/campaign registration in the Twilio console; that is an account step, not code.
"""
import base64
import hashlib
import hmac
import json
import logging

import requests
from django.conf import settings

from .consent import is_opted_out, normalize_phone, set_opt_out
from .models import Integration, SmsMessage

logger = logging.getLogger(__name__)

STOP_WORDS = {'stop', 'stopall', 'unsubscribe', 'cancel', 'end', 'quit', 'revoke', 'optout'}
START_WORDS = {'start', 'unstop', 'yes', 'subscribe'}
TWILIO_TIMEOUT = 10


class SmsError(Exception):
    pass


def _practice_twilio(practice):
    integ = Integration.objects.filter(practice=practice, kind='twilio').first()
    if not integ or not integ.secret:
        return None
    from apps.core.security import decrypt_secret
    try:
        secret = json.loads(decrypt_secret(integ.secret) or '{}')
    except ValueError:
        return None
    sid, token = secret.get('account_sid', ''), secret.get('auth_token', '')
    from_number = (integ.config or {}).get('from_number', '')
    if sid and token and from_number:
        return {'account_sid': sid, 'auth_token': token, 'from_number': from_number, 'source': 'practice'}
    return None


def provider_config(practice):
    # An explicit test mode always wins: credentials present in the environment (or saved by a practice)
    # must never turn a test/staging server into one that texts real phones.
    if getattr(settings, 'SMS_BACKEND', '') == 'console':
        return {'source': 'console', 'from_number': '+15550000000'}
    cfg = _practice_twilio(practice) if practice else None
    if cfg:
        return cfg
    sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    from_number = getattr(settings, 'TWILIO_FROM_NUMBER', '')
    if sid and token and from_number:
        return {'account_sid': sid, 'auth_token': token, 'from_number': from_number, 'source': 'platform'}
    return None


def sms_status(practice) -> dict:
    cfg = provider_config(practice)
    if not cfg:
        return {'configured': False, 'mode': 'off',
                'detail': 'Text messaging is not set up. Connect a Twilio account to enable it.'}
    if cfg['source'] == 'console':
        return {'configured': True, 'mode': 'console',
                'detail': 'Test mode: messages are recorded but not delivered (SMS_BACKEND=console).'}
    return {'configured': True, 'mode': 'live', 'from_number': cfg['from_number'],
            'detail': f"Sending from {cfg['from_number']} via Twilio ({'practice account' if cfg['source'] == 'practice' else 'platform account'})."}


def send_sms(practice, to_number: str, body: str, user=None, appointment=None, outreach: bool = False) -> SmsMessage:
    """Send one staff-approved text. Raises SmsError with a plain-language reason."""
    to = normalize_phone(to_number)
    body = (body or '').strip()
    if not to:
        raise SmsError('That phone number does not look valid. Use a 10-digit US number or include the country code.')
    if not body:
        raise SmsError('Write a message before sending.')
    if len(body) > 1000:
        raise SmsError('Keep text messages under 1,000 characters.')
    if is_opted_out(practice, 'sms', to):
        raise SmsError('This patient replied STOP and has opted out of text messages.')
    cfg = provider_config(practice)
    if not cfg:
        raise SmsError('Text messaging is not set up for this practice yet.')
    if outreach and 'reply stop' not in body.lower():
        body = body + '\nReply STOP to opt out.'

    msg = SmsMessage.objects.create(practice=practice, appointment=appointment, direction='out', to_number=to,
                                    from_number=cfg['from_number'], body=body, status='queued',
                                    provider=cfg['source'], sent_by=user)
    if cfg['source'] == 'console':
        logger.info("SMS (console backend) to %s: %s", to[-4:], body[:60])
        msg.status = 'sent'
        msg.provider_id = f'console-{msg.id.hex[:12]}'
        msg.save(update_fields=['status', 'provider_id'])
        return msg

    url = f"https://api.twilio.com/2010-04-01/Accounts/{cfg['account_sid']}/Messages.json"
    data = {'To': to, 'From': cfg['from_number'], 'Body': body}
    callback = _status_callback_url()
    if callback:
        data['StatusCallback'] = callback
    try:
        resp = requests.post(url, data=data, auth=(cfg['account_sid'], cfg['auth_token']), timeout=TWILIO_TIMEOUT)
    except requests.RequestException as exc:
        msg.status, msg.error = 'failed', 'Could not reach the text message provider. Try again shortly.'
        msg.save(update_fields=['status', 'error'])
        logger.warning("Twilio request failed: %s", type(exc).__name__)
        raise SmsError(msg.error)
    if resp.status_code >= 400:
        try:
            info = resp.json()
        except ValueError:
            info = {}
        msg.status = 'failed'
        msg.error = _twilio_error(info.get('code'), info.get('message', ''))
        msg.save(update_fields=['status', 'error'])
        raise SmsError(msg.error)
    info = resp.json()
    msg.status = 'sent'
    msg.provider_id = str(info.get('sid', ''))[:64]
    msg.save(update_fields=['status', 'provider_id'])
    return msg


def _twilio_error(code, message: str) -> str:
    known = {
        21211: 'The phone number is not valid.',
        21610: 'This number has replied STOP to your texts and cannot be messaged.',
        21408: 'Texting to this country is not enabled on the Twilio account.',
        21606: 'The sending number cannot send text messages.',
        30007: 'The carrier filtered this message. Check your A2P 10DLC registration.',
        20003: 'Twilio rejected the account credentials. Check the account SID and auth token.',
    }
    return known.get(code) or f"The text could not be sent ({(message or 'provider error')[:120]})."


def _status_callback_url() -> str:
    base = (getattr(settings, 'APP_PUBLIC_URL', '') or '').rstrip('/')
    return f"{base}/api/v1/growth/sms/status/" if base.startswith('https://') else ''


def valid_twilio_signature(auth_token: str, url: str, params: dict, signature: str) -> bool:
    """Twilio request validation: HMAC-SHA1 over the full URL plus sorted POST params, base64-encoded."""
    if not (auth_token and signature):
        return False
    payload = url + ''.join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode('utf-8'), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def signing_token(practice) -> str:
    """The Twilio auth token webhooks for this practice are signed with (practice account, else platform)."""
    cfg = _practice_twilio(practice) if practice else None
    return (cfg or {}).get('auth_token') or getattr(settings, 'TWILIO_AUTH_TOKEN', '')


def find_practice_for_number(to_number: str):
    """Which practice owns the number a patient texted (practice integrations first, then last outbound)."""
    from apps.practices.models import Practice
    to = normalize_phone(to_number)
    for integ in Integration.objects.filter(kind='twilio').select_related('practice'):
        if normalize_phone((integ.config or {}).get('from_number', '')) == to:
            return integ.practice, _practice_twilio(integ.practice)
    platform_from = normalize_phone(getattr(settings, 'TWILIO_FROM_NUMBER', ''))
    if platform_from and platform_from == to:
        return None, {'auth_token': getattr(settings, 'TWILIO_AUTH_TOKEN', '')}
    return None, None


def handle_inbound(params: dict, practice_hint=None) -> dict:
    """Record an inbound text and apply STOP/START. Returns what happened (for tests and logs)."""
    from apps.appointments.models import Appointment
    from_number = normalize_phone(params.get('From', ''))
    to_number = normalize_phone(params.get('To', ''))
    body = (params.get('Body') or '').strip()[:1600]
    sid = str(params.get('MessageSid', ''))[:64]
    if sid and SmsMessage.objects.filter(direction='in', provider_id=sid).exists():
        # Twilio retries webhooks; a repeated (or replayed) delivery must not act twice.
        return {'stored': False, 'reason': 'duplicate'}
    practice = practice_hint
    if practice is None and from_number:
        # Shared platform number: attribute the reply to the practice that last texted this patient.
        last = SmsMessage.objects.filter(direction='out', to_number=from_number).order_by('-created_at').first()
        practice = last.practice if last else None
    if practice is None or not from_number:
        return {'stored': False, 'reason': 'unknown practice'}
    appt = (Appointment.objects.filter(practice=practice, patient_phone__icontains=from_number[-10:])
            .order_by('-created_at').first())
    SmsMessage.objects.create(practice=practice, appointment=appt, direction='in', to_number=to_number,
                              from_number=from_number, body=body, status='received',
                              provider='twilio', provider_id=sid)
    word = body.lower().strip(' .!')
    action = ''
    if word in STOP_WORDS:
        set_opt_out(practice, 'sms', from_number, True, source='sms_stop')
        action = 'opted_out'
    elif word in START_WORDS:
        set_opt_out(practice, 'sms', from_number, False, source='sms_start')
        action = 'opted_in'
    elif appt:
        _notify_text_reply(appt)
    return {'stored': True, 'action': action, 'practice_id': practice.id}


def _notify_text_reply(appt):
    from django.core.mail import send_mail
    from .followups import dashboard_link, staff_recipients
    ps = getattr(appt.practice, 'settings', None)
    if not getattr(settings, 'EMAIL_CONFIGURED', False) or (ps is not None and not ps.notify_on_patient_reply):
        return
    recipients = staff_recipients(appt.practice)[:1]
    if not recipients:
        return
    try:
        send_mail(f"Patient replied by text ({appt.confirmation_code})",
                  "A patient replied to your text message.\n\nRead it in the dashboard: "
                  + dashboard_link(f"/dashboard/requests/{appt.id}") + "\n",
                  settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    except Exception as exc:
        logger.warning("Text reply notification failed (practice=%s): %s", appt.practice_id, type(exc).__name__)
