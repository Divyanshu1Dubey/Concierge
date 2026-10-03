"""Email system with tenant-level settings, templates, and provider abstraction."""

from __future__ import annotations

import os
import smtplib
import ssl
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


def _render(template: str, payload: dict[str, Any]) -> str:
    out = template
    for key, value in payload.items():
        out = out.replace("{{" + key + "}}", str(value or ""))
    return out


def send_email(tenant_id: int, to: str, subject: str, body: str, *, reply_to: str | None = None,
               context: dict[str, Any] | None = None) -> SendResult:
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
    try:
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
        track_event(tenant_id, "email_sent", {"to": to, "subject": subject})
        return SendResult(True, "live", msg["Message-ID"])
    except Exception as e:  # pragma: no cover - network path
        track_event(tenant_id, "email_failed", {"to": to, "error": str(e)[:200]})
        return SendResult(False, "live", error=f"{type(e).__name__}: {str(e)[:160]}")


def send_lead_notification(tenant_id: int, lead_id: int) -> SendResult:
    # placeholder for notification routing: email draft/direct/webhook/etc.
    track_event(tenant_id, "notification_created", {"lead_id": lead_id, "channel": "email"})
    return SendResult(True, "default", ref=f"lead:{lead_id}")


def render_template(tenant_id: int, name: str, payload: dict[str, Any]) -> tuple[str, str]:
    templates = _load_templates(tenant_id)
    tmpl = templates.get(name) or templates.get("default") or {"subject": "New lead", "body": "{{message}}"}
    subject = _render(tmpl.get("subject", ""), payload)
    body = _render(tmpl.get("body", ""), payload)
    return subject, body


def _sender(tenant_id: int) -> str:
    return _setting(tenant_id, "from_email") or settings.default_smtp_from or "frontdesk@example.com"


def _provider(tenant_id: int) -> str:
    with connect() as c:
        r = row(c, "SELECT provider FROM email_settings WHERE tenant_id = ?", tenant_id)
    return r["provider"] if r else "default"


def _smtp_row(tenant_id: int) -> dict | None:
    with connect() as c:
        return row(c, "SELECT * FROM email_settings WHERE tenant_id = ?", tenant_id)


def _setting(tenant_id: int, key: str) -> str | None:
    mapping = {
        "smtp_host": "smtp_host",
        "smtp_port": "smtp_port",
        "smtp_user": "smtp_user",
        "smtp_password_enc": "smtp_password_enc",
        "from_email": "from_email",
        "from_name": "from_name",
        "reply_to": "reply_to",
    }
    col = mapping.get(key)
    if not col:
        return None
    with connect() as c:
        r = row(c, f"SELECT {col} FROM email_settings WHERE tenant_id = ?", tenant_id)
    return r[col] if r and r[col] is not None else None


def _dry_run_send(to: str, subject: str, body: str) -> SendResult:
    msg = EmailMessage()
    msg["From"] = settings.default_smtp_from or "frontdesk@example.com"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    path = OUTBOX / f"{_now_prefix()}-{_uid()}.eml"
    path.write_bytes(bytes(msg))
    return SendResult(True, "dry-run", str(path))


def _load_templates(tenant_id: int) -> dict[str, Any]:
    import json
    with connect() as c:
        r = row(c, "SELECT value FROM tenant_settings WHERE tenant_id = ? AND key = ?", tenant_id, "email_templates")
    if not r:
        return {}
    try:
        return json.loads(r["value"])
    except Exception:
        return {}


def _date_header() -> str:
    from email.utils import formatdate
    return formatdate(localtime=True)


def _now_prefix() -> str:
    import time
    return time.strftime("%Y%m%d-%H%M%S")


def _uid() -> str:
    import secrets
    return secrets.token_hex(6)
