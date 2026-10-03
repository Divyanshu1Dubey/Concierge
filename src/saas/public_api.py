"""Public-facing API for the embeddable widget and hosted concierge pages."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from saas.auth import get_current, require_roles
from saas.config import get_settings
from saas.conversation import ConversationEngine, DEFAULT_GREETING, State
from saas.database import connect, rows
from saas.emailer import send_lead_notification
from saas.conversation import ConversationContext
from saas.repositories import (
    add_domain as repo_add_domain,
    complete_conversation,
    create_conversation,
    create_lead,
    list_domains as repo_list_domains,
    list_tenants,
    remove_domain as repo_remove_domain,
    track_event,
    verify_domain as repo_verify_domain,
)
from saas.repositories import get_api_key_by_public

log = logging.getLogger(__name__)
settings = get_settings()
STATIC = Path(__file__).resolve().parent / "static"

public_app = FastAPI(title="HeyJarvis Concierge Public", version="1.0.0")
public_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


def _tenant_config(tenant_id: int) -> dict[str, Any]:
    with connect() as c:
        row = rows(c, "SELECT flags, ai_instructions FROM tenant_settings WHERE tenant_id = ?", tenant_id)
    out: dict[str, Any] = {}
    if row:
        flags_raw = row[0].get("flags") or "{}"
        try:
            out.update(json.loads(flags_raw))
        except json.JSONDecodeError:
            pass
        if row[0].get("ai_instructions"):
            out["ai_instructions"] = row[0]["ai_instructions"]
    out.setdefault("greeting", DEFAULT_GREETING)
    return out


@public_app.get("/health")
def public_health() -> dict:
    return {"ok": True}


@public_app.get("/api/v1/public/config")
def public_config(client_key: str, request: Request) -> dict:
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")
    with connect() as c:
        tenant = rows(c, "SELECT id, name, slug FROM tenants WHERE id = ? AND enabled = 1", key.tenant_id)[0]
        origin = request.headers.get("origin", "").replace("https://", "").replace("http://", "").split("/")[0].lower()
        domain_ok = rows(c, "SELECT 1 FROM domains WHERE tenant_id = ? AND domain = ?", key.tenant_id, origin)
    cfg = _tenant_config(tenant["id"])
    return {
        "tenant_id": tenant["id"],
        "tenant_name": tenant["name"],
        "tenant_slug": tenant["slug"],
        "greeting": cfg.get("greeting"),
        "allowed_origin": bool(domain_ok),
    }


@public_app.post("/api/v1/public/conversations")
def public_conversation_start(client_key: str, request: Request) -> dict:
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")
    cfg = _tenant_config(key.tenant_id)
    engine = ConversationEngine(cfg)
    result = engine.start(key.tenant_id, str(request.url), request.headers.get("referer"), request.headers.get("user-agent"),
                          request.client.host if request.client else None)
    track_event(key.tenant_id, "conversation_started", {"conversation_id": result["conversation_id"]})
    return result


@public_app.post("/api/v1/public/conversations/{conversation_id}/messages")
def public_conversation_message(conversation_id: int, body: dict[str, Any], client_key: str) -> dict:
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")
    with connect() as c:
        conv = rows(c, "SELECT id, tenant_id, status, metadata FROM conversations WHERE id = ?", conversation_id)
    if not conv or conv[0]["tenant_id"] != key.tenant_id:
        raise HTTPException(status_code=404, detail="conversation not found")
    ctx = ConversationContext(conversation_id=conversation_id, tenant_id=conv[0]["tenant_id"])
    context = ConversationEngine(_tenant_config(key.tenant_id))
    result = context.handle(ctx, body.get("message", ""))
    if ctx.state == State.SUBMITTED:
        lead = create_lead(ctx.tenant_id, {
            "conversation_id": conversation_id,
            "source": "website_widget",
            "page_url": conv[0]["metadata"],
            **ctx.fields,
        })
        send_lead_notification(ctx.tenant_id, lead["id"])
        track_event(ctx.tenant_id, "lead_created", {"lead_id": lead["id"], "conversation_id": conversation_id})
    return result


@public_app.get("/widget.js")
def public_widget() -> FileResponse:
    return FileResponse(STATIC / "widget.js", media_type="application/javascript")


admin_app = FastAPI(title="HeyJarvis Admin", version="1.0.0")


@admin_app.get("/api/admin/tenants")
def admin_list_tenants(_: Any = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict[str, Any]]:
    return [t.model_dump() for t in list_tenants()]


@admin_app.post("/api/admin/tenants/{tenant_id}/domains")
def admin_add_domain(tenant_id: int, body: dict[str, Any], _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    dom = repo_add_domain(tenant_id, body.get("domain", ""))
    return dom.model_dump()


@admin_app.post("/api/admin/domains/{domain_id}/verify")
def admin_verify_domain(domain_id: int, _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    repo_verify_domain(domain_id)
    return {"ok": True}


@admin_app.delete("/api/admin/domains/{domain_id}")
def admin_remove_domain(domain_id: int, _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    repo_remove_domain(domain_id)
    return {"ok": True}


@admin_app.get("/api/admin/tenants/{tenant_id}/domains")
def admin_list_domains(tenant_id: int, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict[str, Any]]:
    return [d.model_dump() for d in repo_list_domains(tenant_id)]


@public_app.get("/api/v1/public/leads")
def public_lead_status(client_key: str, lead_id: int) -> dict:
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")
    with connect() as c:
        lead = rows(c, "SELECT id, status, updated_at FROM leads WHERE id = ? AND tenant_id = ?", lead_id, key.tenant_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead[0]
