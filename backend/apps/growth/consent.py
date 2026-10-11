"""Opt-out handling shared by every outreach channel (email links, SMS STOP, staff changes)."""
import re

from django.core import signing
from django.utils import timezone

UNSUBSCRIBE_SALT = 'growth.unsubscribe'


def normalize_phone(value: str, default_country: str = '1') -> str:
    """Best-effort E.164 for North American numbers; other numbers must already include '+'."""
    raw = (value or '').strip()
    digits = re.sub(r'\D', '', raw)
    if raw.startswith('+') and 8 <= len(digits) <= 15:
        return '+' + digits
    if len(digits) == 10:
        return f'+{default_country}{digits}'
    if len(digits) == 11 and digits.startswith('1'):
        return '+' + digits
    return ''


def normalize_address(channel: str, address: str) -> str:
    if channel == 'sms':
        return normalize_phone(address)
    return (address or '').strip().lower()


def is_opted_out(practice, channel: str, address: str) -> bool:
    from .models import ContactPreference
    addr = normalize_address(channel, address)
    if not addr:
        return False
    return ContactPreference.objects.filter(practice=practice, channel=channel, address=addr, opted_out=True).exists()


def set_opt_out(practice, channel: str, address: str, opted_out: bool = True, source: str = 'staff'):
    from .models import ContactPreference
    addr = normalize_address(channel, address)
    if not addr:
        return None
    pref, _ = ContactPreference.objects.get_or_create(practice=practice, channel=channel, address=addr)
    pref.opted_out = opted_out
    pref.opted_out_at = timezone.now() if opted_out else None
    pref.source = source[:40]
    pref.save()
    return pref


def unsubscribe_token(practice, email: str) -> str:
    return signing.dumps({'p': str(practice.id), 'e': (email or '').strip().lower()}, salt=UNSUBSCRIBE_SALT, compress=True)


def read_unsubscribe_token(token: str):
    """Return (practice_id, email) or None. Links do not expire: an opt-out must always work."""
    try:
        data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
    except signing.BadSignature:
        return None
    if not isinstance(data, dict) or 'p' not in data or 'e' not in data:
        return None
    return data['p'], data['e']


def unsubscribe_link(practice, email: str) -> str:
    return f"{api_base()}/api/v1/growth/unsubscribe/{unsubscribe_token(practice, email)}/"


def api_base() -> str:
    from django.conf import settings
    return (getattr(settings, 'APP_PUBLIC_URL', '') or getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
