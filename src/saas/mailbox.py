"""The clinic's own mailbox: send approved drafts from it, read patient replies back.

Sending uses the clinic's SMTP login and reading uses IMAP with the same
credentials. For Google Workspace / Gmail that is the clinic address plus a
Google app password (2-Step Verification must be on).

Privacy rules:
- The inbox is opened read-only (BODY.PEEK): nothing is marked read, moved or deleted.
- Only messages that belong to a known lead are stored. Everything else in the
  clinic's mailbox is skipped without being saved.
"""

from __future__ import annotations

import email
import imaplib
import json
import logging
import re
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage, Message
from email.utils import formatdate, getaddresses, make_msgid, parsedate_to_datetime
from saas.database import connect, insert, now_iso, row, rows
from saas.security import decrypt_value, encrypt_value

log = logging.getLogger(__name__)

GMAIL = {"smtp_host": "smtp.gmail.com", "smtp_port": 465, "imap_host": "imap.gmail.com", "imap_port": 993,
         "sent_folder": "[Gmail]/Sent Mail"}
FIRST_SYNC_DAYS = 14
MAX_FETCH_PER_SYNC = 200


class MailboxError(Exception):
    """A user-facing problem with the clinic mailbox (not connected, bad login, send refused)."""


# ── Settings ─────────────────────────────────────────────────────────────────


def get_settings_row(tenant_id: int) -> dict | None:
    with connect() as c:
        return row(c, "SELECT * FROM email_settings WHERE tenant_id = ?", tenant_id)


def is_connected(tenant_id: int) -> bool:
    s = get_settings_row(tenant_id)
    if not s or s.get("provider") != "smtp" or not s.get("smtp_host"):
        return False
    return bool(s.get("oauth_refresh_enc") if s.get("auth_type") == "oauth" else s.get("smtp_password_enc"))


def connect_gmail(tenant_id: int, address: str, app_password: str, from_name: str | None = None) -> dict:
    """Store Gmail / Google Workspace credentials (encrypted) for sending and reply tracking."""
    address = address.strip().lower()
    secret = encrypt_value(app_password.replace(" ", ""))
    return _save_gmail(tenant_id, address, from_name, auth_type="password", smtp_password_enc=secret,
                       imap_password_enc=secret, oauth_refresh_enc=None)


def connect_gmail_oauth(tenant_id: int, address: str, refresh_token: str, from_name: str | None = None) -> dict:
    """Store a Google OAuth refresh token (encrypted). Sending/reading then use XOAUTH2, no password."""
    return _save_gmail(tenant_id, address.strip().lower(), from_name, auth_type="oauth",
                       oauth_refresh_enc=encrypt_value(refresh_token), smtp_password_enc=None, imap_password_enc=None)


def disconnect(tenant_id: int) -> dict:
    s = get_settings_row(tenant_id) or {}
    if s.get("auth_type") == "oauth" and s.get("oauth_refresh_enc"):
        from saas import google_oauth
        google_oauth.forget(tenant_id, decrypt_value(s["oauth_refresh_enc"]))
    with connect() as c:
        c.execute("UPDATE email_settings SET provider = 'default', smtp_password_enc = NULL, imap_password_enc = NULL, "
                  "oauth_refresh_enc = NULL, auth_type = NULL, updated_at = ? WHERE tenant_id = ?", (now_iso(), tenant_id))
    return mailbox_status(tenant_id)


def _save_gmail(tenant_id: int, address: str, from_name: str | None, **creds) -> dict:
    fields = {
        "provider": "smtp", "smtp_host": GMAIL["smtp_host"], "smtp_port": GMAIL["smtp_port"], "smtp_user": address,
        "imap_host": GMAIL["imap_host"], "imap_port": GMAIL["imap_port"], "imap_user": address,
        "sent_folder": GMAIL["sent_folder"], "from_email": address, "imap_state": None, "last_sync_error": None,
        **creds,
    }
    if from_name:
        fields["from_name"] = from_name
    with connect() as c:
        exists = row(c, "SELECT id FROM email_settings WHERE tenant_id = ?", tenant_id)
        fields["updated_at"] = now_iso()
        if exists:
            sets = ", ".join(f"{k} = ?" for k in fields)
            c.execute(f"UPDATE email_settings SET {sets} WHERE tenant_id = ?", [*fields.values(), tenant_id])
        else:
            insert(c, "email_settings", tenant_id=tenant_id, **fields)
    return mailbox_status(tenant_id)


