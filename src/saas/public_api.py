"""Public-facing API for the embeddable widget and hosted concierge pages."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import logging
import os
import secrets
import zipfile
from urllib.parse import parse_qs
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from starlette import status
from pydantic import BaseModel

from saas.auth import get_current, oauth2, require_roles, login_for_token, TokenOut, CurrentUser
from saas.rate_limit import check_rate_limit
from saas.config import get_settings
from saas.conversation import ConversationEngine, DEFAULT_GREETING, State
from saas.database import connect, now_iso, row, rows
from saas.emailer import (
    MailboxNotConnected,
    send_lead_notification,
    send_test_email,
    test_smtp_connection,
    _smtp_row,
)
from saas.email_templates import list_template_variables
from saas.conversation import ConversationContext
from saas.repositories import (
    add_domain as repo_add_domain,
    complete_conversation,
    create_conversation,
    create_lead,
    get_conversation,
    list_leads,
    get_lead,
    get_conversation,
    get_tenant_by_slug,
    list_domains as repo_list_domains,
    list_tenants,
    list_leads,
    remove_domain as repo_remove_domain,
    track_event,
    update_lead as repo_update_lead,
    verify_domain as repo_verify_domain,
    get_frontdesk_dashboard,
    get_fd_lead_detail,
    create_frontdesk_note,
    get_frontdesk_notes,
    create_frontdesk_task,
    get_frontdesk_tasks,
    complete_frontdesk_task,
    create_ai_draft,
    get_ai_drafts,
    mark_draft_sent,
    get_api_key_by_public,
)
from saas import ai_engine as _ai_engine
from saas import cadence, mailbox
from starlette.concurrency import run_in_threadpool

log = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    """The visitor's address as our hosting proxy saw it.

    uvicorn runs with --proxy-headers --forwarded-allow-ips '*', which makes request.client the LEFTMOST
    X-Forwarded-For entry: whatever the visitor typed into that header. The proxy appends the real address,
    so the RIGHTMOST entry is the one to trust."""
    hops = [h.strip() for v in request.headers.getlist("x-forwarded-for") for h in v.split(",") if h.strip()]
    if not hops:
        return request.client.host if request.client else "unknown"
    ip = hops[-1]
    if ip.startswith("["):  # "[2001:db8::1]:443"
        return ip[1:].split("]")[0]
    return ip.split(":")[0] if ip.count(":") == 1 else ip  # "203.0.113.9:443"; bare IPv6 stays as is


def _limit(request: Request, bucket: str, limit: int, window: int = 60) -> None:
    """Per-IP rate limit for unauthenticated endpoints (lead spam, login guessing)."""
    ip = _client_ip(request)
    allowed, _ = check_rate_limit(f"rl:{bucket}:{ip}", limit, window)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again shortly.",
                            headers={"Retry-After": str(window)})


def _own(cu: CurrentUser, tenant_id: int | None) -> None:
    """403 unless the logged-in user belongs to tenant_id. 404 when the record has no tenant (not found)."""
    if tenant_id is None:
        raise HTTPException(status_code=404, detail="not found")
    if cu.user.tenant_id != int(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="wrong tenant")
settings = get_settings()
STATIC = Path(__file__).resolve().parent / "static"

public_app = FastAPI(title="HeyJarvis Concierge Public", version="1.0.0")
public_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Conversation-Token"],
)


# ── Public Auth ──────────────────────────────────────────────────────────────

async def _extract_auth_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    if "application/x-www-form-urlencoded" in content_type:
        raw = await request.body()
        return {k: v[0] for k, v in parse_qs(raw.decode("utf-8", errors="ignore")).items()}
    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
            return dict(form)
        except Exception:
            raw = await request.body()
            return {k: v[0] for k, v in parse_qs(raw.decode("utf-8", errors="ignore")).items()}
    try:
        body = await request.json()
        if isinstance(body, dict):
            return body
    except Exception:
        pass
    try:
        raw = await request.body()
        return {k: v[0] for k, v in parse_qs(raw.decode("utf-8", errors="ignore")).items()}
    except Exception:
        return {}


class LoginBody(BaseModel):
    tenant_slug: str = "raleigh-dental-demo"
    email: str | None = None
    username: str | None = None
    password: str = ""


@public_app.post("/{tenant_slug}/auth/token")
@public_app.post("/auth/token")
@public_app.post("/auth/login")
async def public_tenant_login(
    request: Request,
    tenant_slug: str | None = None,
) -> TokenOut:
    _limit(request, "login", 10)
    data = await _extract_auth_payload(request)
    slug = str(tenant_slug or data.get("tenant_slug") or "raleigh-dental-demo").strip()
    username = str(data.get("username") or data.get("email") or "").strip()
    password = str(data.get("password") or "")

    if not username or not password:
        raise HTTPException(status_code=422, detail="Username/email and password are required")

    # get_tenant_by_slug creates the demo clinic on demand outside production only.
    # Never fall back to "the only clinic": a typo'd clinic ID must not log into someone else's.
    tenant = get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")

    return login_for_token(tenant.id, OAuth2PasswordRequestForm(username=username, password=password))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tenant_config(tenant_id: int) -> dict[str, Any]:
    with connect() as c:
        row_data = rows(c, "SELECT flags, ai_instructions FROM tenant_settings WHERE tenant_id = ?", (tenant_id,))
    out: dict[str, Any] = {}
    if row_data:
        flags_raw = row_data[0].get("flags") or "{}"
        try:
            out.update(json.loads(flags_raw))
        except json.JSONDecodeError:
            pass
        if row_data[0].get("ai_instructions"):
            out["ai_instructions"] = row_data[0]["ai_instructions"]
    out.setdefault("greeting", DEFAULT_GREETING)
    return out


def _load_tenant(tenant_id: int) -> dict[str, Any]:
    with connect() as c:
        r = rows(c, "SELECT id, name, slug, enabled, metadata FROM tenants WHERE id = ?", (tenant_id,))
    if not r:
        raise HTTPException(status_code=404, detail="tenant not found")
    t = r[0]
    return {
        "id": t["id"],
        "name": t["name"],
        "slug": t["slug"],
        "enabled": bool(t["enabled"]),
        "metadata": json.loads(t["metadata"] or "{}"),
    }


def _load_integration(tenant_id: int) -> dict[str, Any]:
    public_key = _public_key(tenant_id)
    app_url = os.environ.get("APP_URL", "http://localhost:8000").rstrip("/")
    with connect() as c:
        domains = rows(c, "SELECT * FROM domains WHERE tenant_id = ? ORDER BY id", (tenant_id,))
        widget_row = row(c, "SELECT config FROM widget_settings WHERE tenant_id = ?", (tenant_id,))
    widget_config = {}
    if widget_row:
        try:
            widget_config = json.loads(widget_row.get("config") or "{}")
        except (json.JSONDecodeError, TypeError):
            widget_config = {}
    slug = ""
    with connect() as c2:
        r = row(c2, "SELECT slug FROM tenants WHERE id = ?", tenant_id)
        if r:
            slug = r["slug"]
    return {
        "public_key": public_key,
        "widget_url": app_url + "/widget.js",
        "concierge_url": app_url + "/concierge/" + slug,
        "domains": [{"id": d["id"], "domain": d["domain"], "verified": bool(d["verified"])} for d in domains],
        "domain_count": len(domains),
        "widget_config": widget_config,
    }


def _public_key(tenant_id: int) -> str:
    with connect() as c:
        r = row(c, "SELECT public_key FROM api_keys WHERE tenant_id = ? LIMIT 1", (tenant_id,))
    return r["public_key"] if r else ""


# ── Public Routes ────────────────────────────────────────────────────────────

@public_app.get("/health")
def public_health() -> dict:
    return {"ok": True}


@public_app.get("/v1/public/config")
@public_app.get("/api/v1/public/config")
def public_config(client_key: str, request: Request) -> dict:
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")
    with connect() as c:
        tenant = rows(c, "SELECT id, name, slug, enabled FROM tenants WHERE id = ? AND enabled = 1", (key.tenant_id,))
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    origin = request.headers.get("origin", "").replace("https://", "").replace("http://", "").split("/")[0].lower()
    domain_ok = False
    if origin:
        with connect() as c:
            d = rows(c, "SELECT 1 FROM domains WHERE tenant_id = ? AND domain = ?", key.tenant_id, origin)
        domain_ok = bool(d)
    cfg = _tenant_config(tenant[0]["id"])
    return {
        "tenant_id": tenant[0]["id"],
        "tenant_name": tenant[0]["name"],
        "tenant_slug": tenant[0]["slug"],
        "greeting": cfg.get("greeting"),
        "allowed_origin": domain_ok,
        "widget_config": _public_widget_config(key.tenant_id, cfg),
    }


# Look and feel the clinic sets in the widget editor. Everything else in settings stays server side.
_WIDGET_BRANDING = ("title", "primary_color", "text_color", "accent_color", "position", "icon", "auto_open",
                    "auto_open_delay")


def _public_widget_config(tenant_id: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """Only what the patient-facing widget shows. The key is public, so no AI instructions or internal flags."""
    with connect() as c:
        r = row(c, "SELECT config FROM widget_settings WHERE tenant_id = ?", tenant_id)
    try:
        branding = json.loads(r["config"] or "{}") if r else {}
    except (json.JSONDecodeError, TypeError):
        branding = {}
    out = {k: branding[k] for k in _WIDGET_BRANDING if isinstance(branding, dict) and k in branding}
    out.update({
        "greeting": cfg.get("greeting"),
        "service_options": ConversationEngine(cfg).options_for(None),
        "clinic": {"phone": str((cfg.get("clinic") or {}).get("phone") or "")},  # emergency "call us" banner
    })
    return out


# The client key is printed in every website snippet, so it can't protect one patient's chat from another
# visitor. Each conversation gets its own secret, returned once at start and required on every later call.
CONVERSATION_TOKEN_HEADER = "X-Conversation-Token"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _patient_conversation(conversation_id: int, tenant_id: int, request: Request) -> dict[str, Any]:
    """The conversation, for the browser that started it only. Wrong clinic, token or id are all the same 404."""
    token = request.headers.get(CONVERSATION_TOKEN_HEADER) or ""
    with connect() as c:
        conv = row(c, "SELECT id, tenant_id, status, metadata, access_token, lead_id FROM conversations WHERE id = ?",
                   conversation_id)
    if not conv or conv["tenant_id"] != tenant_id or not conv["access_token"] or not token \
            or not hmac.compare_digest(conv["access_token"], _token_hash(token)):
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


@public_app.post("/v1/public/conversations")
@public_app.post("/api/v1/public/conversations")
def public_conversation_start(client_key: str, request: Request) -> dict:
    _limit(request, "conv_start", 20)
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")
    tenant = _load_tenant(key.tenant_id)
    if not tenant["enabled"]:
        raise HTTPException(status_code=403, detail="tenant disabled")
    cfg = _tenant_config(key.tenant_id)
    engine = ConversationEngine(cfg)
    result = engine.start(
        key.tenant_id,
        str(request.url),
        request.headers.get("referer"),
        request.headers.get("user-agent"),
        _client_ip(request),
    )
    token = secrets.token_urlsafe(32)
    with connect() as c:  # only a hash is stored: staff views of the conversation row never expose a usable token
        c.execute("UPDATE conversations SET access_token = ? WHERE id = ?", (_token_hash(token), result["conversation_id"]))
    result["conversation_token"] = token
    track_event(key.tenant_id, "conversation_started", {"conversation_id": result["conversation_id"]})
    return result


@public_app.post("/v1/public/conversations/{conversation_id}/messages")
@public_app.post("/api/v1/public/conversations/{conversation_id}/messages")
def public_conversation_message(conversation_id: int, body: dict[str, Any], client_key: str, request: Request) -> dict:
    _limit(request, "conv_msg", 60)
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")
    conv = _patient_conversation(conversation_id, key.tenant_id, request)

    # Load persisted fields from metadata so turns accumulate
    meta_raw = conv.get("metadata") or "{}"
    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    existing_fields = meta.get("fields") or {}

    ctx = ConversationContext(conversation_id=conversation_id, tenant_id=conv["tenant_id"], fields=existing_fields)
    context = ConversationEngine(_tenant_config(key.tenant_id))
    if conv["lead_id"] is not None:
        # Already sent: keep the message with that request, but no second lead, staff alert or follow-up schedule.
        # "Start a new request" in the widget opens a new conversation for anything else.
        return context.after_submit(ctx, str(body.get("message", "")))
    result = context.handle(ctx, body.get("message", ""))

    # Persist updated fields back to metadata
    updated_meta = dict(meta)
    updated_meta["fields"] = ctx.fields
    with connect() as c:
        c.execute("UPDATE conversations SET metadata = ?, updated_at = ? WHERE id = ?",
                  (json.dumps(updated_meta), now_iso(), conversation_id))

    if ctx.state == State.SUBMITTED and _claim_lead_slot(conversation_id):
        try:
            lead = create_lead(key.tenant_id, {
                "conversation_id": conversation_id,
                "source": "website_widget",
                "page_url": conv.get("metadata", {}).get("page_url") if isinstance(conv.get("metadata"), dict) else None,
                **ctx.fields,
            })
        except Exception:
            with connect() as c:  # release the claim so the patient's next message can still submit
                c.execute("UPDATE conversations SET lead_id = NULL WHERE id = ?", (conversation_id,))
            raise
        with connect() as c:
            c.execute("UPDATE conversations SET lead_id = ? WHERE id = ?", (lead["id"], conversation_id))
        _alert_team_new_lead(key.tenant_id, lead["id"])
        cadence.enroll(key.tenant_id, lead["id"])
        track_event(key.tenant_id, "lead_created", {"lead_id": lead["id"], "conversation_id": conversation_id})
    return result


def _claim_lead_slot(conversation_id: int) -> bool:
    """One lead per conversation, even when two last messages race (double-tapped send): first UPDATE wins."""
    with connect() as c:
        return c.execute("UPDATE conversations SET lead_id = 0 WHERE id = ? AND lead_id IS NULL",
                         (conversation_id,)).rowcount == 1


@public_app.get("/v1/public/leads")
@public_app.get("/api/v1/public/leads")
def public_lead_status(client_key: str, lead_id: int) -> dict:
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")
    lead = get_lead(lead_id)
    if not lead or lead["tenant_id"] != key.tenant_id:
        raise HTTPException(status_code=404, detail="lead not found")
    return {"id": lead["id"], "status": lead["status"], "updated_at": lead["updated_at"]}


@public_app.post("/v1/public/leads")
@public_app.post("/api/v1/public/leads")
def public_lead_create(body: dict[str, Any], client_key: str, request: Request) -> dict:
    _limit(request, "lead_create", 5)
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")

    # Require minimum fields
    if not body.get("name") or not body.get("email"):
        raise HTTPException(status_code=400, detail="name and email are required")

    lead = create_lead(key.tenant_id, {
        "name": body.get("name"),
        "email": body.get("email"),
        "phone": re.sub(r"[^0-9+().\-\s#x]", "", str(body.get("phone") or ""))[:40] or None,
        "service": body.get("service") or body.get("intent"),
        "intent": body.get("intent"),
        "urgency": body.get("urgency"),
        "preferredDate": body.get("preferred_date"),
        "preferredTime": body.get("preferred_time"),
        "insurance": body.get("insurance"),
        "financing": body.get("financing"),
        "message": body.get("message"),
        "conversationSummary": body.get("message"),
        "source": body.get("source", "website_widget"),
        "pageUrl": body.get("page_url"),
        "conversationId": body.get("conversationId") or body.get("conversation_id"),
    })
    _alert_team_new_lead(key.tenant_id, lead["id"])
    cadence.enroll(key.tenant_id, lead["id"])
    track_event(key.tenant_id, "lead_created", {"lead_id": lead["id"]})
    return {"ok": True, "lead_id": lead["id"]}


def _alert_team_new_lead(tenant_id: int, lead_id: int) -> None:
    """Email the clinic team that a new request is waiting (HeyJarvis sender, background thread).

    This goes through HeyJarvis's own sender, not the clinic mailbox, so it carries no patient details at all
    (no name, contact, service or message): only that a request arrived, whether it's urgent, and a link.
    Everything else stays behind the front desk login."""
    import threading

    def run() -> None:
        from saas import login_codes
        from saas.repositories import create_notification, get_lead, get_tenant
        try:
            lead, tenant = get_lead(lead_id), get_tenant(tenant_id)
            with connect() as c:
                team = [r["email"] for r in rows(c, "SELECT email FROM users WHERE tenant_id = ? AND role IN "
                                                    "('owner', 'admin', 'member', 'agent')", tenant_id)]
            if not lead or not tenant or not team:
                return
            urgent = lead.get("intent") == "emergency"
            subject = f"{'URGENT: ' if urgent else ''}New patient request"
            body = ("A new patient request just came in from your website.\n\n"
                    f"{'It was flagged as an emergency. ' if urgent else ''}"
                    f"A reply is drafted and waiting for your approval in the front desk:\n"
                    f"{settings.app_url.rstrip('/')}/frontdesk?clinic={tenant.slug}\n")
            sent = 0
            for to in team:
                try:
                    sent += bool(login_codes.send_system_email(to, subject, body, dev_note=f"New-lead alert to {to}"))
                except Exception:
                    log.exception("new-lead alert to %s failed", to)
            create_notification(tenant_id, lead_id, "email", "sent" if sent else "skipped",
                                {"to": team, "subject": subject})
        except Exception:
            log.exception("new-lead alert failed for tenant %s lead %s", tenant_id, lead_id)

    if os.environ.get("CONCIERGE_SYNC_ALERTS") == "1":  # tests
        run()
    else:
        threading.Thread(target=run, daemon=True, name="new-lead-alert").start()


@public_app.get("/widget.js")
@public_app.get("/api/widget.js")
def public_widget() -> FileResponse:
    return FileResponse(STATIC / "widget.js", media_type="application/javascript")


# ── Front Desk Routes ──────────────────────────────────────────────────────────

frontdesk_app = FastAPI(title="HeyJarvis Front Desk", version="1.0.0")


async def _fd_auth(request: Request) -> dict:
    """Front desk access requires a staff login (JWT).

    The widget's public client key is embedded in customer websites, so it must
    never grant access to leads or conversations.
    """
    token = await oauth2(request)
    if not token:
        raise HTTPException(status_code=401, detail="authentication required")
    cu = await get_current(token)
    return {"tenant_id": cu.user.tenant_id, "user_id": cu.user.id, "auth_type": "jwt"}


@frontdesk_app.get("/dashboard")
async def fd_dashboard(request: Request):
    auth = await _fd_auth(request)
    return get_frontdesk_dashboard(auth["tenant_id"])


@frontdesk_app.get("/dashboard/{tenant_id}")
async def fd_dashboard_tenant(request: Request, tenant_id: int):
    auth = await _fd_auth(request)
    if auth["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="wrong tenant")
    return get_frontdesk_dashboard(tenant_id)


@frontdesk_app.get("/conversations")
async def fd_list_conversations(request: Request, lead_id: int | None = None, status: str | None = None):
    auth = await _fd_auth(request)
    with connect() as c:
        if lead_id:
            convs = rows(c, "SELECT * FROM conversations WHERE id = (SELECT conversation_id FROM leads WHERE id = ? AND tenant_id = ?)", lead_id, auth["tenant_id"])
        else:
            if status:
                convs = rows(c, "SELECT * FROM conversations WHERE tenant_id = ? AND status = ? ORDER BY updated_at DESC LIMIT 100", auth["tenant_id"], status)
            else:
                convs = rows(c, "SELECT * FROM conversations WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT 100", auth["tenant_id"])
    return convs


@frontdesk_app.get("/conversations/{conversation_id}")
async def fd_get_conversation(request: Request, conversation_id: int):
    auth = await _fd_auth(request)
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if conv["tenant_id"] != auth["tenant_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    with connect() as c:
        msgs = rows(c, "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC", (conversation_id,))
    result = dict(conv)
    result["messages"] = msgs
    return result


@frontdesk_app.get("/conversations/{conversation_id}/messages")
async def fd_get_messages(request: Request, conversation_id: int):
    auth = await _fd_auth(request)
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if conv["tenant_id"] != auth["tenant_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    with connect() as c:
        msgs = rows(c, "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC", (conversation_id,))
    # Wrap in {messages: []} to match frontend expectation
    return {"messages": msgs}


@frontdesk_app.get("/leads")
async def fd_list_leads(
    request: Request,
    status: str | None = None,
    intent: str | None = None,
    urgency: str | None = None,
    limit: int = 100,
):
    auth = await _fd_auth(request)
    tid = auth["tenant_id"]
    sql = "SELECT * FROM leads WHERE tenant_id = ?"
    args: list[Any] = [tid]
    if status:
        sql += " AND status = ?"
        args.append(status)
    if intent:
        sql += " AND intent = ?"
        args.append(intent)
    if urgency:
        sql += " AND urgency = ?"
        args.append(urgency)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with connect() as c:
        lead_list = rows(c, sql, tuple(args))
        intent_rows = rows(c,
            "SELECT DISTINCT intent FROM leads WHERE tenant_id = ? AND intent IS NOT NULL ORDER BY intent",
            (tid,),
        )
    intents = [r["intent"] for r in intent_rows if r["intent"]]
    return {"leads": lead_list, "intents": intents}


@frontdesk_app.get("/leads/{lead_id}")
async def fd_get_lead(request: Request, lead_id: int):
    auth = await _fd_auth(request)
    lead = get_fd_lead_detail(auth["tenant_id"], lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@frontdesk_app.patch("/leads/{lead_id}/status")
async def fd_update_lead_status(request: Request, lead_id: int, body: dict[str, Any]):
    auth = await _fd_auth(request)
    lead = get_lead(lead_id)
    if not lead or lead["tenant_id"] != auth["tenant_id"]:
        raise HTTPException(status_code=404, detail="lead not found")
    new_status = body.get("status")
    if not new_status:
        raise HTTPException(status_code=422, detail="status required")
    valid_statuses = {"new", "contacted", "scheduled", "completed", "archived", "emergency", "appointment_request",
                      "qualified", "booked", "closed", "spam"}
    if new_status not in valid_statuses:
        raise HTTPException(status_code=422, detail=f"invalid status: {new_status}")
    with connect() as c:
        c.execute("UPDATE leads SET status = ?, updated_at = ? WHERE id = ?", (new_status, now_iso(), lead_id))
    cadence.stop_for_status(auth["tenant_id"], lead_id, new_status)
    # Return the full updated lead so the frontend can update its state
    updated = get_lead(lead_id)
    return updated


@frontdesk_app.post("/leads/{lead_id}/reply")
async def fd_reply_lead(request: Request, lead_id: int, body: dict[str, Any]):
    """Email the patient now from the clinic mailbox (typed by the desk, no AI)."""
    auth = await _fd_auth(request)
    lead = get_lead(lead_id)
    if not lead or lead["tenant_id"] != auth["tenant_id"]:
        raise HTTPException(status_code=404, detail="lead not found")
    text = (body.get("body") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="body is required")
    draft = create_ai_draft(auth["tenant_id"], lead_id=lead_id, conversation_id=lead.get("conversation_id"),
                            subject=body.get("subject") or "Re: your appointment request", body=text)
    return await _send_draft_or_http(auth["tenant_id"], draft["id"], {})


async def _notify_desk(request: Request, lead_id: int, intent: str) -> str:
    """Re-send the new-lead alert. 409 in production with no clinic mailbox (never written to disk instead).

    With a front desk address set, the full notification goes there from the clinic mailbox ("front_desk").
    Without one, the team gets the PHI-free new-lead alert again from the HeyJarvis sender ("team", in the
    background), never the patient's details mailed to a missing address."""
    auth = await _fd_auth(request)
    lead = get_lead(lead_id)
    if not lead or lead["tenant_id"] != auth["tenant_id"]:
        raise HTTPException(status_code=404, detail="lead not found")
    from saas.emailer import NoFrontDeskAddress, send_lead_notification
    try:
        result = await run_in_threadpool(send_lead_notification, auth["tenant_id"], lead_id, intent)
    except MailboxNotConnected as e:
        raise HTTPException(status_code=409, detail=str(e))
    except NoFrontDeskAddress:
        await run_in_threadpool(_alert_team_new_lead, auth["tenant_id"], lead_id)
        return "team"
    if not result.ok:
        raise HTTPException(status_code=502, detail=f"Could not send: {result.error}")
    return "front_desk"


