"""Email system with tenant-level settings, templates, and provider abstraction."""

from __future__ import annotations

import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from saas.config import get_settings
from saas.database import connect, now_iso
from saas.repositories import create_lead, track_event
from saas.security import decrypt_value

settings = get_settings()
ROOT = Path(__file__).resolve().parents[2]
OUTBOX = ROOT / "outbox" / "sent"
OUTBOX.mkdir(parents=True, exist_ok=True)


class SendResult:
    def __init__(self, ok: bool, mode: str, ref: str | None = None, error: str | None = None) -> None:
        self.ok = ok
        self.mode = mode
        self.ref = ref
        self.error = error


class MailboxNotConnected(RuntimeError):
    """Production send with no clinic mailbox: refused instead of dry-running to the outbox."""


def _refuse_dry_run_in_production(tenant_id: int) -> None:
    # The dry-run outbox writes the whole email (patient details) to disk and reports it as sent.
    if get_settings().is_production and _provider(tenant_id) == "default":
        raise MailboxNotConnected("Connect the clinic mailbox in Settings → Email first.")


# ── Template Engine ─────────────────────────────────────────────────────────


def _render(template: str, payload: dict[str, Any]) -> str:
    out = template
    for key, value in (payload or {}).items():
        out = out.replace("{{" + key + "}}", str(value or ""))
    return out


# ── Sending ─────────────────────────────────────────────────────────────────


def _sender(tenant_id: int) -> str:
    from_name = _setting(tenant_id, "from_name")
    from_email = _setting(tenant_id, "from_email")
    if from_name and from_email:
        return f"{from_name} <{from_email}>"
    return from_email or settings.default_smtp_from or "frontdesk@example.com"


def _provider(tenant_id: int) -> str:
    with connect() as c:
        r = row(c, "SELECT provider FROM email_settings WHERE tenant_id = ?", (tenant_id,))
    return r["provider"] if r else "default"


def _setting(tenant_id: int, key: str) -> str | None:
    mapping = {
        "smtp_host": "smtp_host",
        "smtp_port": "smtp_port",
        "smtp_user": "smtp_user",
        "smtp_password_enc": "smtp_password_enc",
        "from_email": "from_email",
        "from_name": "from_name",
        "reply_to": "reply_to",
        "front_desk_email": "front_desk_email",
    }
    col = mapping.get(key)
    if not col:
        return None
    with connect() as c:
        r = row(c, f"SELECT {col} FROM email_settings WHERE tenant_id = ?", tenant_id)
    return r[col] if r and r[col] is not None else None


def _smtp_row(tenant_id: int) -> dict | None:
    with connect() as c:
        return row(c, "SELECT * FROM email_settings WHERE tenant_id = ?", (tenant_id,))


def send_email(
    tenant_id: int,
    to: str,
    subject: str,
    body: str,
    *,
    reply_to: str | None = None,
    context: dict[str, Any] | None = None,
    max_retries: int = 3,
) -> SendResult:
    """Send an email with retry logic. Raises MailboxNotConnected in production without a mailbox."""
    _refuse_dry_run_in_production(tenant_id)
    context = context or {}
    msg = EmailMessage()
    msg["From"] = _sender(tenant_id)
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = _date_header()
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    provider = _provider(tenant_id)
    if provider == "default":
        return _dry_run_send(to, subject, body)

    last_error = None
    for attempt in range(max_retries):
        try:
            result = _smtp_send(tenant_id, msg)
            if result:
                track_event(tenant_id, "email_sent", {"to": to, "subject": subject, "attempt": attempt + 1})
                return SendResult(True, "live", msg["Message-ID"])
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)[:160]}"
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
                continue

    track_event(tenant_id, "email_failed", {"to": to, "error": last_error})
    return SendResult(False, "live", error=last_error)


def _smtp_send(tenant_id: int, msg: EmailMessage) -> bool:
    host = _setting(tenant_id, "smtp_host")
    port = int(_setting(tenant_id, "smtp_port") or 465)
    user = _setting(tenant_id, "smtp_user")
    password = decrypt_value(_setting(tenant_id, "smtp_password_enc"))

    ctx = ssl.create_default_context()
    if port == 465:
        smtp = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)
        smtp.starttls(context=ctx)
    with smtp:
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)
    return True