def mailbox_status(tenant_id: int) -> dict:
    s = get_settings_row(tenant_id) or {}
    from saas import google_oauth
    connected = is_connected(tenant_id)
    return {"connected": connected, "address": s.get("smtp_user") if connected else None,
            "from_name": s.get("from_name"), "method": (s.get("auth_type") or "password") if connected else None,
            "google_sign_in_available": google_oauth.available(),
            "last_sync_at": s.get("last_sync_at"), "last_sync_error": s.get("last_sync_error")}


def test_mailbox(tenant_id: int) -> dict:
    """Log in to SMTP and IMAP without sending or reading anything."""
    s = _require(tenant_id)
    out = {"smtp": "ok", "imap": "ok"}
    try:
        with _smtp(s):
            pass
    except Exception as e:
        out["smtp"] = _friendly(e)
    try:
        imap = _imap(s)
        imap.logout()
    except Exception as e:
        out["imap"] = _friendly(e)
    out["ok"] = out["smtp"] == "ok" and out["imap"] == "ok"
    return out


def _require(tenant_id: int) -> dict:
    if not is_connected(tenant_id):
        raise MailboxError("The clinic mailbox is not connected yet. Connect Gmail in Settings first.")
    return get_settings_row(tenant_id)


def _friendly(e: Exception) -> str:
    text = str(e)
    if "Application-specific password required" in text or "BadCredentials" in text or "AUTHENTICATIONFAILED" in text \
            or "Username and Password not accepted" in text:
        return ("Google rejected the login. Reconnect with 'Sign in with Google', or use a Google app password "
                "(not the normal password; 2-Step Verification must be on).")
    if "revoked or expired" in text:
        return text
    return f"{type(e).__name__}: {text[:160]}"


# ── Transport (patched in tests) ─────────────────────────────────────────────


def _smtp(s: dict):
    import smtplib
    port = int(s.get("smtp_port") or 465)
    ctx = ssl.create_default_context()
    if port == 465:
        conn = smtplib.SMTP_SSL(s["smtp_host"], port, context=ctx, timeout=30)
    else:
        conn = smtplib.SMTP(s["smtp_host"], port, timeout=30)
        conn.starttls(context=ctx)
    if s.get("auth_type") == "oauth":
        auth = _xoauth2(s)
        conn.ehlo()
        conn.auth("XOAUTH2", lambda challenge=None: auth, initial_response_ok=True)
    else:
        conn.login(s["smtp_user"], decrypt_value(s["smtp_password_enc"]))
    return conn


def _imap(s: dict):
    conn = imaplib.IMAP4_SSL(s.get("imap_host") or GMAIL["imap_host"], int(s.get("imap_port") or 993),
                             ssl_context=ssl.create_default_context(), timeout=30)
    if s.get("auth_type") == "oauth":
        auth = _xoauth2(s).encode()
        conn.authenticate("XOAUTH2", lambda _challenge: auth)
    else:
        conn.login(s.get("imap_user") or s["smtp_user"],
                   decrypt_value(s.get("imap_password_enc") or s["smtp_password_enc"]))
    return conn


def _xoauth2(s: dict) -> str:
    from saas import google_oauth
    token = google_oauth.access_token(s["tenant_id"], decrypt_value(s["oauth_refresh_enc"]))
    return google_oauth.xoauth2(s["smtp_user"], token)


# ── Thread ───────────────────────────────────────────────────────────────────


