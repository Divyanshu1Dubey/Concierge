"""Passwordless staff login: a 6-digit code emailed to the user.

Codes are stored hashed, expire after 10 minutes, allow 5 guesses, and work once.
They are sent from the HeyJarvis address (DEFAULT_SMTP_*), not the clinic mailbox,
so a clinic can log in before its Gmail is connected.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

from saas.config import get_settings
from saas.database import connect, insert, now_iso, row, utcnow

log = logging.getLogger(__name__)
TTL_MINUTES = 10
MAX_ATTEMPTS = 5


class LoginCodeError(Exception):
    pass


def _hash(code: str) -> str:
    return hmac.new(get_settings().jwt_secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def issue(user_id: int, email: str, clinic_name: str) -> None:
    code = f"{secrets.randbelow(10**6):06d}"
    with connect() as c:
        c.execute("UPDATE login_codes SET used_at = ? WHERE user_id = ? AND used_at IS NULL", (now_iso(), user_id))
        insert(c, "login_codes", user_id=user_id, code_hash=_hash(code), attempts=0, created_at=now_iso(),
               expires_at=(utcnow() + timedelta(minutes=TTL_MINUTES)).isoformat(timespec="seconds"))
    _send(email, code, clinic_name)


def verify(user_id: int, code: str) -> bool:
    code = "".join(ch for ch in code if ch.isdigit())
    with connect() as c:
        r = row(c, "SELECT * FROM login_codes WHERE user_id = ? AND used_at IS NULL ORDER BY id DESC LIMIT 1", user_id)
        if not r or r["expires_at"] < now_iso() or r["attempts"] >= MAX_ATTEMPTS:
            return False
        if not hmac.compare_digest(r["code_hash"], _hash(code)):
            c.execute("UPDATE login_codes SET attempts = attempts + 1 WHERE id = ?", (r["id"],))
            return False
        c.execute("UPDATE login_codes SET used_at = ? WHERE id = ?", (now_iso(), r["id"]))
    return True


def _send(to: str, code: str, clinic_name: str) -> None:
    send_system_email(to, f"Your HeyJarvis login code: {code}",
                      f"Your login code for the {clinic_name} front desk is:\n\n    {code}\n\n"
                      f"It expires in {TTL_MINUTES} minutes. If you didn't ask for it, ignore this email.",
                      dev_note=f"Login code for {to}: {code}")


def send_system_email(to: str, subject: str, body: str, dev_note: str | None = None) -> bool:
    """Email from the HeyJarvis address (DEFAULT_SMTP_*). In local dev without SMTP, logs instead of sending.
    Returns True if actually sent."""
    s = get_settings()
    if not (s.default_smtp_host and s.default_smtp_user and s.default_smtp_password):
        if s.is_production:
            raise LoginCodeError("Email login is not configured on production. Ensure DEFAULT_SMTP_USER and DEFAULT_SMTP_PASSWORD are set in Railway Variables.")
        log.warning("DEV ONLY - no SMTP configured. %s", dev_note or f"Would email {to}: {subject}")
        return False
    msg = EmailMessage()
    msg["From"] = s.default_smtp_from or s.default_smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    port = int(s.default_smtp_port or 465)
    ctx = ssl.create_default_context()
    log.info("Sending login email to %s via %s:%d (from %s)...", to, s.default_smtp_host, port, msg["From"])
    conn = smtplib.SMTP_SSL(s.default_smtp_host, port, context=ctx, timeout=20) if port == 465 \
        else smtplib.SMTP(s.default_smtp_host, port, timeout=20)
    with conn:
        if port != 465:
            conn.starttls(context=ctx)
        conn.login(s.default_smtp_user, s.default_smtp_password.get_secret_value())
        conn.send_message(msg)
    log.info("Successfully delivered login email to %s.", to)
    return True