def send_lead_notification(tenant_id: int, lead_id: int, intent: str = "default", subject_override: str | None = None) -> SendResult:
    """Send a lead notification email using the configured template."""
    from saas.repositories import get_lead, get_conversation

    lead = get_lead(lead_id)
    if not lead:
        return SendResult(False, "default", error="lead not found")
    _refuse_dry_run_in_production(tenant_id)

    conversation = get_conversation(lead.get("conversation_id")) if lead.get("conversation_id") else None

    from saas.email_templates import build_payload, get_default_template, render_template
    from saas.repositories import get_tenant

    tenant = get_tenant(tenant_id)
    tenant_name = tenant.name if tenant else "HeyJarvis"

    payload = build_payload(tenant_name, lead, conversation)

    template = get_default_template(intent)
    subject = subject_override or render_template(template["subject"], payload)
    body = render_template(template["body"], payload)

    # Get front desk email from email_settings
    front_desk_email = _setting(tenant_id, "front_desk_email") or settings.default_smtp_reply_to
    reply_to = _setting(tenant_id, "reply_to") or settings.default_smtp_reply_to

    track_event(tenant_id, "notification_created", {
        "lead_id": lead_id,
        "channel": "email",
        "intent": intent,
    })

    result = send_email(tenant_id, front_desk_email, subject, body, reply_to=reply_to, context=payload)

    # Record notification in DB
    from saas.repositories import create_notification
    create_notification(tenant_id, lead_id, "email", "sent" if result.ok else "failed",
                        {"to": front_desk_email, "subject": subject, "mode": result.mode},
                        error=result.error)

    return result


def send_test_email(tenant_id: int, to: str) -> SendResult:
    """Send a test email to verify SMTP configuration."""
    from saas.email_templates import build_payload, get_default_template, render_template
    from saas.repositories import get_tenant

    tenant = get_tenant(tenant_id)
    tenant_name = tenant.name if tenant else "HeyJarvis"

    template = get_default_template("test")
    payload = build_payload(tenant_name)
    subject = render_template(template["subject"], payload)
    body = render_template(template["body"], payload)

    return send_email(tenant_id, to, subject, body, max_retries=1)


def test_smtp_connection(tenant_id: int) -> tuple[bool, str]:
    """Test SMTP connection without sending an email."""
    host = _setting(tenant_id, "smtp_host")
    port = int(_setting(tenant_id, "smtp_port") or 465)
    if not host:
        return False, "No SMTP host configured"

    try:
        ctx = ssl.create_default_context()
        if port == 465:
            smtp = smtplib.SMTP_SSL(host, port, context=ctx, timeout=15)
        else:
            smtp = smtplib.SMTP(host, port, timeout=15)
            smtp.starttls(context=ctx)
        with smtp:
            user = _setting(tenant_id, "smtp_user")
            password = decrypt_value(_setting(tenant_id, "smtp_password_enc"))
            if user and password:
                smtp.login(user, password)
        return True, f"Connected to {host}:{port} successfully"
    except Exception as e:
        return False, f"Connection failed: {type(e).__name__}: {str(e)[:120]}"


# ── Dry-run / Outbox ─────────────────────────────────────────────────────────


def _dry_run_send(to: str, subject: str, body: str) -> SendResult:
    msg = EmailMessage()
    msg["From"] = settings.default_smtp_from or "frontdesk@example.com"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    path = OUTBOX / f"{_now_prefix()}-{_uid()}.eml"
    path.write_bytes(bytes(msg))
    return SendResult(True, "dry-run", str(path))


# ── Helpers ──────────────────────────────────────────────────────────────────


def _date_header() -> str:
    from email.utils import formatdate
    return formatdate(localtime=True)


def _now_prefix() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _uid() -> str:
    import secrets
    return secrets.token_hex(6)


# ── DB helpers (local, avoid circular imports) ────────────────────────────────


def row(conn, sql: str, *args):
    if len(args) == 1 and isinstance(args[0], (tuple, list)):
        args = tuple(args[0])
    rows = conn.execute(sql, args).fetchall()
    return dict(rows[0]) if rows else None