def lead_thread(tenant_id: int, lead_id: int) -> list[dict]:
    with connect() as c:
        out = rows(c, "SELECT * FROM email_messages WHERE tenant_id = ? AND lead_id = ? ORDER BY sent_at, id",
                   tenant_id, lead_id)
    for m in out:
        m["classification"] = json.loads(m["classification"]) if m.get("classification") else None
    return out


def _thread_headers(tenant_id: int, lead_id: int) -> tuple[str | None, str | None, str | None]:
    """(in_reply_to, references, root_subject) so follow-ups land in the same Gmail thread."""
    thread = lead_thread(tenant_id, lead_id)
    if not thread:
        return None, None, None
    ids = [m["message_id"] for m in thread][-20:]
    return thread[-1]["message_id"], " ".join(ids), thread[0]["subject"]


def record_message(tenant_id: int, lead_id: int, direction: str, message_id: str, *, from_addr: str | None,
                   to_addr: str | None, subject: str | None, body: str | None, sent_at: str | None = None,
                   in_reply_to: str | None = None, references: str | None = None, draft_id: int | None = None,
                   cadence_step: str | None = None, source: str = "heyjarvis") -> dict | None:
    """Insert one thread message. Returns None if this Message-ID is already stored."""
    with connect() as c:
        if row(c, "SELECT id FROM email_messages WHERE tenant_id = ? AND message_id = ?", tenant_id, message_id):
            return None
        mid = insert(c, "email_messages", tenant_id=tenant_id, lead_id=lead_id, direction=direction,
                     message_id=message_id, in_reply_to=in_reply_to, references_hdr=references, from_addr=from_addr,
                     to_addr=to_addr, subject=subject, body=body, draft_id=draft_id, cadence_step=cadence_step,
                     source=source, sent_at=sent_at or now_iso(), created_at=now_iso())
        return row(c, "SELECT * FROM email_messages WHERE id = ?", mid)


# ── Send ─────────────────────────────────────────────────────────────────────