@frontdesk_app.post("/leads/{lead_id}/retry")
@frontdesk_app.post("/leads/{lead_id}/retry-notify")  # alias used by frontend
async def fd_retry_lead(request: Request, lead_id: int):
    notified = await _notify_desk(request, lead_id, "retry")
    return {"ok": True, "status": "queued", "notified": notified}


@frontdesk_app.post("/leads/{lead_id}/resend")
@frontdesk_app.post("/leads/{lead_id}/resend-email")  # alias used by frontend
async def fd_resend_lead(request: Request, lead_id: int):
    notified = await _notify_desk(request, lead_id, "resend")
    return {"ok": True, "status": "sent" if notified == "front_desk" else "queued", "notified": notified}


@frontdesk_app.get("/notes")
async def fd_list_notes(request: Request, lead_id: int | None = None):
    auth = await _fd_auth(request)
    note_list = get_frontdesk_notes(auth["tenant_id"], lead_id=lead_id)
    # Wrap in {notes: []} to match frontend expectation
    return {"notes": note_list}


@frontdesk_app.post("/notes")
async def fd_create_note(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    if not (body.get("note") or "").strip():
        raise HTTPException(status_code=422, detail="note is required")
    _fd_lead_owned(body.get("lead_id"), auth["tenant_id"])
    note = create_frontdesk_note(
        auth["tenant_id"],
        note=body.get("note", "").strip(),
        lead_id=body.get("lead_id"),
        conversation_id=body.get("conversation_id"),
        created_by=auth.get("user_id"),
    )
    from starlette.responses import JSONResponse
    return JSONResponse(content=note, status_code=201)


@frontdesk_app.get("/tasks")
async def fd_list_tasks(request: Request, status: str | None = None, lead_id: int | None = None):
    auth = await _fd_auth(request)
    tid = auth["tenant_id"]
    with connect() as c:
        sql = "SELECT * FROM frontdesk_tasks WHERE tenant_id = ?"
        params: list[Any] = [tid]
        if lead_id is not None:
            sql += " AND lead_id = ?"
            params.append(lead_id)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += (
            " ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,"
            " due_at IS NOT NULL DESC, created_at DESC LIMIT 100"
        )
        task_list = rows(c, sql, tuple(params))
    # Wrap in {tasks: []} to match frontend expectation
    return {"tasks": task_list}


@frontdesk_app.post("/tasks")
async def fd_create_task(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    if not (body.get("title") or "").strip():
        raise HTTPException(status_code=422, detail="title is required")
    _fd_lead_owned(body.get("lead_id"), auth["tenant_id"])
    task = create_frontdesk_task(
        auth["tenant_id"],
        title=body.get("title", "").strip(),
        priority=body.get("priority", "medium"),
        lead_id=body.get("lead_id"),
        description=body.get("description"),
        due_at=body.get("due_at"),
        created_by=auth.get("user_id"),
    )
    from starlette.responses import JSONResponse
    return JSONResponse(content=task, status_code=201)


@frontdesk_app.post("/tasks/{task_id}/complete")
async def fd_complete_task(request: Request, task_id: int):
    auth = await _fd_auth(request)
    task = complete_frontdesk_task(task_id, auth["tenant_id"])
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@frontdesk_app.get("/drafts")
async def fd_list_drafts(request: Request, lead_id: int | None = None, status: str | None = None):
    auth = await _fd_auth(request)
    drafts = get_ai_drafts(auth["tenant_id"], lead_id=lead_id, status=status, limit=200)
    names = {l["id"]: l["name"] for l in list_leads(auth["tenant_id"], limit=1000)}
    for d in drafts:
        d["lead_name"] = names.get(d.get("lead_id"))
    return drafts


@frontdesk_app.post("/drafts")
async def fd_create_draft(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    _fd_lead_owned(body.get("lead_id"), auth["tenant_id"])
    draft = create_ai_draft(
        auth["tenant_id"],
        lead_id=body.get("lead_id"),
        conversation_id=body.get("conversation_id"),
        subject=body.get("subject", ""),
        body=body.get("body", ""),
    )
    from starlette.responses import JSONResponse
    return JSONResponse(content=draft, status_code=201)


async def _ai(fn, *args, **kwargs):
    """AI calls take seconds: run them off the event loop so one request can't freeze every clinic."""
    return await run_in_threadpool(lambda: fn(*args, **kwargs))


async def _send_draft_or_http(tenant_id: int, draft_id: int, edits: dict[str, Any]) -> dict:
    try:
        return await run_in_threadpool(lambda: mailbox.send_draft(
            tenant_id, draft_id, subject=edits.get("subject"), body=edits.get("body"), to=edits.get("to")))
    except LookupError:
        raise HTTPException(status_code=404, detail="draft not found")
    except mailbox.MailboxError as e:
        raise HTTPException(status_code=409, detail=str(e))


@frontdesk_app.post("/drafts/{draft_id}/send")
async def fd_send_draft(request: Request, draft_id: int, body: dict[str, Any] = Body(default_factory=dict)):
    """Approve and send a draft to the patient from the clinic mailbox. Optional edits: subject, body, to."""
    auth = await _fd_auth(request)
    return await _send_draft_or_http(auth["tenant_id"], draft_id, body or {})


@frontdesk_app.patch("/drafts/{draft_id}")
async def fd_edit_draft(request: Request, draft_id: int, body: dict[str, Any]):
    auth = await _fd_auth(request)
    fields = {k: body[k] for k in ("subject", "body", "to_email") if k in body}
    with connect() as c:
        draft = row(c, "SELECT * FROM ai_drafts WHERE id = ? AND tenant_id = ?", draft_id, auth["tenant_id"])
        if not draft or draft["status"] != "pending":
            raise HTTPException(status_code=404, detail="pending draft not found")
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            c.execute(f"UPDATE ai_drafts SET {sets}, updated_at = ? WHERE id = ?", [*fields.values(), now_iso(), draft_id])
        return row(c, "SELECT * FROM ai_drafts WHERE id = ?", draft_id)


@frontdesk_app.post("/drafts/{draft_id}/discard")
async def fd_discard_draft(request: Request, draft_id: int):
    """Throw a draft away. A discarded cadence step counts as skipped."""
    auth = await _fd_auth(request)
    with connect() as c:
        draft = row(c, "SELECT * FROM ai_drafts WHERE id = ? AND tenant_id = ?", draft_id, auth["tenant_id"])
        if not draft or draft["status"] != "pending":
            raise HTTPException(status_code=404, detail="pending draft not found")
        c.execute("UPDATE ai_drafts SET status = 'discarded', updated_at = ? WHERE id = ?", (now_iso(), draft_id))
    if draft.get("lead_id"):
        cadence.on_discard(auth["tenant_id"], draft["lead_id"], draft.get("cadence_step"))
    return {"ok": True}


# ── Email thread, mailbox, cadence ───────────────────────────────────────────

@frontdesk_app.get("/leads/{lead_id}/emails")
async def fd_lead_emails(request: Request, lead_id: int):
    """Everything email for one patient: thread, pending drafts, cadence position."""
    auth = await _fd_auth(request)
    _fd_lead_owned(lead_id, auth["tenant_id"])
    return {
        "messages": mailbox.lead_thread(auth["tenant_id"], lead_id),
        "drafts": get_ai_drafts(auth["tenant_id"], lead_id=lead_id, status="pending"),
        "cadence": cadence.get_enrollment(auth["tenant_id"], lead_id),
    }


@frontdesk_app.post("/leads/{lead_id}/cadence")
async def fd_lead_cadence(request: Request, lead_id: int, body: dict[str, Any]):
    """action: enroll | restart | pause | resume | stop"""
    auth = await _fd_auth(request)
    _fd_lead_owned(lead_id, auth["tenant_id"])
    action = body.get("action")
    if action in ("enroll", "restart"):
        enr = cadence.enroll(auth["tenant_id"], lead_id, restart=action == "restart")
        if not enr:
            raise HTTPException(status_code=409, detail="cannot enroll: lead has no email or cadence is disabled")
        return enr
    states = {"pause": "paused", "resume": "active", "stop": "stopped"}
    if action not in states:
        raise HTTPException(status_code=422, detail="action must be enroll, restart, pause, resume or stop")
    if not cadence.get_enrollment(auth["tenant_id"], lead_id):
        raise HTTPException(status_code=404, detail="lead is not in the cadence")
    return cadence.set_state(auth["tenant_id"], lead_id, states[action], reason=f"{action} by front desk")


@frontdesk_app.get("/cadence")
async def fd_get_cadence(request: Request):
    auth = await _fd_auth(request)
    return {"cadence": cadence.get_cadence(auth["tenant_id"]), "reply_types": cadence.REPLY_INTENTS,
            "lead_statuses": sorted(cadence.LEAD_STATUSES)}


@frontdesk_app.put("/cadence")
async def fd_put_cadence(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    _fd_require_manager(auth)
    try:
        return {"cadence": cadence.save_cadence(auth["tenant_id"], body)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@frontdesk_app.post("/cadence/run")
async def fd_run_cadence(request: Request):
    """Create any follow-up drafts that are due now (the background scheduler also does this)."""
    auth = await _fd_auth(request)
    ids = await run_in_threadpool(cadence.run_due, auth["tenant_id"])
    return {"drafts_created": len(ids), "draft_ids": ids}


@frontdesk_app.get("/mailbox")
async def fd_mailbox_status(request: Request):
    auth = await _fd_auth(request)
    return mailbox.mailbox_status(auth["tenant_id"])


@frontdesk_app.put("/mailbox")
async def fd_connect_mailbox(request: Request, body: dict[str, Any]):
    """Connect the clinic mailbox: Gmail (app password), Einstein Mail, Microsoft 365, or any IMAP/SMTP server."""
    auth = await _fd_auth(request)
    _fd_require_manager(auth)
    provider = body.get("provider") or "gmail"
    password = (body.get("password") or body.get("app_password") or "").strip()
    try:
        status_ = await run_in_threadpool(
            lambda: mailbox.connect_mailbox(
                auth["tenant_id"], provider, body.get("address") or "", password,
                username=(body.get("username") or "").strip() or None,
                smtp_host=body.get("smtp_host"), smtp_port=body.get("smtp_port"),
                imap_host=body.get("imap_host"), imap_port=body.get("imap_port"),
                from_name=body.get("from_name")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    check = await run_in_threadpool(mailbox.test_mailbox, auth["tenant_id"])
    from saas.repositories import audit
    audit(auth["tenant_id"], auth.get("user_id"), "mailbox_connected",
          {"address": status_.get("address"), "provider": provider, "ok": check["ok"]})
    return {**mailbox.mailbox_status(auth["tenant_id"]), "test": check}


@frontdesk_app.get("/clinic")
async def fd_get_clinic(request: Request):
    """Clinic name, phone, address, hours and website (used in patient emails and the chat)."""
    auth = await _fd_auth(request)
    from saas.repositories import get_clinic_profile
    return get_clinic_profile(auth["tenant_id"])


@frontdesk_app.put("/clinic")
async def fd_put_clinic(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    _fd_require_manager(auth)
    from saas.repositories import audit, save_clinic_profile
    if "name" in body and not str(body.get("name") or "").strip():
        raise HTTPException(status_code=422, detail="Clinic name can't be empty")
    profile = save_clinic_profile(auth["tenant_id"], body)
    audit(auth["tenant_id"], auth.get("user_id"), "clinic_profile_updated", {})
    return profile


TEAM_ROLES = {"admin": "Can change settings", "member": "Replies to patients"}


@frontdesk_app.get("/team")
async def fd_list_team(request: Request):
    auth = await _fd_auth(request)
    with connect() as c:
        people = rows(c, "SELECT id, email, display_name, role, created_at FROM users WHERE tenant_id = ? "
                         "AND role != 'removed' ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, "
                         "created_at", auth["tenant_id"])
    for p in people:
        p["you"] = p["id"] == auth.get("user_id")
    return {"team": people, "roles": TEAM_ROLES}


@frontdesk_app.post("/team")
async def fd_add_teammate(request: Request, body: dict[str, Any]):
    """Add a front desk teammate. They sign in with a code emailed to them (no password)."""
    auth = await _fd_auth(request)
    _fd_require_manager(auth)
    from saas.repositories import audit, create_user, get_tenant, get_user, get_user_by_email
    email = (body.get("email") or "").strip().lower()
    name = (body.get("name") or "").strip()[:80] or None
    role = body.get("role") or "member"
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    if role not in TEAM_ROLES:
        raise HTTPException(status_code=422, detail="Role must be admin or member")
    me = get_user(auth["user_id"])
    if role == "admin" and me.role != "owner":
        raise HTTPException(status_code=403, detail="Only the clinic owner can add admins")
    existing = get_user_by_email(auth["tenant_id"], email)
    if existing and existing.role != "removed":
        raise HTTPException(status_code=409, detail="That person is already on the team")
    if existing:  # re-adding someone who was removed
        with connect() as c:
            c.execute("UPDATE users SET role = ?, display_name = COALESCE(?, display_name), updated_at = ? WHERE id = ?",
                      (role, name, now_iso(), existing.id))
            c.execute("INSERT OR IGNORE INTO memberships (tenant_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
                      (auth["tenant_id"], existing.id, role, now_iso()))
        user_id = existing.id
    else:
        user_id = create_user(auth["tenant_id"], email, display_name=name, password=None, role=role).id
    tenant = get_tenant(auth["tenant_id"])
    invited = await run_in_threadpool(_send_invite, email, tenant)
    audit(auth["tenant_id"], auth.get("user_id"), "teammate_added", {"email": email, "role": role})
    return {"id": user_id, "email": email, "role": role, "invite_sent": invited}


def _send_invite(email: str, tenant: Any) -> bool:
    from saas import login_codes
    url = f"{settings.app_url.rstrip('/')}/frontdesk?clinic={tenant.slug}"
    try:
        return login_codes.send_system_email(
            email, f"You've been added to the {tenant.name} front desk",
            f"Hi,\n\nYou now have access to the {tenant.name} front desk on HeyJarvis, where patient requests "
            f"from the website are answered.\n\nSign in here: {url}\nClinic ID: {tenant.slug}\n\n"
            "Use this email address. We'll email you a 6-digit code each time you sign in, so there's no password "
            "to remember.\n",
            dev_note=f"Invite for {email}: {url}")
    except Exception:
        log.exception("invite email failed for %s", email)
        return False


@frontdesk_app.delete("/team/{user_id}")
async def fd_remove_teammate(request: Request, user_id: int):
    auth = await _fd_auth(request)
    _fd_require_manager(auth)
    from saas.repositories import audit, get_user
    target = get_user(user_id)
    if not target or target.tenant_id != auth["tenant_id"] or target.role == "removed":
        raise HTTPException(status_code=404, detail="Teammate not found")
    if target.id == auth.get("user_id"):
        raise HTTPException(status_code=409, detail="You can't remove yourself")
    if target.role == "owner":
        raise HTTPException(status_code=403, detail="The clinic owner can't be removed here")
    if target.role == "admin" and get_user(auth["user_id"]).role != "owner":
        raise HTTPException(status_code=403, detail="Only the clinic owner can remove admins")
    with connect() as c:
        c.execute("UPDATE users SET role = 'removed', updated_at = ? WHERE id = ?", (now_iso(), user_id))
        c.execute("DELETE FROM memberships WHERE user_id = ?", (user_id,))
        c.execute("UPDATE login_codes SET used_at = ? WHERE user_id = ? AND used_at IS NULL", (now_iso(), user_id))
    audit(auth["tenant_id"], auth.get("user_id"), "teammate_removed", {"email": target.email})
    return {"ok": True}


@frontdesk_app.post("/mailbox/test-send")
async def fd_mailbox_test_send(request: Request):
    """Send a test email from the clinic mailbox to itself."""
    auth = await _fd_auth(request)
    _fd_require_manager(auth)
    try:
        return await run_in_threadpool(mailbox.send_test_email, auth["tenant_id"])
    except mailbox.MailboxError as e:
        raise HTTPException(status_code=409, detail=str(e))


@frontdesk_app.post("/mailbox/google/start")
async def fd_google_start(request: Request, body: dict[str, Any] = Body(default_factory=dict)):
    """Returns Google's consent URL; the browser goes there and comes back to /oauth/google/callback."""
    auth = await _fd_auth(request)
    _fd_require_manager(auth)
    import secrets as _secrets

    from saas import google_oauth
    nonce = _secrets.token_urlsafe(16)
    try:
        url = google_oauth.start_url(auth["tenant_id"], auth["user_id"], (body or {}).get("address"),
                                     (body or {}).get("from_name"), nonce=nonce)
    except google_oauth.OAuthError as e:
        raise HTTPException(status_code=409, detail=str(e))
    from starlette.responses import JSONResponse
    resp = JSONResponse({"url": url})
    resp.set_cookie(google_oauth.STATE_COOKIE, nonce, max_age=600, httponly=True, samesite="lax",
                    secure=settings.is_production, path="/oauth/google")
    return resp


@frontdesk_app.delete("/mailbox")
async def fd_disconnect_mailbox(request: Request):
    auth = await _fd_auth(request)
    _fd_require_manager(auth)
    from saas.repositories import audit
    audit(auth["tenant_id"], auth.get("user_id"), "mailbox_disconnected", {})
    return mailbox.disconnect(auth["tenant_id"])


@frontdesk_app.get("/inbox")
async def fd_inbox(request: Request):
    """Every open patient request with what the front desk needs to sort it:
    pending reply draft, last email direction/time, and follow-up status."""
    auth = await _fd_auth(request)
    tid = auth["tenant_id"]
    with connect() as c:
        leads = rows(c, """
            SELECT l.*,
              (SELECT direction FROM email_messages e WHERE e.tenant_id = l.tenant_id AND e.lead_id = l.id
                 ORDER BY e.sent_at DESC, e.id DESC LIMIT 1) AS last_direction,
              (SELECT sent_at FROM email_messages e WHERE e.tenant_id = l.tenant_id AND e.lead_id = l.id
                 ORDER BY e.sent_at DESC, e.id DESC LIMIT 1) AS last_email_at,
              (SELECT status FROM cadence_enrollments ce WHERE ce.lead_id = l.id) AS followup_status
            FROM leads l WHERE l.tenant_id = ? AND l.status NOT IN ('spam', 'archived', 'closed')
            ORDER BY l.created_at DESC LIMIT 300""", tid)
        drafts = rows(c, "SELECT * FROM ai_drafts WHERE tenant_id = ? AND status = 'pending' ORDER BY id DESC", tid)
    first = {}
    for d in drafts:
        first.setdefault(d["lead_id"], d)
    for l in leads:
        l["draft"] = first.get(l["id"])
    return leads


@frontdesk_app.post("/demo/leads/{lead_id}/reply")
async def fd_demo_reply(request: Request, lead_id: int, body: dict[str, Any]):
    """Demo mode: simulate the patient answering by email."""
    auth = await _fd_auth(request)
    _fd_lead_owned(lead_id, auth["tenant_id"])
    text = (body.get("body") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="body is required")
    try:
        return await run_in_threadpool(mailbox.simulate_reply, auth["tenant_id"], lead_id, text)
    except mailbox.MailboxError as e:
        raise HTTPException(status_code=409, detail=str(e))


@frontdesk_app.post("/demo/fast-forward")
async def fd_demo_fast_forward(request: Request, body: dict[str, Any] = Body(default_factory=dict)):
    """Demo mode: pretend time passed so the next follow-ups come due."""
    auth = await _fd_auth(request)
    if not mailbox.demo_mode(auth["tenant_id"]):
        raise HTTPException(status_code=409, detail="Only available in demo mode.")
    hours = float((body or {}).get("hours", 24))
    ids = await run_in_threadpool(cadence.fast_forward, auth["tenant_id"], hours)
    return {"drafts_created": len(ids)}


@frontdesk_app.post("/mailbox/sync")
async def fd_sync_mailbox(request: Request):
    """Pull patient replies now (the background scheduler also does this every few minutes)."""
    auth = await _fd_auth(request)
    try:
        stats = await run_in_threadpool(mailbox.sync_mailbox, auth["tenant_id"])
    except mailbox.MailboxError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return stats


def _fd_require_manager(auth: dict) -> None:
    from saas.repositories import get_user
    user = get_user(auth["user_id"]) if auth.get("user_id") else None
    if not user or user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="only owners and admins can change this")


# ── AI Endpoints ──────────────────────────────────────────────────────────────

def _fd_lead_owned(lead_id: Any, tenant_id: int) -> None:
    """Reject notes/tasks/drafts that point at another tenant's lead."""
    if lead_id in (None, ""):
        return
    lead = get_lead(int(lead_id))
    if not lead or lead["tenant_id"] != tenant_id:
        raise HTTPException(status_code=404, detail="lead not found")


def _lead_context(lead_id: int | None, tenant_id: int) -> dict[str, Any]:
    if not lead_id:
        return {}
    lead = get_lead(lead_id)
    if not lead or lead["tenant_id"] != tenant_id:
        raise HTTPException(status_code=404, detail="lead not found")
    conv_text = ""
    cid = lead.get("conversation_id")
    if cid:
        with connect() as c:
            msgs = rows(c, "SELECT role, body FROM messages WHERE conversation_id = ? ORDER BY id ASC", (cid,))
            conv_text = "\n".join(
                f"{'Patient' if m['role'] == 'user' else 'Concierge'}: {m['body']}"
                for m in msgs
            )
    if not conv_text:
        conv_text = lead.get("message", "") or ""
    return {
        "lead": lead,
        "conv_text": conv_text,
    }


@frontdesk_app.post("/ai/draft")
async def fd_ai_draft(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    lead_id = body.get("lead_id")
    instruction = body.get("instruction", "")
    ctx = _lead_context(lead_id, auth["tenant_id"])
    lead = ctx.get("lead") or {}
    history = cadence._history(auth["tenant_id"], lead) if lead else ctx.get("conv_text", "")
    result = await _ai(_ai_engine.draft_reply, history, cadence._patient(lead) if lead else {},
                                    cadence._practice(auth["tenant_id"]), instruction=instruction)
    subject = result.get("subject") or "Re: " + (lead.get("service") or "your inquiry")
    draft = create_ai_draft(auth["tenant_id"], lead_id=lead_id, conversation_id=lead.get("conversation_id"),
                            subject=subject, body=result.get("body", ""), html_body=None)
    return {"draft_id": draft["id"], "subject": subject, "body": result.get("body", ""),
            "internal_note": result.get("internal_note"), "provider": result.get("provider")}


@frontdesk_app.post("/ai/summarize")
async def fd_ai_summarize(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    lead_id = body.get("lead_id")
    ctx = _lead_context(lead_id, auth["tenant_id"])
    result = await _ai(_ai_engine.summarize_conversation, ctx.get("conv_text", ""))
    return result


@frontdesk_app.post("/ai/next-action")
async def fd_ai_next_action(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    lead_id = body.get("lead_id")
    conversation_state = body.get("conversation_state", "open")
    ctx = _lead_context(lead_id, auth["tenant_id"])
    result = await _ai(_ai_engine.next_best_action, ctx.get("conv_text", ""), ctx.get("lead") or {}, conversation_state)
    return result


@frontdesk_app.post("/ai/follow-up")
async def fd_ai_followup(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    lead_id = body.get("lead_id")
    hours = body.get("hours", 24)
    ctx = _lead_context(lead_id, auth["tenant_id"])
    result = await _ai(_ai_engine.generate_follow_up, ctx.get("lead") or {}, hours_passed=hours)
    subject = result.get("subject", "Following up on your inquiry")
    draft = create_ai_draft(auth["tenant_id"], lead_id=lead_id,
                             subject=subject, body=result.get("body", ""))
    return {"draft_id": draft["id"], "subject": subject, "body": result.get("body", ""),
            "tokens_used": result.get("tokens_used", 0)}


@frontdesk_app.post("/ai/confirm")
async def fd_ai_confirm(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    lead_id = body.get("lead_id")
    appointment_time = body.get("appointment_time", "")
    ctx = _lead_context(lead_id, auth["tenant_id"])
    result = await _ai(_ai_engine.generate_confirmation, ctx.get("lead") or {}, appointment_time)
    subject = result.get("subject", "Appointment Confirmation")
    draft = create_ai_draft(auth["tenant_id"], lead_id=lead_id,
                             subject=subject, body=result.get("body", ""))
    return {"draft_id": draft["id"], "subject": subject, "body": result.get("body", ""),
            "tokens_used": result.get("tokens_used", 0)}


@frontdesk_app.post("/ai/reschedule")
async def fd_ai_reschedule(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    lead_id = body.get("lead_id")
    new_time = body.get("new_time", "")
    reason = body.get("reason", "")
    ctx = _lead_context(lead_id, auth["tenant_id"])
    result = await _ai(_ai_engine.generate_reschedule, ctx.get("lead") or {}, new_time, reason=reason)
    subject = result.get("subject", "Rescheduling Your Appointment")
    draft = create_ai_draft(auth["tenant_id"], lead_id=lead_id,
                             subject=subject, body=result.get("body", ""))
    return {"draft_id": draft["id"], "subject": subject, "body": result.get("body", ""),
            "tokens_used": result.get("tokens_used", 0)}


@frontdesk_app.post("/ai/shorten")
async def fd_ai_shorten(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    return {"body": await run_in_threadpool(_ai_engine.rewrite_text, text, "shorten")}


@frontdesk_app.post("/ai/warmer")
async def fd_ai_warmer(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    return {"body": await run_in_threadpool(_ai_engine.rewrite_text, text, "warmer")}


@frontdesk_app.post("/ai/classify")
async def fd_ai_classify(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    lead_id = body.get("lead_id")
    ctx = _lead_context(lead_id, auth["tenant_id"])
    lead = ctx.get("lead") or {}
    message = lead.get("message", "")
    result = await _ai(_ai_engine.classify_message, message, existing_fields={
        "intent": lead.get("intent", ""),
        "urgency": lead.get("urgency", ""),
        "service": lead.get("service", ""),
    })
    if lead_id and result:
        updates = {k: v for k, v in result.items()
                   if k in {"intent", "urgency", "service", "summary"}}
        if updates:
            repo_update_lead(lead_id, **updates)
    return result


@frontdesk_app.post("/ai/parse-time")
async def fd_ai_parse_time(request: Request, body: dict[str, Any]):
    auth = await _fd_auth(request)
    instruction = body.get("instruction", "")
    result = await _ai(_ai_engine.parse_time_instruction, instruction)
    return result


@frontdesk_app.post("/ai/action")
async def fd_ai_action(request: Request, body: dict[str, Any]):
    """Unified AI action endpoint used by the React front desk app.

    Actions: draft, summarize, next-action, follow-up, confirm, classify, shorten, warmer
    """
    auth = await _fd_auth(request)
    action = body.get("action", "")
    lead_id = body.get("lead_id")
    instruction = body.get("instruction", "")
    ctx = _lead_context(lead_id, tenant_id=auth["tenant_id"])
    lead = ctx.get("lead") or {}
    conv_text = ctx.get("conv_text", "")

    if action == "draft":
        history = cadence._history(auth["tenant_id"], lead) if lead else conv_text
        result = await _ai(_ai_engine.draft_reply, history, cadence._patient(lead) if lead else {},
                                        cadence._practice(auth["tenant_id"]), instruction=instruction)
        return {"result": result.get("body", ""), "model": result.get("provider", "unknown")}
    elif action == "summarize":
        result = await _ai(_ai_engine.summarize_conversation, conv_text)
        return {"result": result.get("summary", "")}
    elif action == "next-action" or action == "next_action":
        result = await _ai(_ai_engine.next_best_action, conv_text, lead, "open")
        return {"result": result.get("action", "") or result.get("recommendation", "")}
    elif action == "follow-up" or action == "follow_up":
        result = await _ai(_ai_engine.generate_follow_up, lead, hours_passed=24)
        return {"result": result.get("body", "")}
    elif action == "confirm":
        result = await _ai(_ai_engine.generate_confirmation, lead, instruction or "")
        return {"result": result.get("body", "")}
    elif action == "classify":
        result = await _ai(_ai_engine.classify_message, lead.get("message", ""), existing_fields={
            "intent": lead.get("intent", ""), "urgency": lead.get("urgency", ""), "service": lead.get("service", ""),
        })
        if lead_id and result:
            updates = {k: v for k, v in result.items() if k in {"intent", "urgency", "service"}}
            if updates:
                repo_update_lead(lead_id, **updates)
        return {"result": f"Classified: intent={result.get('intent','?')}, urgency={result.get('urgency','?')}"}
    elif action in ("shorten", "warmer"):
        text = instruction or lead.get("message", "") or conv_text
        return {"result": await run_in_threadpool(_ai_engine.rewrite_text, text, action)}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


# ── Search ──────────────────────────────────────────────────────────────────

@frontdesk_app.get("/search")
async def fd_search(request: Request, q: str = ""):
    auth = await _fd_auth(request)
    if not q or len(q) < 2:
        return {"leads": [], "conversations": [], "notes": []}
    tid = auth["tenant_id"]
    like = f"%{q}%"
    with connect() as c:
        leads = rows(c, "SELECT * FROM leads WHERE tenant_id = ? AND (name LIKE ? OR email LIKE ? OR phone LIKE ? OR message LIKE ?) LIMIT 20",
                     tid, like, like, like, like)
        convs = rows(c, "SELECT * FROM conversations WHERE tenant_id = ? AND (summary LIKE ? OR page_url LIKE ?) LIMIT 10",
                     tid, like, like)
        notes = rows(c, "SELECT * FROM frontdesk_notes WHERE tenant_id = ? AND note LIKE ? LIMIT 10",
                     tid, like)
    return {"leads": leads, "conversations": convs, "notes": notes}


# ── Activity Log ───────────────────────────────────────────────────────────

@frontdesk_app.get("/activity")
async def fd_activity(request: Request, limit: int = 50):
    auth = await _fd_auth(request)
    with connect() as c:
        events = rows(c, "SELECT * FROM analytics_events WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
                       auth["tenant_id"], limit)
        audits = rows(c, "SELECT * FROM audit_logs WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
                       auth["tenant_id"], limit)
    return {"events": events, "audits": audits}


# ── Health ──────────────────────────────────────────────────────────────────

@frontdesk_app.get("/health")
async def fd_health() -> dict:
    return {"ok": True, "service": "frontdesk"}


# ── Admin Routes ─────────────────────────────────────────────────────────────

async def _enforce_tenant_scope(request: Request) -> None:
    """Every /tenants/{tenant_id}/... route is only usable by that tenant's own users."""
    tid = request.path_params.get("tenant_id")
    if tid is None:
        return
    token = await oauth2(request)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    _own(await get_current(token), tid)


admin_app = FastAPI(title="HeyJarvis Admin", version="1.0.0", dependencies=[Depends(_enforce_tenant_scope)])


@admin_app.post("/auth/login")
@admin_app.post("/auth/token")
async def admin_login(request: Request) -> TokenOut:
    _limit(request, "login", 10)
    data = await _extract_auth_payload(request)
    slug = str(data.get("tenant_slug") or "raleigh-dental-demo").strip()
    email = str(data.get("email") or data.get("username") or "").strip()
    password = str(data.get("password") or "")

    if not email or not password:
        raise HTTPException(status_code=422, detail="Email/username and password are required")

    # get_tenant_by_slug creates the demo clinic on demand outside production only.
    # Never fall back to "the only clinic": a typo'd clinic ID must not log into someone else's.
    tenant = get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")

    return login_for_token(tenant.id, OAuth2PasswordRequestForm(username=email, password=password))


def _check_tenant(cu: CurrentUser, tenant_id: int) -> None:
    if cu.user.tenant_id != tenant_id:
        with connect() as c:
            m = row(c, "SELECT 1 FROM memberships WHERE user_id = ? AND tenant_id = ?", cu.user.id, tenant_id)
        if not m:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


@admin_app.get("/auth/demo")
def admin_demo_available() -> dict:
    from saas.repositories import _demo_allowed
    return {"available": _demo_allowed()}


@admin_app.post("/auth/demo")
def admin_demo_login(request: Request) -> TokenOut:
    """One-click login to the demo clinic. Local/dev only; refused on production servers."""
    from saas.auth import _user_payload
    from saas.repositories import _demo_allowed, ensure_demo_data, get_user_by_email
    from saas.security import create_access_token
    if not _demo_allowed():
        raise HTTPException(status_code=404, detail="not found")
    tenant = ensure_demo_data()
    user = get_user_by_email(tenant.id, "admin@raleighdentistry.com")
    return TokenOut(access_token=create_access_token(subject=str(user.id), tenant_id=tenant.id), user=_user_payload(user))


@admin_app.post("/auth/code/request")
def admin_request_code(body: dict[str, Any], request: Request) -> dict:
    """Email a 6-digit login code. Same answer whether or not the account exists."""
    _limit(request, "login_code", 5)
    from saas import login_codes
    from saas.repositories import get_user_by_email
    tenant = get_tenant_by_slug((body.get("tenant_slug") or "").strip())
    email = (body.get("email") or "").strip().lower()
    user = get_user_by_email(tenant.id, email) if tenant and email else None
    if user and user.role != "removed":
        try:
            login_codes.issue(user.id, user.email, tenant.name)
        except login_codes.LoginCodeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception:
            log.exception("login code email failed")
            raise HTTPException(status_code=503, detail="Could not send the login email. Try again shortly.")
    return {"ok": True, "message": "If that account exists, a login code is on its way."}


@admin_app.post("/auth/code/verify")
def admin_verify_code(body: dict[str, Any], request: Request) -> TokenOut:
    _limit(request, "login", 10)
    from saas import login_codes
    from saas.auth import _user_payload
    from saas.repositories import get_user_by_email
    from saas.security import create_access_token
    tenant = get_tenant_by_slug((body.get("tenant_slug") or "").strip())
    user = get_user_by_email(tenant.id, (body.get("email") or "").strip().lower()) if tenant else None
    if not user or user.role == "removed" or not login_codes.verify(user.id, str(body.get("code") or "")):
        raise HTTPException(status_code=401, detail="That code is wrong or expired. Request a new one.")
    return TokenOut(access_token=create_access_token(subject=str(user.id), tenant_id=tenant.id),
                    user=_user_payload(user))


@admin_app.get("/tenants")
def admin_list_tenants(cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict[str, Any]]:
    return [t.model_dump() for t in list_tenants() if t.id == cu.user.tenant_id]


@admin_app.get("/tenants/{tenant_id}")
def admin_get_tenant(tenant_id: int, cu: CurrentUser = Depends(get_current)) -> dict:
    _check_tenant(cu, tenant_id)
    return _load_tenant(tenant_id)


@admin_app.patch("/tenants/{tenant_id}")
def admin_update_tenant(tenant_id: int, body: dict[str, Any], cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    _check_tenant(cu, tenant_id)
    from saas.repositories import update_tenant
    allowed = {"name", "enabled", "plan"}
    fields = {k: v for k, v in body.items() if k in allowed}
    update_tenant(tenant_id, **fields)
    from saas.repositories import audit
    audit(tenant_id, cu.user.id, "tenant_updated", {"fields": list(fields.keys())})
    return _load_tenant(tenant_id)


@admin_app.post("/tenants/{tenant_id}/domains")
def admin_add_domain(tenant_id: int, body: dict[str, Any], cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    _check_tenant(cu, tenant_id)
    dom = repo_add_domain(tenant_id, body.get("domain", ""))
    return dom.model_dump()


@admin_app.post("/domains/{domain_id}/verify")
def admin_verify_domain(domain_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    from saas.repositories import get_domain
    dom = get_domain(domain_id)
    _own(cu, dom.tenant_id if dom else None)
    repo_verify_domain(domain_id)
    return {"ok": True}


@admin_app.delete("/domains/{domain_id}")
def admin_remove_domain(domain_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    from saas.repositories import get_domain
    dom = get_domain(domain_id)
    _own(cu, dom.tenant_id if dom else None)
    repo_remove_domain(domain_id)
    return {"ok": True}


@admin_app.get("/tenants/{tenant_id}/domains")
def admin_list_domains(tenant_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict[str, Any]]:
    _check_tenant(cu, tenant_id)
    return [d.model_dump() for d in repo_list_domains(tenant_id)]


# ── Integration Center ──────────────────────────────────────────────────────────

@admin_app.get("/tenants/{tenant_id}/integration")
def admin_get_integration(tenant_id: int, cu: Any = Depends(get_current)) -> dict:
    if cu.user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="forbidden")
    return _load_integration(tenant_id)


@admin_app.post("/tenants/{tenant_id}/integration/domains")
def admin_add_integration_domain(tenant_id: int, body: dict[str, Any], cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    if cu.user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="forbidden")
    domain = (body.get("domain") or "").strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    if not domain:
        raise HTTPException(status_code=422, detail="domain is required")
    with connect() as c:
        existing = rows(c, "SELECT id FROM domains WHERE tenant_id = ? AND domain = ?", tenant_id, domain)
        if existing:
            raise HTTPException(status_code=409, detail="domain already added")
        did = c.execute("INSERT INTO domains (tenant_id, domain, created_at) VALUES (?, ?, ?)",
                        (tenant_id, domain, now_iso())).lastrowid
        r = row(c, "SELECT * FROM domains WHERE id = ?", (did,))
    from saas.repositories import audit
    audit(tenant_id, cu.user.id, "domain_added", {"domain": domain})
    return dict(r)


@admin_app.delete("/tenants/{tenant_id}/integration/domains/{domain_id}")
def admin_remove_integration_domain(tenant_id: int, domain_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    if cu.user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="forbidden")
    with connect() as c:
        r = row(c, "SELECT domain FROM domains WHERE id = ? AND tenant_id = ?", domain_id, tenant_id)
        if not r:
            raise HTTPException(status_code=404, detail="domain not found")
        domain = r["domain"]
        c.execute("DELETE FROM domains WHERE id = ?", (domain_id,))
    from saas.repositories import audit
    audit(tenant_id, cu.user.id, "domain_removed", {"domain": domain})
    return {"ok": True}


@admin_app.post("/tenants/{tenant_id}/integration/domains/{domain_id}/verify")
def admin_verify_integration_domain(tenant_id: int, domain_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    if cu.user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="forbidden")
    with connect() as c:
        c.execute("UPDATE domains SET verified = 1 WHERE id = ? AND tenant_id = ?", (domain_id, tenant_id))
        r = row(c, "SELECT * FROM domains WHERE id = ?", (domain_id,))
    if not r:
        raise HTTPException(status_code=404, detail="domain not found")
    from saas.repositories import audit
    audit(tenant_id, cu.user.id, "domain_verified", {"domain_id": domain_id})
    return dict(r)


@admin_app.post("/tenants/{tenant_id}/integration/regenerate-key")
def admin_regenerate_client_key(tenant_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    if cu.user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="forbidden")
    with connect() as c:
        rows_data = rows(c, "SELECT id FROM api_keys WHERE tenant_id = ? AND revoked_at IS NULL LIMIT 1", (tenant_id,))
    if rows_data:
        from saas.repositories import revoke_api_key
        revoke_api_key(rows_data[0]["id"])
    from saas.repositories import create_api_key
    new_key = create_api_key(tenant_id, label="primary", secret=__import__("secrets").token_urlsafe(24))
    from saas.repositories import audit
    audit(tenant_id, cu.user.id, "api_key_regenerated", {})
    return {"public_key": new_key.public_key, "message": "New client key generated. Update your website snippet."}


@admin_app.post("/tenants/{tenant_id}/integration/test")
def admin_test_integration(tenant_id: int, cu: Any = Depends(get_current)) -> dict:
    if cu.user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="forbidden")
    tenant = _load_tenant(tenant_id)
    public_key = _public_key(tenant_id)
    if not public_key:
        return {"status": "error", "message": "No client key found. Generate one first."}
    with connect() as c:
        domains = rows(c, "SELECT domain, verified FROM domains WHERE tenant_id = ?", (tenant_id,))
    domain_list = [d["domain"] for d in domains]
    if not domain_list:
        return {
            "status": "pending",
            "message": "No domains configured. Add your website domain to enable origin validation.",
            "domains": [],
            "client_key_configured": True,
        }
    return {
        "status": "ready",
        "message": "Integration is configured. Paste the snippet on your website.",
        "domains": domain_list,
        "domain_count": len(domain_list),
        "verified_domains": [d["domain"] for d in domains if d["verified"]],
        "client_key_configured": bool(public_key),
    }


# ── Leads Admin ──────────────────────────────────────────────────────────────

@admin_app.get("/tenants/{tenant_id}/leads")
def admin_list_leads(tenant_id: int, status: str | None = None, limit: int = 100, offset: int = 0,
                     cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict]:
    _check_tenant(cu, tenant_id)
    from saas.repositories import list_leads
    return list_leads(tenant_id, status=status, limit=limit, offset=offset)


@admin_app.get("/leads/{lead_id}")
def admin_get_lead(lead_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    lead = get_lead(lead_id)
    _own(cu, lead["tenant_id"] if lead else None)
    return lead


@admin_app.patch("/leads/{lead_id}")
def admin_update_lead(lead_id: int, body: dict[str, Any], cu: CurrentUser = Depends(require_roles("owner", "admin", "member"))) -> dict:
    existing = get_lead(lead_id)
    _own(cu, existing["tenant_id"] if existing else None)
    allowed = {"status", "name", "email", "phone", "intent", "service", "urgency",
               "preferred_date", "preferred_time", "insurance", "financing", "message"}
    fields = {k: v for k, v in body.items() if k in allowed}
    if not fields:
        raise HTTPException(status_code=400, detail="no valid fields")
    repo_update_lead(lead_id, **fields)
    if fields.get("status"):
        cadence.stop_for_status(existing["tenant_id"], lead_id, fields["status"])
    lead = get_lead(lead_id)
    return lead


# ── Conversations Admin ──────────────────────────────────────────────────────

@admin_app.get("/tenants/{tenant_id}/conversations")
def admin_list_conversations(tenant_id: int, status: str | None = None, limit: int = 100, offset: int = 0,
                              cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict]:
    _check_tenant(cu, tenant_id)
    with connect() as c:
        sql = "SELECT * FROM conversations WHERE tenant_id = ?"
        args = [tenant_id]
        if status:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        return rows(c, sql, tuple(args))


@admin_app.get("/tenants/{tenant_id}/conversations/{conversation_id}")
def admin_get_tenant_conversation(tenant_id: int, conversation_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    _check_tenant(cu, tenant_id)
    conv = get_conversation(conversation_id)
    if not conv or conv["tenant_id"] != tenant_id:
        raise HTTPException(status_code=404, detail="conversation not found")
    with connect() as c:
        msgs = rows(c, "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,))
    res = dict(conv)
    res["messages"] = msgs
    return res


@admin_app.post("/tenants/{tenant_id}/conversations")
def admin_create_conversation(tenant_id: int, body: dict = Body(default_factory=dict), cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    _check_tenant(cu, tenant_id)
    body = body or {}
    now = now_iso()
    with connect() as c:
        cur = c.execute(
            "INSERT INTO conversations (tenant_id, status, page_url, summary, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, "new", body.get("page_url", "/"), body.get("summary"), json.dumps(body), now, now),
        )
        cid = cur.lastrowid
        return rows(c, "SELECT * FROM conversations WHERE id = ?", (cid,))[0]


@admin_app.get("/conversations/{conversation_id}/messages")
def admin_get_messages(conversation_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict]:
    with connect() as c:
        conv = rows(c, "SELECT tenant_id FROM conversations WHERE id = ?", (conversation_id,))
    _own(cu, conv[0]["tenant_id"] if conv else None)
    with connect() as c:
        return rows(c, "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,))


# ── Analytics Admin ──────────────────────────────────────────────────────────

@admin_app.get("/tenants/{tenant_id}/analytics")
def admin_analytics(tenant_id: int, days: int = 7, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    _check_tenant(cu, tenant_id)
    since = _days_ago(days)
    with connect() as c:
        events = rows(c, "SELECT event, COUNT(1) as cnt FROM analytics_events "
                         "WHERE tenant_id = ? AND created_at >= ? GROUP BY event", tenant_id, since)
        conversations = rows(c, "SELECT status, COUNT(1) as cnt FROM conversations "
                                "WHERE tenant_id = ? AND created_at >= ? GROUP BY status", tenant_id, since)
        leads = rows(c, "SELECT status, COUNT(1) as cnt FROM leads "
                        "WHERE tenant_id = ? AND created_at >= ? GROUP BY status", tenant_id, since)
    return {
        "events": {e["event"]: e["cnt"] for e in events},
        "conversations": {c["status"]: c["cnt"] for c in conversations},
        "leads": {l["status"]: l["cnt"] for l in leads},
        "days": days,
    }


def _days_ago(n: int) -> str:
    from datetime import datetime, timedelta
    from saas.database import utcnow
    return (utcnow() - timedelta(days=n)).isoformat(timespec="seconds")


# ── Widget Settings Admin ────────────────────────────────────────────────────

@admin_app.get("/tenants/{tenant_id}/widget")
def admin_get_widget(tenant_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    _check_tenant(cu, tenant_id)
    with connect() as c:
        r = rows(c, "SELECT config FROM widget_settings WHERE tenant_id = ?", (tenant_id,))
    return json.loads(r[0]["config"]) if r else {}


@admin_app.put("/tenants/{tenant_id}/widget")
def admin_update_widget(tenant_id: int, body: dict[str, Any], cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    _check_tenant(cu, tenant_id)
    with connect() as c:
        existing = rows(c, "SELECT id FROM widget_settings WHERE tenant_id = ?", (tenant_id,))
        config_json = json.dumps(body)
        now = now_iso()
        if existing:
            c.execute("UPDATE widget_settings SET config = ?, updated_at = ? WHERE tenant_id = ?",
                      (config_json, now, tenant_id))
        else:
            c.execute("INSERT INTO widget_settings (tenant_id, config, updated_at) VALUES (?, ?, ?)",
                      (tenant_id, config_json, now))
    return body


# ── Tenant Members Admin ───────────────────────────────────────────────────────

@admin_app.get("/tenants/{tenant_id}/members")
def admin_list_members(tenant_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict]:
    _check_tenant(cu, tenant_id)
    with connect() as c:
        return rows(c, "SELECT id, email, role, display_name FROM users WHERE tenant_id=? AND role != 'owner'", (tenant_id,))


@admin_app.post("/tenants/{tenant_id}/members")
def admin_add_member(tenant_id: int, body: dict[str, Any], cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    from saas.security import hash_password
    import secrets as _secrets
    email = body.get("email", "").strip()
    role = body.get("role", "member")
    if role not in {"owner", "admin", "member", "viewer", "agent"}:
        raise HTTPException(status_code=422, detail="invalid role")
    if role in {"owner", "admin"} and cu.user.role != "owner":
        raise HTTPException(status_code=403, detail="only an owner can add owners or admins")
    display_name = body.get("display_name", email.split("@")[0] if email else "")
    password = body.get("password")
    if not email:
        raise HTTPException(status_code=422, detail="email required")
    with connect() as c:
        existing = rows(c, "SELECT 1 FROM users WHERE tenant_id=? AND email=?", tenant_id, email)
        if existing:
            raise HTTPException(status_code=409, detail="member already exists")
        hashed = hash_password(password or _secrets.token_urlsafe(16))
        now = now_iso()
        cur = c.execute(
            "INSERT INTO users (tenant_id, email, display_name, hashed_password, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, email, display_name, hashed, role, now, now),
        )
        return {"id": cur.lastrowid, "email": email, "role": role, "display_name": display_name}


# ── Email Settings Admin ─────────────────────────────────────────────────────

@admin_app.get("/tenants/{tenant_id}/email")
def admin_get_email(tenant_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    _check_tenant(cu, tenant_id)
    with connect() as c:
        r = rows(c, "SELECT * FROM email_settings WHERE tenant_id = ?", (tenant_id,))
    if not r:
        return {"provider": "default", "from_name": "", "from_email": "", "reply_to": ""}
    row_data = r[0]
    return {
        "provider": row_data["provider"],
        "from_name": row_data.get("from_name", ""),
        "from_email": row_data.get("from_email", ""),
        "reply_to": row_data.get("reply_to", ""),
        "smtp_host": row_data.get("smtp_host", ""),
        "smtp_port": row_data.get("smtp_port"),
        "smtp_user": row_data.get("smtp_user", ""),
        "updated_at": row_data.get("updated_at"),
    }


@admin_app.put("/tenants/{tenant_id}/email")
def admin_update_email(tenant_id: int, body: dict[str, Any], cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    _check_tenant(cu, tenant_id)
    # Mailbox servers and passwords are set only through Settings -> Email (PUT /fd/mailbox), which validates
    # hosts and ports. Accepting them here would bypass that and could send the stored password elsewhere.
    allowed = {"from_name", "from_email", "reply_to", "front_desk_email", "backup_email", "delivery_mode"}
    fields = {k: v for k, v in body.items() if k in allowed}
    if not fields:
        return {"ok": True, "note": "Connect the clinic mailbox in Settings -> Email."}

    with connect() as c:
        existing = rows(c, "SELECT id FROM email_settings WHERE tenant_id = ?", (tenant_id,))
        sets = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [tenant_id]
        now = now_iso()
        if existing:
            c.execute(f"UPDATE email_settings SET {sets}, updated_at = ? WHERE tenant_id = ?", vals + [now])
        else:
            cols = ", ".join(["tenant_id"] + list(fields.keys()) + ["updated_at"])
            marks = ", ".join(["?"] * (len(fields) + 2))
            c.execute(f"INSERT INTO email_settings ({cols}) VALUES ({marks})",
                      [tenant_id] + list(fields.values()) + [now])
    return {"ok": True}


@admin_app.post("/tenants/{tenant_id}/email/test")
def admin_test_email(tenant_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    _check_tenant(cu, tenant_id)
    row_data = _smtp_row(tenant_id)
    to = (row_data or {}).get("from_email") or settings.default_smtp_from
    try:
        result = send_test_email(tenant_id, to)
    except MailboxNotConnected as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": result.ok, "mode": result.mode, "ref": result.ref, "error": result.error}


@admin_app.post("/tenants/{tenant_id}/email/test-smtp")
def admin_test_smtp(tenant_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    _check_tenant(cu, tenant_id)
    ok, detail = test_smtp_connection(tenant_id)
    return {"ok": ok, "detail": detail}


# ── Email Templates Admin ────────────────────────────────────────────────────

@admin_app.get("/tenants/{tenant_id}/templates")
def admin_list_templates(tenant_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> list:
    _check_tenant(cu, tenant_id)
    with connect() as c:
        db_templates = rows(c, "SELECT name, subject, body, intent FROM email_templates WHERE tenant_id = ? ORDER BY id", (tenant_id,))
    # Default templates if none exist in DB
    defaults = [
        {"name": "appointment_request", "subject": "New Appointment Request", "body": "Patient {{patient_name}} ({{phone}}) requested a {{service}} appointment on {{preferred_date}} at {{preferred_time}}.", "intent": "appointment_request"},
        {"name": "emergency", "subject": "URGENT: Emergency Dental Request", "body": "Emergency request from {{patient_name}} ({{phone}}). Concern: {{message}}", "intent": "emergency"},
        {"name": "general_inquiry", "subject": "New Inquiry from {{patient_name}}", "body": "{{patient_name}} ({{email}}, {{phone}}) sent an inquiry: {{message}}", "intent": "general_inquiry"},
    ]
    if db_templates:
        return [dict(t) for t in db_templates]
    return defaults


@admin_app.put("/tenants/{tenant_id}/templates/{template_name}")
def admin_update_template(tenant_id: int, template_name: str, body: dict[str, str],
                          cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    _check_tenant(cu, tenant_id)
    now = now_iso()
    with connect() as c:
        existing = rows(c, "SELECT id FROM email_templates WHERE tenant_id = ? AND name = ?", (tenant_id, template_name))
        if existing:
            c.execute("UPDATE email_templates SET subject = ?, body = ?, updated_at = ? WHERE tenant_id = ? AND name = ?",
                      (body.get("subject", ""), body.get("body", ""), now, tenant_id, template_name))
        else:
            c.execute("INSERT INTO email_templates (tenant_id, name, subject, body, intent, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                      (tenant_id, template_name, body.get("subject", ""), body.get("body", ""), template_name, now))
    return body


@admin_app.get("/template-variables")
def admin_template_variables(_: Any = Depends(require_roles("owner", "admin", "viewer"))) -> dict[str, str]:
    return list_template_variables()


# ── Business Rules Admin ─────────────────────────────────────────────────────

@admin_app.get("/tenants/{tenant_id}/business-rules")
def admin_get_business_rules(tenant_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    _check_tenant(cu, tenant_id)
    with connect() as c:
        r = rows(c, "SELECT rules FROM business_rules WHERE tenant_id = ?", (tenant_id,))
    return json.loads(r[0]["rules"]) if r else {}


@admin_app.put("/tenants/{tenant_id}/business-rules")
def admin_update_business_rules(tenant_id: int, body: dict[str, Any], cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    _check_tenant(cu, tenant_id)
    with connect() as c:
        existing = rows(c, "SELECT id FROM business_rules WHERE tenant_id = ?", (tenant_id,))
        now = now_iso()
        if existing:
            c.execute("UPDATE business_rules SET rules = ?, updated_at = ? WHERE tenant_id = ?",
                      (json.dumps(body), now, tenant_id))
        else:
            c.execute("INSERT INTO business_rules (tenant_id, rules, updated_at) VALUES (?, ?, ?)",
                      (tenant_id, json.dumps(body), now))
    return body


# ── Tenant Settings Admin ────────────────────────────────────────────────────

@admin_app.get("/tenants/{tenant_id}/settings")
def admin_get_settings(tenant_id: int, current: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    _check_tenant(current, tenant_id)
    return _tenant_config(tenant_id)


@admin_app.put("/tenants/{tenant_id}/settings")
def admin_update_settings(tenant_id: int, body: dict[str, Any], cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    _check_tenant(cu, tenant_id)
    allowed_flags = {
        "greeting", "enabled", "ai_enabled", "lead_collection_enabled",
        "email_enabled", "widget_enabled", "auto_open", "auto_open_delay",
        "mode", "max_turns", "conciergeEnabled", "aiEnabled",
        "emailEnabled", "leadCollectionEnabled", "widgetEnabled",
        "autoOpenEnabled", "humanHandoffEnabled", "service_options",
    }
    flags = {k: v for k, v in body.items() if k in allowed_flags}
    ai_instructions = body.get("ai_instructions")

    with connect() as c:
        existing = rows(c, "SELECT id, flags, ai_instructions FROM tenant_settings WHERE tenant_id = ?", (tenant_id,))
        now = now_iso()
        current_flags = json.loads(existing[0]["flags"]) if existing else {}
        current_flags.update(flags)
        if existing:
            sets = ["flags = ?", "updated_at = ?"]
            vals = [json.dumps(current_flags), now]
            if ai_instructions is not None:
                sets.append("ai_instructions = ?")
                vals.append(ai_instructions)
            vals.append(tenant_id)
            c.execute(f"UPDATE tenant_settings SET {', '.join(sets)} WHERE tenant_id = ?", vals)
        else:
            c.execute(
                "INSERT INTO tenant_settings (tenant_id, flags, ai_instructions, updated_at) VALUES (?, ?, ?, ?)",
                (tenant_id, json.dumps(flags), ai_instructions, now),
            )
    return _tenant_config(tenant_id)


# ── Dashboard Template ────────────────────────────────────────────────────────

_dashboard_template = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{dashboard_title}</title>
<style>
  :root {{ --primary: #1f3b2e; --accent: #3a7d6e; --bg: #f0f2f4; --card: #fff; --border: #e5e5e5; --text: #222; --muted: #888; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font: 14px/1.5 system-ui, sans-serif; background: var(--bg); color: var(--text); display: flex; min-height: 100vh; }}
  .sidebar {{ width: 230px; background: var(--primary); color: #fff; flex-shrink: 0; padding: 20px 0; }}
  .sidebar .logo {{ padding: 0 20px 20px; font-size: 20px; font-weight: 800; border-bottom: 1px solid rgba(255,255,255,.15); margin-bottom: 10px; }}
  .sidebar a {{ display: block; padding: 9px 20px; color: rgba(255,255,255,.85); text-decoration: none; font-size: 13px; border-left: 3px solid transparent; }}
  .sidebar a:hover, .sidebar a.active {{ background: rgba(255,255,255,.1); border-left-color: var(--accent); color: #fff; }}
  .sidebar .section {{ font-size: 11px; text-transform: uppercase; color: rgba(255,255,255,.4); padding: 14px 20px 4px; letter-spacing: .08em; }}
  .main {{ flex: 1; padding: 24px 28px; overflow: auto; }}
  .topbar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
  .topbar h1 {{ font-size: 22px; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
  .badge.ok {{ background: #e6f4ea; color: #1e7e34; }}
  .badge.warn {{ background: #fff3cd; color: #856404; }}
  .badge.off {{ background: #fde8e8; color: #c0392b; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 14px; margin-bottom: 24px; }}
  .stat {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }}
  .stat .v {{ font-size: 26px; font-weight: 800; color: var(--primary); }}
  .stat .l {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; margin-bottom: 16px; box-shadow: 0 2px 6px rgba(0,0,0,.04); }}
  .card h3 {{ font-size: 14px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; padding: 8px 6px; border-bottom: 2px solid var(--border); color: var(--muted); font-weight: 600; }}
  td {{ padding: 8px 6px; border-bottom: 1px solid var(--border); }}
  .btn {{ display: inline-block; padding: 8px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; border: 0; text-decoration: none; }}
  .btn-primary {{ background: var(--primary); color: #fff; }}
  .btn-sm {{ padding: 5px 10px; font-size: 12px; }}
  .code {{ background: #f5f5f5; border: 1px solid #ddd; border-radius: 8px; padding: 10px; font-family: monospace; font-size: 12px; word-break: break-all; }}
  .copy-row {{ display: flex; gap: 8px; align-items: center; }}
  .nav {{ display: flex; gap: 10px; margin-bottom: 18px; }}
  .nav a {{ font-size: 13px; color: var(--primary); font-weight: 600; text-decoration: none; }}
  .empty {{ color: var(--muted); font-size: 13px; padding: 16px 0; }}
  .status-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }}
  .status-dot.active {{ background: #28a745; }}
  .status-dot.inactive {{ background: #dc3545; }}
  .tab-bar {{ display: flex; gap: 2px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }}
  .tab {{ padding: 8px 14px; font-size: 13px; cursor: pointer; border-bottom: 2px solid transparent; color: var(--muted); }}
  .tab.active {{ border-bottom-color: var(--primary); color: var(--primary); font-weight: 600; }}
  input[type="text"], input[type="email"], input[type="password"], input[type="number"], select, textarea {{ width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; font-size: 13px; font-family: inherit; }}
  textarea {{ min-height: 80px; resize: vertical; }}
  label {{ display: block; font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 4px; text-transform: uppercase; letter-spacing: .04em; }}
  .form-row {{ margin-bottom: 12px; }}
</style>
</head>
<body>
<nav class="sidebar">
  <div class="logo">HeyJarvis</div>
  <a href="/dashboard/{tenant_id}" class="active">Dashboard</a>
  <div class="section">Core</div>
  <a href="/dashboard/{tenant_id}?tab=concierge">Concierge</a>
  <a href="/dashboard/{tenant_id}?tab=conversations">Conversations</a>
  <a href="/dashboard/{tenant_id}?tab=leads">Leads</a>
  <a href="/dashboard/{tenant_id}?tab=installation">Installation</a>
  <div class="section">Configuration</div>
  <a href="/dashboard/{tenant_id}?tab=widget">Widget</a>
  <a href="/dashboard/{tenant_id}?tab=questions">Questions & Fields</a>
  <a href="/dashboard/{tenant_id}?tab=email">Email</a>
  <a href="/dashboard/{tenant_id}?tab=templates">Templates</a>
  <a href="/dashboard/{tenant_id}?tab=business-rules">Business Rules</a>
  <a href="/dashboard/{tenant_id}?tab=notifications">Notifications</a>
  <div class="section">System</div>
  <a href="/dashboard/{tenant_id}?tab=integrations">Integrations</a>
  <a href="/dashboard/{tenant_id}?tab=team">Team</a>
  <a href="/dashboard/{tenant_id}?tab=security">Security & API</a>
  <a href="/dashboard/{tenant_id}?tab=analytics">Analytics</a>
  <a href="/dashboard/{tenant_id}?tab=settings">Settings</a>
</nav>
<div class="main">
  <div class="topbar">
    <h1>{tenant_name} Dashboard</h1>
    <span class="badge {status_class}"><span class="status-dot {status_dot}"></span>{status_text}</span>
  </div>

  <div id="tab-dashboard" class="tab-content">
    <div class="grid">
      <div class="stat"><div class="v" id="s-conversations">{conversations_count}</div><div class="l">Conversations</div></div>
      <div class="stat"><div class="v" id="s-leads">{leads_count}</div><div class="l">Leads</div></div>
      <div class="stat"><div class="v" id="s-new-leads">{new_leads_count}</div><div class="l">New Leads</div></div>
      <div class="stat"><div class="v" id="s-emails">{emails_sent_count}</div><div class="l">Emails Sent</div></div>
      <div class="stat"><div class="v" id="s-completion">{completion_rate}%</div><div class="l">Completion Rate</div></div>
    </div>
    <div class="card">
      <h3>Recent Conversations</h3>
      {recent_conversations_html}
    </div>
  </div>

  <div id="tab-concierge" class="tab-content" style="display:none">
    <div class="card">
      <h3>Concierge Behavior</h3>
      <p>Manage how your Concierge interacts with visitors.</p>
      <br>
      <div class="form-row">
        <label>Mode</label>
        <select id="concierge-mode">
          <option value="chatbot" {concierge_mode_chatbot}>Chatbot</option>
          <option value="form" {concierge_mode_form}>Form</option>
          <option value="chat+form" {concierge_mode_hybrid}>Chat + Form</option>
        </select>
      </div>
      <div class="form-row">
        <label>Auto-open</label>
        <select id="concierge-auto-open">
          <option value="instant" {auto_open_instant}>Instant</option>
          <option value="3s" {auto_open_3s}>After 3 seconds</option>
          <option value="5s" {auto_open_5s}>After 5 seconds</option>
          <option value="10s" {auto_open_10s}>After 10 seconds</option>
          <option value="never" {auto_open_never}>Never auto-open</option>
        </select>
      </div>
      <br>
      <button class="btn btn-primary" onclick="saveConcierge()">Save Concierge Settings</button>
      <span id="concierge-save-msg" style="margin-left:12px;font-size:13px;color:#888;"></span>
    </div>
  </div>

  <div id="tab-conversations" class="tab-content" style="display:none">
    <div class="card">
      <h3>All Conversations</h3>
      {conversations_table_html}
    </div>
  </div>

  <div id="tab-leads" class="tab-content" style="display:none">
    <div class="card">
      <h3>All Leads</h3>
      {leads_table_html}
    </div>
  </div>

  <div id="tab-installation" class="tab-content" style="display:none">
    <div class="card">
      <h3>Installation</h3>
      <p>Add one of these snippets to your website to enable the Concierge.</p>
      <br>
      <h4>JavaScript Snippet (Recommended)</h4>
      <br>
      <div class="code" id="install-snippet">&lt;script
  src="{widget_url}"
  data-heyjarvis-client="{public_client_key}"
  async&gt;
&lt;/script&gt;</div>
      <br>
      <button class="btn btn-primary btn-sm" onclick="copySnippet()">Copy Snippet</button>
      <br><br>
      <h4>Direct Link</h4>
      <div class="code"><a href="{concierge_url}" target="_blank">{concierge_url}</a></div>
      <br>
      <h4>WordPress</h4>
      <p>Use the HeyJarvis WordPress plugin. Install it from your WP admin dashboard and enter your public client key.</p>
      <br>
      <h4>Google Tag Manager</h4>
      <p>Create a Custom HTML tag in GTM and paste the script snippet above. Trigger on All Pages.</p>
    </div>
  </div>

  <div id="tab-widget" class="tab-content" style="display:none">
    <div class="card">
      <h3>Widget Customization</h3>
      <div class="form-row">
        <label>Widget Title</label>
        <input type="text" id="widget-title" value="{widget_title}">
      </div>
      <div class="form-row">
        <label>Greeting</label>
        <input type="text" id="widget-greeting" value="{widget_greeting}">
      </div>
      <div class="form-row">
        <label>Brand Color</label>
        <input type="text" id="widget-color" value="{widget_color}" placeholder="#1f3b2e">
      </div>
      <div class="form-row">
        <label>Position</label>
        <select id="widget-position">
          <option value="bottom-right" {widget_pos_br}>Bottom Right</option>
          <option value="bottom-left" {widget_pos_bl}>Bottom Left</option>
        </select>
      </div>
      <div class="form-row">
        <label>Launcher Text</label>
        <input type="text" id="widget-launcher" value="{widget_launcher}">
      </div>
      <br>
      <button class="btn btn-primary" onclick="saveWidget()">Save Widget Settings</button>
      <span id="widget-save-msg" style="margin-left:12px;font-size:13px;color:#888;"></span>
    </div>
  </div>

  <div id="tab-questions" class="tab-content" style="display:none">
    <div class="card">
      <h3>Questions & Fields</h3>
      <p>Configure which fields your Concierge collects from visitors.</p>
      <br>
      {fields_list_html}
      <br>
      <button class="btn btn-primary" onclick="saveFields()">Save Field Configuration</button>
      <span id="fields-save-msg" style="margin-left:12px;font-size:13px;color:#888;"></span>
    </div>
  </div>

  <div id="tab-email" class="tab-content" style="display:none">
    <div class="card">
      <h3>Email Configuration</h3>
      <div class="tab-bar">
        <div class="tab active" onclick="showEmailTab('general')">General</div>
        <div class="tab" onclick="showEmailTab('smtp')">Custom SMTP</div>
        <div class="tab" onclick="showEmailTab('delivery')">Delivery Mode</div>
      </div>
      <div id="email-tab-general">
        <div class="form-row">
          <label>From Name</label>
          <input type="text" id="email-from-name" value="{email_from_name}">
        </div>
        <div class="form-row">
          <label>From Email</label>
          <input type="email" id="email-from" value="{email_from}">
        </div>
        <div class="form-row">
          <label>Reply-To</label>
          <input type="email" id="email-reply-to" value="{email_reply_to}">
        </div>
        <div class="form-row">
          <label>Front Desk Email</label>
          <input type="email" id="email-front-desk" value="{email_front_desk}">
        </div>
        <div class="form-row">
          <label>Backup Email</label>
          <input type="email" id="email-backup" value="{email_backup}">
        </div>
      </div>
      <div id="email-tab-smtp" style="display:none">
        <p class="empty">Leave blank to use HeyJarvis default email delivery.</p>
        <div class="form-row">
          <label>SMTP Host</label>
          <input type="text" id="smtp-host" value="{smtp_host}" placeholder="smtp.gmail.com">
        </div>
        <div class="form-row">
          <label>SMTP Port</label>
          <input type="number" id="smtp-port" value="{smtp_port}" placeholder="587">
        </div>
        <div class="form-row">
          <label>SMTP Username</label>
          <input type="text" id="smtp-username" value="{smtp_username}">
        </div>
        <div class="form-row">
          <label>SMTP Password</label>
          <input type="password" id="smtp-password" value="{smtp_password}" placeholder="Enter password">
        </div>
        <div class="form-row">
          <label>SMTP Security</label>
          <select id="smtp-security">
            <option value="tls" {smtp_tls}>TLS</option>
            <option value="ssl" {smtp_ssl}>SSL</option>
            <option value="none" {smtp_none}>None</option>
          </select>
        </div>
        <button class="btn btn-sm btn-primary" onclick="testSMTP()">Test SMTP Connection</button>
        <span id="smtp-test-msg" style="margin-left:10px;font-size:13px;"></span>
      </div>
      <div id="email-tab-delivery" style="display:none">
        <div class="form-row">
          <label>Delivery Mode</label>
          <select id="email-delivery-mode">
            <option value="email_draft" {delivery_draft}>Email Draft (front desk sends manually)</option>
            <option value="direct_email" {delivery_direct}>Direct Email (sent automatically)</option>
          </select>
        </div>
        <p style="font-size:12px;color:#888;">Email Draft creates a draft email for your front desk to review and send. Direct Email sends automatically.</p>
      </div>
      <br>
      <button class="btn btn-primary" onclick="saveEmail()">Save Email Settings</button>
      <button class="btn btn-sm" onclick="testEmail()" style="margin-left:8px;">Send Test Email</button>
      <span id="email-save-msg" style="margin-left:12px;font-size:13px;color:#888;"></span>
    </div>
  </div>

  <div id="tab-templates" class="tab-content" style="display:none">
    <div class="card">
      <h3>Email Templates</h3>
      <p>Customize the emails sent to your front desk for each type of request.</p>
      <br>
      <div class="form-row">
        <label>Template Type</label>
        <select id="template-type" onchange="loadTemplate()">
          <option value="appointment_request">New Appointment Request</option>
          <option value="emergency">Emergency Request</option>
          <option value="general_inquiry">General Inquiry</option>
        </select>
      </div>
      <div class="form-row">
        <label>Subject</label>
        <input type="text" id="template-subject" value="{template_subject}">
      </div>
      <div class="form-row">
        <label>Body</label>
        <textarea id="template-body" placeholder="Use {{patient_name}}, {{phone}}, {{email}}, {{service}}, etc.">{template_body}</textarea>
      </div>
      <br>
      <button class="btn btn-primary" onclick="saveTemplate()">Save Template</button>
      <button class="btn btn-sm" onclick="restoreTemplate()" style="margin-left:8px;">Restore Default</button>
      <span id="template-save-msg" style="margin-left:12px;font-size:13px;color:#888;"></span>
    </div>
  </div>

  <div id="tab-business-rules" class="tab-content" style="display:none">
    <div class="card">
      <h3>Business Rules</h3>
      <p>Configure appointment durations, staffing, and business policies.</p>
      <br>
      <div class="form-row">
        <label>New Patient Duration (minutes)</label>
        <input type="number" id="br-new-patient" value="{br_new_patient}">
      </div>
      <div class="form-row">
        <label>Normal Appointment Duration (minutes)</label>
        <input type="number" id="br-normal" value="{br_normal}">
      </div>
      <div class="form-row">
        <label>Emergency Duration (minutes)</label>
        <input type="number" id="br-emergency" value="{br_emergency}">
      </div>
      <div class="form-row">
        <label>Doctor Columns</label>
        <input type="number" id="br-doctors" value="{br_doctors}">
      </div>
      <div class="form-row">
        <label>Hygiene Columns</label>
        <input type="number" id="br-hygiene" value="{br_hygiene}">
      </div>
      <div class="form-row">
        <label>Confirmation Hours</label>
        <input type="number" id="br-confirm-hours" value="{br_confirm_hours}">
      </div>
      <div class="form-row">
        <label>Broken/No-Show Fee</label>
        <input type="text" id="br-no-show-fee" value="{br_no_show_fee}">
      </div>
      <br>
      <button class="btn btn-primary" onclick="saveBusinessRules()">Save Business Rules</button>
      <span id="br-save-msg" style="margin-left:12px;font-size:13px;color:#888;"></span>
    </div>
  </div>

  <div id="tab-notifications" class="tab-content" style="display:none">
    <div class="card">
      <h3>Notifications</h3>
      <p>Configure how and when notifications are sent to your front desk.</p>
      <div class="form-row">
        <label>Enable Email Notifications</label>
        <select id="notif-email">
          <option value="true" {notif_email_on}>On</option>
          <option value="false" {notif_email_off}>Off</option>
        </select>
      </div>
      <div class="form-row">
        <label>Enable Human Handoff</label>
        <select id="notif-handoff">
          <option value="true" {notif_handoff_on}>On</option>
          <option value="false" {notif_handoff_off}>Off</option>
        </select>
      </div>
      <div class="form-row">
        <label>Handoff Message</label>
        <textarea id="notif-handoff-msg">{notif_handoff_msg}</textarea>
      </div>
      <br>
      <button class="btn btn-primary" onclick="saveNotifications()">Save Notifications</button>
      <span id="notif-save-msg" style="margin-left:12px;font-size:13px;color:#888;"></span>
    </div>
  </div>

  <div id="tab-integrations" class="tab-content" style="display:none">
    <div class="card">
      <h3>Integrations</h3>
      <p>Connect HeyJarvis to your other tools.</p>
      <br>
      <div class="stat"><div class="l">Webhook URL</div><input type="text" id="webhook-url" value="{webhook_url}" placeholder="https://..." style="margin-top:6px;"></div>
      <br>
      <button class="btn btn-primary btn-sm" onclick="saveIntegrations()">Save</button>
      <span id="int-save-msg" style="margin-left:10px;font-size:13px;color:#888;"></span>
    </div>
  </div>

  <div id="tab-team" class="tab-content" style="display:none">
    <div class="card">
      <h3>Team Members</h3>
      {team_members_html}
      <br>
      <h4 style="font-size:13px;margin-bottom:8px;">Add Team Member</h4>
      <input type="email" id="team-email" placeholder="Email" style="width:280px;display:inline-block;margin-right:8px;">
      <select id="team-role" style="width:140px;display:inline-block;">
        <option value="admin">Admin</option>
        <option value="member">Member</option>
        <option value="viewer">Viewer</option>
      </select>
      <button class="btn btn-primary btn-sm" onclick="addTeamMember()">Add</button>
      <span id="team-save-msg" style="margin-left:10px;font-size:13px;color:#888;"></span>
    </div>
  </div>

  <div id="tab-security" class="tab-content" style="display:none">
    <div class="card">
      <h3>Security & API Keys</h3>
      <p>Public client key (safe to use in your website): <span class="code">{public_client_key}</span></p>
      <br>
      <h4>API Keys</h4>
      <table>
        <tr><th>Label</th><th>Public Key</th><th>Created</th><th>Actions</th></tr>
        {api_keys_html}
      </table>
      <br>
      <button class="btn btn-primary btn-sm" onclick="createApiKey()">Create New API Key</button>
      <span id="api-key-msg" style="margin-left:10px;font-size:13px;color:#888;"></span>
    </div>
  </div>

  <div id="tab-analytics" class="tab-content" style="display:none">
    <div class="card">
      <h3>Analytics</h3>
      {analytics_html}
    </div>
  </div>

  <div id="tab-settings" class="tab-content" style="display:none">
    <div class="card">
      <h3>Tenant Settings</h3>
      <div class="form-row">
        <label>Business Name</label>
        <input type="text" id="settings-name" value="{tenant_name}">
      </div>
      <div class="form-row">
        <label>Slug</label>
        <input type="text" id="settings-slug" value="{tenant_slug}" disabled>
      </div>
      <div class="form-row">
        <label>Timezone</label>
        <input type="text" id="settings-timezone" value="{tenant_timezone}">
      </div>
      <br>
      <button class="btn btn-primary" onclick="saveSettings()">Save Settings</button>
      <span id="settings-save-msg" style="margin-left:12px;font-size:13px;color:#888;"></span>
    </div>
  </div>

</div>
<script>
  const API_BASE = '/api/admin';
  const TENANT_ID = '{tenant_id}';
  const TOKEN = '{auth_token}';
  const headers = {{ Authorization: 'Bearer ' + TOKEN }};

  function showTab(name) {{
    document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
    document.querySelector('.sidebar a[href*=\"' + name + '\"]')?.classList.add('active');
    const t = document.getElementById('tab-' + name);
    if (t) t.style.display = 'block';
    else document.getElementById('tab-dashboard').style.display = 'block';
  }}

  const urlParams = new URLSearchParams(window.location.search);
  const initTab = urlParams.get('tab') || 'dashboard';
  showTab(initTab);

  async function api(method, path, body) {{
    const r = await fetch(API_BASE + path, {{ method, headers, body: body ? JSON.stringify(body) : undefined }});
    return r.ok ? r.json() : r.json().then(d => {{ throw d }});
  }}

  async function saveConcierge() {{
    try {{
      await api('PUT', '/tenants/' + TENANT_ID + '/settings', {{
        concierge_mode: document.getElementById('concierge-mode').value,
        concierge_auto_open: document.getElementById('concierge-auto-open').value,
      }});
      showMsg('concierge-save-msg', 'Saved');
    }} catch(e) {{ showMsg('concierge-save-msg', 'Error'); }}
  }}

  async function saveWidget() {{
    try {{
      await api('PUT', '/tenants/' + TENANT_ID + '/widget', {{
        title: document.getElementById('widget-title').value,
        greeting: document.getElementById('widget-greeting').value,
        brand_color: document.getElementById('widget-color').value,
        launcher_text: document.getElementById('widget-launcher').value,
        position: document.getElementById('widget-position').value,
      }});
      showMsg('widget-save-msg', 'Saved');
    }} catch(e) {{ showMsg('widget-save-msg', 'Error'); }}
  }}

  async function saveEmail() {{
    try {{
      await api('PUT', '/tenants/' + TENANT_ID + '/email', {{
        from_name: document.getElementById('email-from-name').value,
        from_email: document.getElementById('email-from').value,
        reply_to: document.getElementById('email-reply-to').value,
        front_desk_email: document.getElementById('email-front-desk').value,
        backup_email: document.getElementById('email-backup').value,
        smtp_host: document.getElementById('smtp-host').value,
        smtp_port: parseInt(document.getElementById('smtp-port').value) || 0,
        smtp_username: document.getElementById('smtp-username').value,
        smtp_password: document.getElementById('smtp-password').value,
        smtp_security: document.getElementById('smtp-security').value,
        delivery_mode: document.querySelector('input[name=\"delivery-mode\"]:checked')?.value || 'email_draft',
      }});
      showMsg('email-save-msg', 'Saved');
    }} catch(e) {{ showMsg('email-save-msg', 'Error'); }}
  }}

  async function testEmail() {{
    const m = document.getElementById('email-save-msg');
    try {{
      const r = await api('POST', '/tenants/' + TENANT_ID + '/email/test', {{}});
      m.textContent = 'Sent!'; m.style.color = '#28a745';
    }} catch(e) {{ m.textContent = 'Error'; m.style.color = '#dc3545'; }}
  }}

  async function testSMTP() {{
    const m = document.getElementById('smtp-test-msg');
    try {{
      const r = await api('POST', '/tenants/' + TENANT_ID + '/email/test-smtp', {{
        smtp_host: document.getElementById('smtp-host').value,
        smtp_port: parseInt(document.getElementById('smtp-port').value) || 587,
        smtp_username: document.getElementById('smtp-username').value,
        smtp_password: document.getElementById('smtp-password').value,
        smtp_security: document.getElementById('smtp-security').value,
      }});
      m.textContent = 'Connected!'; m.style.color = '#28a745';
    }} catch(e) {{ m.textContent = 'Failed'; m.style.color = '#dc3545'; }}
  }}

  async function saveBusinessRules() {{
    try {{
      await api('PUT', '/tenants/' + TENANT_ID + '/business-rules', {{
        new_patient_minutes: parseInt(document.getElementById('br-new-patient').value) || 90,
        normal_appointment_minutes: parseInt(document.getElementById('br-normal').value) || 30,
        emergency_minutes: parseInt(document.getElementById('br-emergency').value) || 60,
        doctor_columns: parseInt(document.getElementById('br-doctors').value) || 2,
        hygiene_columns: parseInt(document.getElementById('br-hygiene').value) || 1,
        confirmation_hours: parseInt(document.getElementById('br-confirm-hours').value) || 48,
        no_show_fee: document.getElementById('br-no-show-fee').value,
      }});
      showMsg('br-save-msg', 'Saved');
    }} catch(e) {{ showMsg('br-save-msg', 'Error'); }}
  }}

  async function saveNotifications() {{
    try {{
      await api('PUT', '/tenants/' + TENANT_ID + '/settings', {{
        email_notifications: document.getElementById('notif-email').value === 'true',
        human_handoff: document.getElementById('notif-handoff').value === 'true',
        handoff_message: document.getElementById('notif-handoff-msg').value,
      }});
      showMsg('notif-save-msg', 'Saved');
    }} catch(e) {{ showMsg('notif-save-msg', 'Error'); }}
  }}

  async function saveIntegrations() {{
    try {{
      await api('PUT', '/tenants/' + TENANT_ID + '/settings', {{
        webhook_url: document.getElementById('webhook-url').value,
      }});
      showMsg('int-save-msg', 'Saved');
    }} catch(e) {{ showMsg('int-save-msg', 'Error'); }}
  }}

  async function saveSettings() {{
    try {{
      await api('PATCH', '/tenants/' + TENANT_ID, {{
        name: document.getElementById('settings-name').value,
        timezone: document.getElementById('settings-timezone').value,
      }});
      showMsg('settings-save-msg', 'Saved');
    }} catch(e) {{ showMsg('settings-save-msg', 'Error'); }}
  }}

  async function saveTemplate() {{
    try {{
      const type = document.getElementById('template-type').value;
      await api('PUT', '/tenants/' + TENANT_ID + '/templates/' + type, {{
        subject: document.getElementById('template-subject').value,
        body: document.getElementById('template-body').value,
      }});
      showMsg('template-save-msg', 'Saved');
    }} catch(e) {{ showMsg('template-save-msg', 'Error'); }}
  }}

  async function restoreTemplate() {{
    try {{
      const type = document.getElementById('template-type').value;
      await api('PUT', '/tenants/' + TENANT_ID + '/templates/' + type, {{ restore_default: true }});
      loadTemplate();
      showMsg('template-save-msg', 'Restored');
    }} catch(e) {{ showMsg('template-save-msg', 'Error'); }}
  }}

  async function loadTemplate() {{
    const type = document.getElementById('template-type').value;
    try {{
      const d = await api('GET', '/tenants/' + TENANT_ID + '/templates');
      let t = {{}};
      if (Array.isArray(d)) {{
        t = d.find(x => x.name === type) || d[0] || {{}};
      }} else if (d && d[type]) {{
        t = d[type];
      }}
      document.getElementById('template-subject').value = t.subject || '';
      document.getElementById('template-body').value = t.body || '';
    }} catch(e) {{}}
  }}

  function showMsg(id, msg) {{
    const el = document.getElementById(id); if (!el) return;
    el.textContent = msg; el.style.color = '#28a745';
    setTimeout(() => {{ el.textContent = ''; }}, 2000);
  }}

  async function saveFields() {{
    try {{
      const fields = [];
      document.querySelectorAll('.field-row').forEach(row => {{
        fields.push({{
          key: row.dataset.key,
          label: row.querySelector('.f-label')?.value || '',
          type: row.querySelector('.f-type')?.value || 'text',
          required: row.querySelector('.f-required')?.checked || false,
          enabled: row.querySelector('.f-enabled')?.checked !== false,
        }});
      }});
      await api('PUT', '/tenants/' + TENANT_ID + '/settings', {{ custom_fields: fields }});
      showMsg('fields-save-msg', 'Saved');
    }} catch(e) {{ showMsg('fields-save-msg', 'Error'); }}
  }}

  function showEmailTab(name) {{
    ['general','smtp','delivery'].forEach(t => document.getElementById('email-tab-'+t).style.display = t === name ? 'block' : 'none');
    document.querySelectorAll('#tab-email .tab').forEach((t,i) => t.classList.toggle('active', ['general','smtp','delivery'][i] === name));
  }}

  async function addTeamMember() {{
    const email = document.getElementById('team-email').value;
    const role = document.getElementById('team-role').value;
    if (!email) return;
    try {{
      await api('POST', '/tenants/' + TENANT_ID + '/members', {{ email, role }});
      document.getElementById('team-email').value = '';
      showMsg('team-save-msg', 'Added');
    }} catch(e) {{ showMsg('team-save-msg', 'Error'); }}
  }}

  async function createApiKey() {{
    try {{
      const d = await api('POST', '/tenants/' + TENANT_ID + '/api-keys', {{ label: 'new' }});
      showMsg('api-key-msg', 'Created: ' + d.public_key);
    }} catch(e) {{ showMsg('api-key-msg', 'Error'); }}
  }}

  function copySnippet() {{
    const text = document.getElementById('install-snippet').textContent.trim();
    navigator.clipboard.writeText(text).then(() => alert('Copied!'));
  }}
</script>
</body>
</html>"""


@admin_app.get("/dashboard/{tenant_id}")
@admin_app.get("/admin/dashboard/{tenant_id}")
def admin_dashboard(tenant_id: int, cu: Any = Depends(get_current)):
    if cu.user.tenant_id != tenant_id:
        raise HTTPException(403)
    tenant = _load_tenant(tenant_id)
    tenant_name = tenant.get("name", "My Business")
    tenant_slug = tenant.get("slug", "")
    tenant_timezone = tenant.get("timezone", "UTC")
    public_key = _public_key(tenant_id)  # load actual public key
    status_class = "ok" if tenant.get("enabled") else "off"
    status_dot = "active" if tenant.get("enabled") else "inactive"
    status_text = "Active" if tenant.get("enabled") else "Disabled"
    # Generate a fresh token for the dashboard JS to use
    from saas.security import create_access_token
    auth_token = create_access_token(subject=str(cu.user.id), tenant_id=tenant_id)

    app_url = os.environ.get("APP_URL", "http://localhost:8000").rstrip("/")
    widget_url = app_url + "/widget.js"
    concierge_url = app_url + "/concierge/" + tenant_slug

    with connect() as c:
        conversations_count = c.execute("SELECT COUNT(*) FROM conversations WHERE tenant_id=?", (tenant_id,)).fetchone()[0]
        new_leads_count = c.execute("SELECT COUNT(*) FROM leads WHERE tenant_id=? AND status='new'", (tenant_id,)).fetchone()[0]
        leads_count = c.execute("SELECT COUNT(*) FROM leads WHERE tenant_id=?", (tenant_id,)).fetchone()[0]
        emails_sent_count = c.execute("SELECT COUNT(*) FROM notifications WHERE tenant_id=? AND status='sent'", (tenant_id,)).fetchone()[0]
        total_leads = leads_count or 1
        completion_rate = min(100, round(((conversations_count or 0) / max(total_leads, 1)) * 100))
        recent = rows(c, "SELECT id, visitor_id, page_url, status, created_at FROM conversations WHERE tenant_id=? ORDER BY id DESC LIMIT 8", (tenant_id,))
        recent_leads = rows(c, "SELECT id, name, email, intent, status, created_at FROM leads WHERE tenant_id=? ORDER BY id DESC LIMIT 5", (tenant_id,))
        conv_rows = rows(c, "SELECT id, visitor_id, page_url, status, created_at FROM conversations WHERE tenant_id=? ORDER BY id DESC LIMIT 50", (tenant_id,))
        lead_rows = rows(c, "SELECT id, name, email, intent, status, created_at FROM leads WHERE tenant_id=? ORDER BY id DESC LIMIT 50", (tenant_id,))
        api_keys = rows(c, "SELECT id, label, public_key, created_at FROM api_keys WHERE tenant_id=?", (tenant_id,))
        members = rows(c, "SELECT id, email, role, display_name FROM users WHERE tenant_id=? AND role != 'owner'", (tenant_id,))

    # Analytics
    analytics = rows(c, "SELECT event_type, COUNT(*) as cnt FROM analytics WHERE tenant_id=? GROUP BY event_type ORDER BY cnt DESC", (tenant_id,)) if False else []

    recent_html = ""
    if recent:
        recent_html += "<table><tr><th>ID</th><th>Visitor ID</th><th>Page</th><th>Status</th><th>Date</th></tr>"
        for r in recent:
            recent_html += f"<tr><td>{r.get('id')}</td><td>{r.get('visitor_id','')}</td><td>{r.get('page_url','')}</td><td>{r.get('status','')}</td><td>{r.get('created_at','')}</td></tr>"
        recent_html += "</table>"
    else:
        recent_html = "<p class='empty'>No conversations yet.</p>"

    conv_html = ""
    if conv_rows:
        conv_html += "<table><tr><th>ID</th><th>Visitor ID</th><th>Page</th><th>Status</th><th>Date</th></tr>"
        for r in conv_rows:
            conv_html += f"<tr><td><a href='#'>{r.get('id')}</a></td><td>{r.get('visitor_id','')}</td><td>{r.get('page_url','')}</td><td>{r.get('status','')}</td><td>{r.get('created_at','')}</td></tr>"
        conv_html += "</table>"
    else:
        conv_html = "<p class='empty'>No conversations yet.</p>"

    leads_html = ""
    if lead_rows:
        leads_html += "<table><tr><th>ID</th><th>Name</th><th>Email</th><th>Intent</th><th>Status</th><th>Date</th></tr>"
        for r in lead_rows:
            leads_html += f"<tr><td>{r.get('id')}</td><td>{r.get('name','')}</td><td>{r.get('email','')}</td><td>{r.get('intent','')}</td><td>{r.get('status','')}</td><td>{r.get('created_at','')}</td></tr>"
        leads_html += "</table>"
    else:
        leads_html = "<p class='empty'>No leads yet.</p>"

    team_html = ""
    if members:
        team_html += "<table><tr><th>Email</th><th>Name</th><th>Role</th></tr>"
        for m in members:
            team_html += f"<tr><td>{m.get('email','')}</td><td>{m.get('display_name','')}</td><td>{m.get('role','')}</td></tr>"
        team_html += "</table>"
    else:
        team_html = "<p class='empty'>No additional team members.</p>"

    api_keys_html = ""
    if api_keys:
        api_keys_html = "<table><tr><th>Label</th><th>Public Key</th><th>Created</th><th>Actions</th></tr>"
        for k in api_keys:
            api_keys_html += f"<tr><td>{k.get('label','')}</td><td><span class='code'>{k.get('public_key','')}</span></td><td>{k.get('created_at','')}</td><td><button class='btn btn-sm' onclick='alert(\"Revoke via API\")'>Revoke</button></td></tr>"
        api_keys_html += "</table>"
    else:
        api_keys_html = "<p class='empty'>No API keys yet.</p>"

    analytics_html = ""
    if analytics:
        analytics_html = "<table><tr><th>Event</th><th>Count</th></tr>"
        for a in analytics:
            analytics_html += f"<tr><td>{a.get('event_type','')}</td><td>{a.get('cnt',0)}</td></tr>"
        analytics_html += "</table>"
    else:
        analytics_html = "<p class='empty'>No analytics yet.</p>"

    # Email settings
    from saas.repositories import get_tenant_email, get_templates
    email_settings = get_tenant_email(tenant_id) or {}
    templates = get_templates(tenant_id)
    template_body = ""
    template_subject = "New Appointment Request"
    if templates:
        for t in templates:
            if t.get("name") == "appointment_request":
                template_subject = t.get("subject", template_subject)
                template_body = t.get("body", "")
                break

    # Business rules
    from saas.repositories import _loads
    rules_raw = ""
    with connect() as c:
        row_br = row(c, "SELECT rules FROM business_rules WHERE tenant_id=?", (tenant_id,))
    rules = _loads(row_br.get("rules") if row_br else "")
    br = rules if isinstance(rules, dict) else {}

    # Settings flags
    flags = {}
    with connect() as c:
        row_s = row(c, "SELECT flags FROM tenant_settings WHERE tenant_id=?", (tenant_id,))
    flags = _loads(row_s.get("flags") if row_s else "")
    if not isinstance(flags, dict):
        flags = {}

    # Fields
    custom_fields = flags.get("custom_fields", [
        {"key": "name", "label": "Name", "type": "text", "required": True},
        {"key": "email", "label": "Email", "type": "email", "required": True},
        {"key": "phone", "label": "Phone", "type": "tel", "required": True},
        {"key": "service", "label": "Service", "type": "select", "required": True},
        {"key": "preferred_date", "label": "Preferred Date", "type": "text", "required": False},
        {"key": "preferred_time", "label": "Preferred Time", "type": "text", "required": False},
        {"key": "message", "label": "Message", "type": "textarea", "required": False},
    ])
    fields_list_html = "<table><tr><th>Label</th><th>Type</th><th>Required</th><th>Enabled</th></tr>"
    for field in custom_fields:
        fields_list_html += f"""<tr class="field-row" data-key="{field.get('key','')}">
          <td><input class="f-label" value="{field.get('label','')}"></td>
          <td><select class="f-type"><option {'selected' if field.get('type')=='text' else ''}>text</option><option {'selected' if field.get('type')=='email' else ''}>email</option><option {'selected' if field.get('type')=='tel' else ''}>tel</option><option {'selected' if field.get('type')=='textarea' else ''}>textarea</option><option {'selected' if field.get('type')=='select' else ''}>select</option><option {'selected' if field.get('type')=='checkbox' else ''}>checkbox</option></select></td>
          <td><input type="checkbox" class="f-required" {'checked' if field.get('required') else ''}></td>
          <td><input type="checkbox" class="f-enabled" {'checked' if field.get('enabled', True) else ''}></td>
        </tr>"""
    fields_list_html += "</table>"

    concierge_mode = flags.get("concierge_mode", "chatbot")
    concierge_auto_open = flags.get("concierge_auto_open", "instant")
    widget_settings = flags.get("widget_settings", {})
    if isinstance(widget_settings, dict):
        ws = widget_settings
    else:
        ws = {}

    widget_title = ws.get("title", tenant_name)
    widget_greeting = ws.get("greeting", "Hi! How can we help today?")
    widget_color = ws.get("brand_color", "#1f3b2e")
    widget_position = ws.get("position", "bottom-right")
    widget_launcher = ws.get("launcher_text", "Chat with us")

    notif_email_on = 'selected' if flags.get("email_notifications", True) else ""
    notif_email_off = 'selected' if not flags.get("email_notifications", True) else ""
    notif_handoff_on = 'selected' if flags.get("human_handoff", True) else ""
    notif_handoff_off = 'selected' if not flags.get("human_handoff", True) else ""
    handoff_msg = flags.get("handoff_message", "Let me connect you with our front desk.")
    webhook_url = flags.get("webhook_url", "")

    html = _dashboard_template.format(
        dashboard_title=tenant_name + " - Dashboard",
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        tenant_slug=tenant_slug,
        tenant_timezone=tenant_timezone,
        public_client_key=public_key,
        status_class=status_class,
        status_dot=status_dot,
        status_text=status_text,
        widget_url=widget_url,
        concierge_url=concierge_url,
        conversations_count=conversations_count or 0,
        leads_count=leads_count or 0,
        new_leads_count=new_leads_count or 0,
        emails_sent_count=emails_sent_count or 0,
        completion_rate=completion_rate,
        recent_conversations_html=recent_html,
        conversations_table_html=conv_html,
        leads_table_html=leads_html,
        team_members_html=team_html,
        api_keys_html=api_keys_html,
        analytics_html=analytics_html,
        fields_list_html=fields_list_html,
        widget_title=widget_title,
        widget_greeting=widget_greeting,
        widget_color=widget_color,
        widget_position=widget_position,
        widget_launcher=widget_launcher,
        widget_pos_br='selected' if widget_position == 'bottom-right' else '',
        widget_pos_bl='selected' if widget_position == 'bottom-left' else '',
        email_from_name=email_settings.get("from_name", tenant_name),
        email_from=email_settings.get("from_email", ""),
        email_reply_to=email_settings.get("reply_to", ""),
        email_front_desk=email_settings.get("front_desk_email", ""),
        email_backup=email_settings.get("backup_email", ""),
        smtp_host=email_settings.get("smtp_host", ""),
        smtp_port=email_settings.get("smtp_port", ""),
        smtp_username=email_settings.get("smtp_username", ""),
        smtp_password=email_settings.get("smtp_password", ""),
        smtp_tls='selected' if email_settings.get("smtp_security", "tls") == "tls" else '',
        smtp_ssl='selected' if email_settings.get("smtp_security") == "ssl" else '',
        smtp_none='selected' if not email_settings.get("smtp_security") else '',
        delivery_draft='selected' if email_settings.get("delivery_mode", "email_draft") == "email_draft" else '',
        delivery_direct='selected' if email_settings.get("delivery_mode") == "direct_email" else '',
        template_subject=template_subject,
        template_body=template_body,
        br_new_patient=br.get("new_patient_minutes", 90),
        br_normal=br.get("normal_appointment_minutes", 30),
        br_emergency=br.get("emergency_minutes", 60),
        br_doctors=br.get("doctor_columns", 2),
        br_hygiene=br.get("hygiene_columns", 1),
        br_confirm_hours=br.get("confirmation_hours", 48),
        br_no_show_fee=br.get("no_show_fee", "$65"),
        notif_email_on=notif_email_on,
        notif_email_off=notif_email_off,
        notif_handoff_on=notif_handoff_on,
        notif_handoff_off=notif_handoff_off,
        notif_handoff_msg=handoff_msg,
        webhook_url=webhook_url,
        concierge_mode_chatbot='selected' if concierge_mode == 'chatbot' else '',
        concierge_mode_form='selected' if concierge_mode == 'form' else '',
        concierge_mode_hybrid='selected' if concierge_mode == 'chat+form' else '',
        auto_open_instant='selected' if concierge_auto_open == 'instant' else '',
        auto_open_3s='selected' if concierge_auto_open == '3s' else '',
        auto_open_5s='selected' if concierge_auto_open == '5s' else '',
        auto_open_10s='selected' if concierge_auto_open == '10s' else '',
        auto_open_never='selected' if concierge_auto_open == 'never' else '',
        auth_token=auth_token,
    )
    return HTMLResponse(content=html)

@admin_app.get("/tenants/{tenant_id}/audit")
def admin_audit_log(tenant_id: int, limit: int = 50, cu: CurrentUser = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict]:
    _check_tenant(cu, tenant_id)
    with connect() as c:
        return rows(c, "SELECT * FROM audit_logs WHERE tenant_id = ? ORDER BY id DESC LIMIT ?", tenant_id, limit)


# ── API Keys Admin ────────────────────────────────────────────────────────────

@admin_app.post("/tenants/{tenant_id}/api-keys")
def admin_create_api_key(tenant_id: int, body: dict[str, Any], cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    _check_tenant(cu, tenant_id)
    from saas.repositories import create_api_key
    label = body.get("label", "default")
    secret = body.get("secret") or __import__("secrets").token_urlsafe(24)
    key = create_api_key(tenant_id, label, secret)
    return {"id": key.id, "label": key.label, "public_key": key.public_key, "secret": secret}


@admin_app.delete("/api-keys/{key_id}")
def admin_revoke_api_key(key_id: int, cu: CurrentUser = Depends(require_roles("owner", "admin"))) -> dict:
    from saas.repositories import revoke_api_key, get_api_key
    key = get_api_key(key_id)
    _own(cu, key.tenant_id if key else None)
    revoke_api_key(key_id)
    return {"ok": True}


@admin_app.get("/tenants/{tenant_id}/integration/wordpress")
def admin_download_wordpress(tenant_id: int, cu: Any = Depends(get_current)):
    if cu.user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="forbidden")
    plugin_dir = Path(__file__).resolve().parent.parent.parent / "wordpress" / "heyjarvis-concierge"
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail="plugin not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in plugin_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(plugin_dir))
    buf.seek(0)
    from fastapi.responses import Response
    return Response(content=buf.read(), media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename=heyjarvis-concierge.zip"})
