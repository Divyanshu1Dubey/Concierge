"""Invite and password-reset emails using Django's signed, single-use reset tokens."""
import logging
import secrets

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


def _public_base(request) -> str:
    base = getattr(settings, 'FRONTEND_URL', '') or getattr(settings, 'APP_PUBLIC_URL', '')
    if not base and request is not None:
        base = request.build_absolute_uri('/')
    return (base or '').rstrip('/')


def set_password_link(user, request, invite: bool = False) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    suffix = '&invite=1' if invite else ''
    return f"{_public_base(request)}/reset-password?uid={uid}&token={token}{suffix}"


def send_set_password_email(user, request, invite: bool = False) -> bool:
    """Email a set-password (invite) or reset link. Returns True only when the email was sent."""
    link = set_password_link(user, request, invite=invite)
    practice = getattr(user, 'practice', None)
    practice_name = practice.name if practice else 'HeyJarvis Concierge'
    hours = int(getattr(settings, 'PASSWORD_RESET_TIMEOUT', 259200) // 3600)
    if invite:
        subject = f"You're invited to {practice_name} on HeyJarvis Concierge"
        body = (
            f"Hello {user.first_name or ''},\n\n"
            f"You have been given access to {practice_name} on HeyJarvis Concierge.\n\n"
            f"Set your password here (link valid for {hours} hours):\n{link}\n\n"
            f"Then sign in with this email address: {user.email}\n"
        )
    else:
        subject = 'Reset your HeyJarvis Concierge password'
        body = (
            f"Hello {user.first_name or ''},\n\n"
            f"We received a request to reset your password. Use this link (valid for {hours} hours):\n{link}\n\n"
            "If you did not request this, you can ignore this email; your password will not change.\n"
        )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        return True
    except Exception as exc:
        logger.warning("Account email to user %s failed: %s", user.pk, type(exc).__name__)
        return False


def provision_access(user, password: str, request) -> dict:
    """
    Give a newly created user a way in: the admin-chosen password, otherwise an invite
    email; if the invite cannot be sent, a one-time temporary password for the admin to share.
    """
    if password:
        return {'invite_sent': False}
    user.set_unusable_password()
    user.save(update_fields=['password'])
    if send_set_password_email(user, request, invite=True):
        return {'invite_sent': True}
    temporary = secrets.token_urlsafe(12)
    user.set_password(temporary)
    user.save(update_fields=['password'])
    return {'invite_sent': False, 'temporary_password': temporary}