def send_draft(tenant_id: int, draft_id: int, *, subject: str | None = None, body: str | None = None,
               to: str | None = None) -> dict:
    """Send an approved draft from the clinic mailbox to the patient. Edits may be passed in at send time."""
    from saas.repositories import get_lead

    s = _require(tenant_id)
    with connect() as c:
        draft = row(c, "SELECT * FROM ai_drafts WHERE id = ? AND tenant_id = ?", draft_id, tenant_id)
    if not draft:
        raise LookupError("draft not found")
    if draft["status"] == "sent":
        raise MailboxError("This draft was already sent.")
    lead = get_lead(draft["lead_id"]) if draft.get("lead_id") else None
    if not lead:
        raise MailboxError("Draft is not attached to a patient.")
    recipient = (to or draft.get("to_email") or lead.get("email") or "").strip()
    if not recipient or "@" not in recipient:
        raise MailboxError("Patient has no email address on file.")
    text = (body if body is not None else draft["body"] or "").strip()
    if not text:
        raise MailboxError("Draft body is empty.")

    in_reply_to, references, root_subject = _thread_headers(tenant_id, lead["id"])
    subj = (subject if subject is not None else draft.get("subject") or "").strip() or "Your appointment request"
    if root_subject:  # keep everything in one thread for the patient and for Gmail
        base = re.sub(r"^(re:\s*)+", "", root_subject, flags=re.I)
        subj = f"Re: {base}"

    sender = s["from_email"] or s["smtp_user"]
    msg = EmailMessage()
    msg["From"] = f'{s["from_name"]} <{sender}>' if s.get("from_name") else sender
    msg["To"] = recipient
    msg["Subject"] = subj
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references
    msg.set_content(text)

    try:
        with _smtp(s) as conn:
            conn.send_message(msg)
    except Exception as e:
        err = _friendly(e)
        with connect() as c:
            c.execute("UPDATE ai_drafts SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                      (err, now_iso(), draft_id))
        raise MailboxError(f"Send failed: {err}") from e

    now = now_iso()
    with connect() as c:
        c.execute("UPDATE ai_drafts SET status = 'sent', subject = ?, body = ?, to_email = ?, sent_at = ?, error = NULL, "
                  "updated_at = ? WHERE id = ?", (subj, text, recipient, now, now, draft_id))
    record_message(tenant_id, lead["id"], "out", msg["Message-ID"], from_addr=sender, to_addr=recipient,
                   subject=subj, body=text, sent_at=now, in_reply_to=in_reply_to, references=references,
                   draft_id=draft_id, cadence_step=draft.get("cadence_step"))

    from saas import cadence
    cadence.on_outbound(tenant_id, lead["id"], draft.get("cadence_step"))
    if lead.get("status") == "new":
        from saas.repositories import update_lead
        update_lead(lead["id"], status="contacted")
    return {"ok": True, "message_id": msg["Message-ID"], "to": recipient, "subject": subj}


# ── Sync replies ─────────────────────────────────────────────────────────────


def sync_mailbox(tenant_id: int) -> dict:
    """Pull new patient replies (inbox) and desk-sent emails (sent folder) for known leads."""
    s = _require(tenant_id)
    state = json.loads(s.get("imap_state") or "{}")
    stats = {"inbound": 0, "outbound": 0, "skipped": 0}
    try:
        imap = _imap(s)
    except Exception as e:
        _save_sync(tenant_id, state, _friendly(e))
        raise MailboxError(_friendly(e)) from e
    try:
        for folder, direction in (("INBOX", "in"), (s.get("sent_folder") or GMAIL["sent_folder"], "out")):
            try:
                _sync_folder(imap, tenant_id, folder, direction, state, stats)
            except Exception as e:  # a missing Sent folder must not block reply tracking
                log.warning("mailbox sync %s failed for tenant %s: %s", folder, tenant_id, e)
                if direction == "in":
                    raise
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    _save_sync(tenant_id, state, None)
    return stats


def _save_sync(tenant_id: int, state: dict, error: str | None) -> None:
    with connect() as c:
        c.execute("UPDATE email_settings SET imap_state = ?, last_sync_at = ?, last_sync_error = ? WHERE tenant_id = ?",
                  (json.dumps(state), now_iso(), error, tenant_id))


def _sync_folder(imap, tenant_id: int, folder: str, direction: str, state: dict, stats: dict) -> None:
    typ, _ = imap.select(_quote(folder), readonly=True)
    if typ != "OK":
        raise MailboxError(f"cannot open {folder}")
    uidvalidity = _uidvalidity(imap)
    key = f"{direction}:{folder}"
    prev = state.get(key) or {}
    if prev.get("uidvalidity") != uidvalidity:
        prev = {"uidvalidity": uidvalidity, "last_uid": 0}
    last_uid = int(prev.get("last_uid") or 0)

    if last_uid:
        typ, data = imap.uid("SEARCH", None, f"UID {last_uid + 1}:*")
    else:
        since = (datetime.now() - timedelta(days=FIRST_SYNC_DAYS)).strftime("%d-%b-%Y")
        typ, data = imap.uid("SEARCH", None, f"SINCE {since}")
    uids = sorted(int(u) for u in (data[0] or b"").split() if int(u) > last_uid)[:MAX_FETCH_PER_SYNC]

    for uid in uids:
        typ, parts = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
        raw = next((p[1] for p in parts or [] if isinstance(p, tuple)), None)
        if raw:
            _ingest(tenant_id, email.message_from_bytes(raw), direction, stats)
        last_uid = max(last_uid, uid)
    state[key] = {"uidvalidity": uidvalidity, "last_uid": last_uid}


def _quote(folder: str) -> str:
    return folder if folder.upper() == "INBOX" else '"' + folder.replace('"', '\\"') + '"'


def _uidvalidity(imap) -> str:
    try:
        typ, data = imap.response("UIDVALIDITY")
        return (data[0].decode() if isinstance(data[0], bytes) else str(data[0])) if data and data[0] else ""
    except Exception:
        return ""


def _ingest(tenant_id: int, msg: Message, direction: str, stats: dict) -> None:
    message_id = (msg.get("Message-ID") or "").strip()
    if not message_id:
        stats["skipped"] += 1
        return
    in_reply_to = (msg.get("In-Reply-To") or "").strip() or None
    references = " ".join((msg.get("References") or "").split()) or None
    from_addr = _addr(msg.get("From"))
    to_addrs = [a.lower() for _, a in getaddresses(msg.get_all("To", []) + msg.get_all("Cc", [])) if a]

    lead = _match_lead(tenant_id, in_reply_to, references, from_addr if direction == "in" else None,
                       to_addrs if direction == "out" else [])
    if not lead:
        stats["skipped"] += 1
        return
    sent_at = _date(msg.get("Date"))
    body = _text_body(msg)
    saved = record_message(tenant_id, lead["id"], direction, message_id, from_addr=from_addr,
                           to_addr=", ".join(to_addrs), subject=msg.get("Subject"), body=body, sent_at=sent_at,
                           in_reply_to=in_reply_to, references=references, source="mailbox")
    if not saved:  # already have it (e.g. a draft we sent ourselves, now seen in Sent)
        return
    from saas import cadence
    if direction == "in":
        stats["inbound"] += 1
        cadence.on_reply(tenant_id, lead["id"], saved)
    else:
        stats["outbound"] += 1
        cadence.on_outbound(tenant_id, lead["id"], None)


def _match_lead(tenant_id: int, in_reply_to: str | None, references: str | None, from_addr: str | None,
                to_addrs: list[str]) -> dict | None:
    ids = [i for i in ([in_reply_to] if in_reply_to else []) + (references or "").split() if i]
    with connect() as c:
        if ids:
            marks = ",".join("?" * len(ids))
            hit = row(c, f"SELECT lead_id FROM email_messages WHERE tenant_id = ? AND message_id IN ({marks}) "
                         "ORDER BY id DESC LIMIT 1", tenant_id, *ids)
            if hit:
                return row(c, "SELECT * FROM leads WHERE id = ?", hit["lead_id"])
        for addr in ([from_addr] if from_addr else []) + to_addrs:
            hit = row(c, "SELECT * FROM leads WHERE tenant_id = ? AND lower(email) = ? ORDER BY id DESC LIMIT 1",
                      tenant_id, addr.lower())
            if hit:
                return hit
    return None


def _addr(value: str | None) -> str | None:
    found = [a for _, a in getaddresses([value or ""]) if a]
    return found[0].lower() if found else None


def _date(value: str | None) -> str:
    try:
        return parsedate_to_datetime(value).astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    except Exception:
        return now_iso()


def _text_body(msg: Message) -> str:
    part = msg.get_body(preferencelist=("plain", "html")) if hasattr(msg, "get_body") else None
    if part is None:
        for p in msg.walk():
            if p.get_content_type() in ("text/plain", "text/html"):
                part = p
                break
    if part is None:
        return ""
    payload = part.get_payload(decode=True) or b""
    text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        text = re.sub(r"<(br|/p|/div)[^>]*>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
    return strip_quoted(text)


def strip_quoted(text: str) -> str:
    """Keep only the new part of a reply (drop 'On ... wrote:' and '>' quoted history)."""
    out = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if re.match(r"^\s*On .{3,200}wrote:\s*$", line) or re.match(r"^-{2,}\s*Original Message", line, re.I):
            break
        if line.lstrip().startswith(">"):
            continue
        out.append(line)
    return "\n".join(out).strip()[:20000]


def connected_tenants() -> list[int]:
    with connect() as c:
        return [r["tenant_id"] for r in rows(c, "SELECT tenant_id FROM email_settings WHERE provider = 'smtp' "
                                                "AND imap_host IS NOT NULL "
                                                "AND (smtp_password_enc IS NOT NULL OR oauth_refresh_enc IS NOT NULL)")]

