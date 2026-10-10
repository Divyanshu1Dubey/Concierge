"""
Inbound patient replies.

A reply is accepted only when its In-Reply-To/References headers point at a Message-ID
that Concierge itself sent, so unrelated mailbox content is never imported. A matched
reply is added to the request's email thread, pauses that patient's active follow-up
cadences, puts the request back in front of the front desk and (if the practice wants
it) emails the team. Drafting the answer stays a human-reviewed step.
"""
import email
import email.header
import imaplib
import logging
import re
from datetime import timedelta
from email.utils import parseaddr

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Email, EmailCadence

logger = logging.getLogger(__name__)

OUR_MSGID = re.compile(r"<[^<>@\s]+@[^<>\s]*heyjarvis\.ai>", re.I)
QUOTE_HEADER = re.compile(r"^\s*On .+wrote:\s*$")


def _plain_body(msg) -> str:
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                payload = part.get_payload(decode=True) or b""
                text = payload.decode(part.get_content_charset() or "utf-8", "replace")
                break
    else:
        payload = msg.get_payload(decode=True) or b""
        text = payload.decode(msg.get_content_charset() or "utf-8", "replace")
    # Keep only the new text: drop quoted history ("> ..." and "On ... wrote:").
    lines = []
    for line in text.splitlines():
        if line.strip().startswith(">") or QUOTE_HEADER.match(line):
            break
        lines.append(line)
    return "\n".join(lines).strip()[:20000]


def ingest_email_message(msg) -> dict:
    """Store one inbound email if it answers a message we sent. Returns {"status": ...}."""
    header_text = " ".join([str(msg.get("In-Reply-To", "")), str(msg.get("References", ""))])
    refs = OUR_MSGID.findall(header_text)
    if not refs:
        return {"status": "ignored"}
    incoming_id = (msg.get("Message-ID") or "").strip()
    if incoming_id and Email.objects.filter(direction=Email.DIRECTION_INCOMING, provider_message_id=incoming_id).exists():
        return {"status": "duplicate"}
    parent = (Email.objects.filter(direction=Email.DIRECTION_OUTGOING, provider_message_id__in=refs)
              .select_related("thread", "thread__practice").order_by("-created_at").first())
    if not parent:
        return {"status": "unmatched"}
    thread = parent.thread
    sender = parseaddr(msg.get("From", ""))[1].lower()
    subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))[:500]
    body = _plain_body(msg)
    now = timezone.now()

    with transaction.atomic():
        reply = Email.objects.create(
            thread=thread, direction=Email.DIRECTION_INCOMING, status=Email.STATUS_RECEIVED,
            from_email=sender or thread.patient_email, to_email=parent.from_email,
            subject=subject or ("Re: " + thread.subject), body=body,
            provider_message_id=incoming_id[:200], provider="inbound", sent_at=now,
        )
        thread.last_message_at = now
        thread.status = thread.STATUS_ACTIVE
        thread.save(update_fields=["last_message_at", "status", "updated_at"])

        paused = 0
        for cadence in EmailCadence.objects.filter(
            practice=thread.practice, patient_email__iexact=thread.patient_email, status=EmailCadence.STATUS_ACTIVE
        ):
            cadence.status = EmailCadence.STATUS_PAUSED
            cadence.next_scheduled_at = None
            cadence.metadata = {**(cadence.metadata or {}), "paused_reason": "patient_replied", "paused_at": now.isoformat()}
            cadence.save(update_fields=["status", "next_scheduled_at", "metadata", "updated_at"])
            paused += 1

        appt = thread_appointment(thread)
        if appt is not None:
            notes = list(appt.internal_notes or [])
            notes.append({"author": "Concierge", "text": "Patient replied by email. Review the reply and draft a response.",
                          "created_at": now.isoformat()})
            appt.internal_notes = notes
            fields = ["internal_notes"]
            if appt.status == "contacted":
                appt.status = "pending"
                fields.append("status")
            appt.save(update_fields=fields)
            appt_id = appt.id
            transaction.on_commit(lambda: _notify_reply(appt_id))
    return {"status": "stored", "email_id": str(reply.id), "practice_id": thread.practice_id, "cadences_paused": paused}


def thread_appointment(thread):
    from apps.appointments.models import Appointment
    appt_id = (thread.metadata or {}).get("appointment_id")
    if not appt_id:
        return None
    return Appointment.objects.filter(id=appt_id, practice=thread.practice).first()


def _notify_reply(appointment_id):
    from django.core.mail import send_mail
    from apps.appointments.models import Appointment
    appt = Appointment.objects.select_related("practice").filter(id=appointment_id).first()
    if not appt or not getattr(settings, "EMAIL_CONFIGURED", False):
        return
    ps = getattr(appt.practice, "settings", None)
    if ps is not None and not ps.notify_on_patient_reply:
        return
    cfg = (ps.notification_emails if ps is not None else None) or {}
    recipient = (cfg.get("appointment") or cfg.get("general")) if isinstance(cfg, dict) else None
    recipient = recipient or appt.practice.email
    if not recipient:
        return
    base = (getattr(settings, "FRONTEND_URL", "") or getattr(settings, "APP_PUBLIC_URL", "")).rstrip("/")
    link = base + "/dashboard/requests/" + str(appt.id)
    try:
        send_mail("Patient replied (" + appt.confirmation_code + ")",
                  "A patient replied to your email.\n\nReview it in the dashboard: " + link + "\n",
                  settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
    except Exception as exc:
        logger.warning("Reply notification failed (practice=%s): %s", appt.practice_id, type(exc).__name__)


def inbound_mailbox_configured() -> bool:
    return bool(getattr(settings, "IMAP_HOST", "") and getattr(settings, "IMAP_USER", "") and getattr(settings, "IMAP_PASSWORD", ""))


def fetch_replies(days: int = 7, limit: int = 1000) -> dict:
    """Read-only scan of the inbound mailbox for replies to Concierge emails (nothing is marked read)."""
    if not inbound_mailbox_configured():
        return {"configured": False, "stored": 0}
    since = (timezone.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    counts = {"configured": True, "checked": 0, "stored": 0, "duplicate": 0, "unmatched": 0, "practice_ids": []}
    box = imaplib.IMAP4_SSL(settings.IMAP_HOST, 993, timeout=30)
    try:
        box.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
        box.select("INBOX", readonly=True)
        typ, data = box.search(None, "SINCE", since)
        ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-limit:]
        # One round trip per 200 messages for the reply headers; full bodies only for real replies.
        matches = []
        for start in range(0, len(ids), 200):
            chunk = b",".join(ids[start:start + 200]).decode()
            typ, rows = box.fetch(chunk, "(BODY.PEEK[HEADER.FIELDS (IN-REPLY-TO REFERENCES)])")
            if typ != "OK":
                continue
            for row in rows or []:
                if isinstance(row, tuple) and OUR_MSGID.search(row[1].decode("utf-8", "replace")):
                    matches.append(row[0].split()[0])
        for num in matches:
            counts["checked"] += 1
            typ, full = box.fetch(num, "(BODY.PEEK[])")
            if typ != "OK" or not full or not isinstance(full[0], tuple):
                continue
            result = ingest_email_message(email.message_from_bytes(full[0][1]))
            if result["status"] in counts:
                counts[result["status"]] += 1
            if result.get("practice_id"):
                counts["practice_ids"].append(result["practice_id"])
    finally:
        try:
            box.logout()
        except Exception:
            pass
    return counts