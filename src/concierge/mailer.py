"""Sends patient emails over SMTP from the dashboard.

Live when SMTP_USER and SMTP_PASSWORD are set (port 465 = SSL, 587 = STARTTLS).
Otherwise, or with CONCIERGE_SMTP_DRYRUN=1, nothing is sent: each email is
saved to outbox/sent/ so the demo works end to end.
"""

from __future__ import annotations

import os
import smtplib
import ssl
import time
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from .store import ROOT


@dataclass
class SendResult:
    ok: bool
    ref: str
    mode: str  # live | dry-run
    error: str | None = None


def mode() -> str:
    env = os.environ
    if env.get("CONCIERGE_SMTP_DRYRUN") == "1" or not (env.get("SMTP_USER") and env.get("SMTP_PASSWORD")):
        return "dry-run"
    return "live"


def sender() -> str:
    return os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "frontdesk@example.com"


def send(to: str, subject: str, body: str, *, reply_to: str | None = None) -> SendResult:
    msg = EmailMessage()
    msg["From"] = sender()
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender().split("@")[-1] or "concierge.local")
    msg.set_content(body)

    if mode() == "dry-run":
        out = Path(os.environ.get("CONCIERGE_OUTBOX") or ROOT / "outbox") / "sent"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.eml"
        path.write_bytes(bytes(msg))
        return SendResult(True, str(path), "dry-run")

    env = os.environ
    host, port = env.get("SMTP_HOST", "smtp.gmail.com"), int(env.get("SMTP_PORT", "465"))
    try:
        ctx = ssl.create_default_context()
        if port == 465:
            smtp = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
        else:
            smtp = smtplib.SMTP(host, port, timeout=30)
            smtp.starttls(context=ctx)
        with smtp:
            smtp.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
            smtp.send_message(msg)
        return SendResult(True, msg["Message-ID"], "live")
    except Exception as e:
        return SendResult(False, "", "live", f"{type(e).__name__}: {str(e)[:160]}")


def check_login() -> tuple[bool, str]:
    """Logs in without sending anything. For the dashboard status chip."""
    if mode() == "dry-run":
        return True, "dry-run (emails saved to outbox/sent)"
    env = os.environ
    host, port = env.get("SMTP_HOST", "smtp.gmail.com"), int(env.get("SMTP_PORT", "465"))
    try:
        ctx = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) if port == 465 else smtplib.SMTP(host, port, timeout=15)
        with smtp:
            if port != 465:
                smtp.starttls(context=ctx)
            smtp.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
        return True, f"live via {host}"
    except Exception as e:
        return False, f"login failed: {type(e).__name__}"
