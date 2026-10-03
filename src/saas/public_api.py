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
from saas.database import connect, now_iso, rows
from saas.emailer import (
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
    get_lead,
    list_domains as repo_list_domains,
    list_tenants,
    remove_domain as repo_remove_domain,
    track_event,
    update_lead as repo_update_lead,
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


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tenant_config(tenant_id: int) -> dict[str, Any]:
    with connect() as c:
        row_data = rows(c, "SELECT flags, ai_instructions FROM tenant_settings WHERE tenant_id = ?", tenant_id)
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
        r = rows(c, "SELECT id, name, slug, enabled, metadata FROM tenants WHERE id = ?", tenant_id)
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


# ── Public Routes ────────────────────────────────────────────────────────────

@public_app.get("/health")
def public_health() -> dict:
    return {"ok": True}


@public_app.get("/api/v1/public/config")
def public_config(client_key: str, request: Request) -> dict:
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")
    with connect() as c:
        tenant = rows(c, "SELECT id, name, slug, enabled FROM tenants WHERE id = ? AND enabled = 1", key.tenant_id)
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
        "widget_config": cfg,
    }


@public_app.post("/api/v1/public/conversations")
def public_conversation_start(client_key: str, request: Request) -> dict:
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
        request.client.host if request.client else None,
    )
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
        lead = create_lead(key.tenant_id, {
            "conversation_id": conversation_id,
            "source": "website_widget",
            "page_url": conv[0].get("metadata", {}).get("page_url") if isinstance(conv[0].get("metadata"), dict) else None,
            **ctx.fields,
        })
        try:
            send_lead_notification(key.tenant_id, lead["id"], intent=ctx.fields.get("intent", "default"))
        except Exception as e:
            log.exception("lead notification failed for tenant %s lead %s", key.tenant_id, lead["id"])
        track_event(key.tenant_id, "lead_created", {"lead_id": lead["id"], "conversation_id": conversation_id})
    return result


@public_app.get("/api/v1/public/leads")
def public_lead_status(client_key: str, lead_id: int) -> dict:
    key = get_api_key_by_public(client_key)
    if not key or key.revoked_at:
        raise HTTPException(status_code=401, detail="invalid client key")
    lead = get_lead(lead_id)
    if not lead or lead["tenant_id"] != key.tenant_id:
        raise HTTPException(status_code=404, detail="lead not found")
    return {"id": lead["id"], "status": lead["status"], "updated_at": lead["updated_at"]}


@public_app.get("/widget.js")
def public_widget() -> FileResponse:
    return FileResponse(STATIC / "widget.js", media_type="application/javascript")


# ── Admin Routes ─────────────────────────────────────────────────────────────

admin_app = FastAPI(title="HeyJarvis Admin", version="1.0.0")


@admin_app.get("/api/admin/tenants")
def admin_list_tenants(_: Any = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict[str, Any]]:
    return [t.model_dump() for t in list_tenants()]


@admin_app.get("/api/admin/tenants/{tenant_id}")
def admin_get_tenant(tenant_id: int, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    return _load_tenant(tenant_id)


@admin_app.patch("/api/admin/tenants/{tenant_id}")
def admin_update_tenant(tenant_id: int, body: dict[str, Any], _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    from saas.repositories import update_tenant
    allowed = {"name", "enabled", "plan"}
    fields = {k: v for k, v in body.items() if k in allowed}
    update_tenant(tenant_id, **fields)
    from saas.repositories import audit
    actor_id = current.user.id if hasattr(current, "user") else None
    audit(tenant_id, actor_id, "tenant_updated", {"fields": list(fields.keys())})
    return _load_tenant(tenant_id)


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


# ── Leads Admin ──────────────────────────────────────────────────────────────

@admin_app.get("/api/admin/tenants/{tenant_id}/leads")
def admin_list_leads(tenant_id: int, status: str | None = None, limit: int = 100, offset: int = 0,
                     _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict]:
    from saas.repositories import list_leads
    return list_leads(tenant_id, status=status, limit=limit, offset=offset)


@admin_app.get("/api/admin/leads/{lead_id}")
def admin_get_lead(lead_id: int, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@admin_app.patch("/api/admin/leads/{lead_id}")
def admin_update_lead(lead_id: int, body: dict[str, Any], _: Any = Depends(require_roles("owner", "admin", "member"))) -> dict:
    allowed = {"status", "name", "email", "phone", "intent", "service", "urgency",
               "preferred_date", "preferred_time", "insurance", "financing", "message"}
    fields = {k: v for k, v in body.items() if k in allowed}
    if not fields:
        raise HTTPException(status_code=400, detail="no valid fields")
    repo_update_lead(lead_id, **fields)
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


# ── Conversations Admin ──────────────────────────────────────────────────────

@admin_app.get("/api/admin/tenants/{tenant_id}/conversations")
def admin_list_conversations(tenant_id: int, status: str | None = None, limit: int = 100, offset: int = 0,
                              _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict]:
    with connect() as c:
        sql = "SELECT * FROM conversations WHERE tenant_id = ?"
        args = [tenant_id]
        if status:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        return rows(c, sql, *args)


@admin_app.get("/api/admin/conversations/{conversation_id}/messages")
def admin_get_messages(conversation_id: int, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict]:
    with connect() as c:
        conv = rows(c, "SELECT tenant_id FROM conversations WHERE id = ?", conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    with connect() as c:
        return rows(c, "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", conversation_id)


# ── Analytics Admin ──────────────────────────────────────────────────────────

@admin_app.get("/api/admin/tenants/{tenant_id}/analytics")
def admin_analytics(tenant_id: int, days: int = 7, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
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
    return (datetime.now() - timedelta(days=n)).isoformat(timespec="seconds")


# ── Widget Settings Admin ────────────────────────────────────────────────────

@admin_app.get("/api/admin/tenants/{tenant_id}/widget")
def admin_get_widget(tenant_id: int, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    with connect() as c:
        r = rows(c, "SELECT config FROM widget_settings WHERE tenant_id = ?", tenant_id)
    return json.loads(r[0]["config"]) if r else {}


@admin_app.put("/api/admin/tenants/{tenant_id}/widget")
def admin_update_widget(tenant_id: int, body: dict[str, Any], _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    with connect() as c:
        existing = rows(c, "SELECT id FROM widget_settings WHERE tenant_id = ?", tenant_id)
        config_json = json.dumps(body)
        now = now_iso()
        if existing:
            c.execute("UPDATE widget_settings SET config = ?, updated_at = ? WHERE tenant_id = ?",
                      (config_json, now, tenant_id))
        else:
            c.execute("INSERT INTO widget_settings (tenant_id, config, updated_at) VALUES (?, ?, ?)",
                      (tenant_id, config_json, now))
    return body


# ── Email Settings Admin ─────────────────────────────────────────────────────

@admin_app.get("/api/admin/tenants/{tenant_id}/email")
def admin_get_email(tenant_id: int, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    with connect() as c:
        r = rows(c, "SELECT * FROM email_settings WHERE tenant_id = ?", tenant_id)
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


@admin_app.put("/api/admin/tenants/{tenant_id}/email")
def admin_update_email(tenant_id: int, body: dict[str, Any], _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    from saas.security import encrypt_value
    allowed = {"provider", "smtp_host", "smtp_port", "smtp_user", "smtp_password",
               "from_name", "from_email", "reply_to"}
    fields = {k: v for k, v in body.items() if k in allowed}
    if "smtp_password" in fields and fields["smtp_password"]:
        fields["smtp_password_enc"] = encrypt_value(fields.pop("smtp_password"))
    elif "smtp_password" in fields:
        fields.pop("smtp_password")

    with connect() as c:
        existing = rows(c, "SELECT id FROM email_settings WHERE tenant_id = ?", tenant_id)
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


@admin_app.post("/api/admin/tenants/{tenant_id}/email/test")
def admin_test_email(tenant_id: int, _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    row_data = _smtp_row(tenant_id)
    to = (row_data or {}).get("from_email") or settings.default_smtp_from
    result = send_test_email(tenant_id, to)
    return {"ok": result.ok, "mode": result.mode, "ref": result.ref, "error": result.error}


@admin_app.post("/api/admin/tenants/{tenant_id}/email/test-smtp")
def admin_test_smtp(tenant_id: int, _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    ok, detail = test_smtp_connection(tenant_id)
    return {"ok": ok, "detail": detail}


# ── Email Templates Admin ────────────────────────────────────────────────────

@admin_app.get("/api/admin/tenants/{tenant_id}/templates")
def admin_list_templates(tenant_id: int, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    from saas.email_templates import DEFAULT_TEMPLATES
    with connect() as c:
        r = rows(c, "SELECT value FROM tenant_settings WHERE tenant_id = ? AND key = 'email_templates'", tenant_id)
    custom = {}
    if r:
        try:
            custom = json.loads(r[0]["value"])
        except Exception:
            pass
    merged = dict(DEFAULT_TEMPLATES)
    merged.update(custom)
    return merged


@admin_app.put("/api/admin/tenants/{tenant_id}/templates/{template_name}")
def admin_update_template(tenant_id: int, template_name: str, body: dict[str, str],
                          _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    with connect() as c:
        r = rows(c, "SELECT value FROM tenant_settings WHERE tenant_id = ? AND key = 'email_templates'", tenant_id)
        existing = json.loads(r[0]["value"]) if r else {}
    existing[template_name] = body
    with connect() as c:
        rid = rows(c, "SELECT id FROM tenant_settings WHERE tenant_id = ? AND key = 'email_templates'", tenant_id)
        now = now_iso()
        if rid:
            c.execute("UPDATE tenant_settings SET value = ?, updated_at = ? WHERE tenant_id = ? AND key = 'email_templates'",
                      (json.dumps(existing), now, tenant_id))
        else:
            c.execute("INSERT INTO tenant_settings (tenant_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
                      (tenant_id, "email_templates", json.dumps(existing), now))
    return body


@admin_app.get("/api/admin/template-variables")
def admin_template_variables(_: Any = Depends(require_roles("owner", "admin", "viewer"))) -> dict[str, str]:
    return list_template_variables()


# ── Business Rules Admin ─────────────────────────────────────────────────────

@admin_app.get("/api/admin/tenants/{tenant_id}/business-rules")
def admin_get_business_rules(tenant_id: int, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    with connect() as c:
        r = rows(c, "SELECT rules FROM business_rules WHERE tenant_id = ?", tenant_id)
    return json.loads(r[0]["rules"]) if r else {}


@admin_app.put("/api/admin/tenants/{tenant_id}/business-rules")
def admin_update_business_rules(tenant_id: int, body: dict[str, Any], _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    with connect() as c:
        existing = rows(c, "SELECT id FROM business_rules WHERE tenant_id = ?", tenant_id)
        now = now_iso()
        if existing:
            c.execute("UPDATE business_rules SET rules = ?, updated_at = ? WHERE tenant_id = ?",
                      (json.dumps(body), now, tenant_id))
        else:
            c.execute("INSERT INTO business_rules (tenant_id, rules, updated_at) VALUES (?, ?, ?)",
                      (tenant_id, json.dumps(body), now))
    return body


# ── Tenant Settings Admin ────────────────────────────────────────────────────

@admin_app.get("/api/admin/tenants/{tenant_id}/settings")
def admin_get_settings(tenant_id: int, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> dict:
    return _tenant_config(tenant_id)


@admin_app.put("/api/admin/tenants/{tenant_id}/settings")
def admin_update_settings(tenant_id: int, body: dict[str, Any], _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    allowed_flags = {
        "greeting", "enabled", "ai_enabled", "lead_collection_enabled",
        "email_enabled", "widget_enabled", "auto_open", "auto_open_delay",
        "mode", "max_turns", "conciergeEnabled", "aiEnabled",
        "emailEnabled", "leadCollectionEnabled", "widgetEnabled",
        "autoOpenEnabled", "humanHandoffEnabled",
    }
    flags = {k: v for k, v in body.items() if k in allowed_flags}
    ai_instructions = body.get("ai_instructions")

    with connect() as c:
        existing = rows(c, "SELECT id, flags, ai_instructions FROM tenant_settings WHERE tenant_id = ?", tenant_id)
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


# ── Audit Logs Admin ─────────────────────────────────────────────────────────

@admin_app.get("/api/admin/tenants/{tenant_id}/audit")
def admin_audit_log(tenant_id: int, limit: int = 50, _: Any = Depends(require_roles("owner", "admin", "viewer"))) -> list[dict]:
    with connect() as c:
        return rows(c, "SELECT * FROM audit_logs WHERE tenant_id = ? ORDER BY id DESC LIMIT ?", tenant_id, limit)


# ── API Keys Admin ────────────────────────────────────────────────────────────

@admin_app.post("/api/admin/tenants/{tenant_id}/api-keys")
def admin_create_api_key(tenant_id: int, body: dict[str, Any], _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    from saas.repositories import create_api_key
    label = body.get("label", "default")
    secret = body.get("secret") or __import__("secrets").token_urlsafe(24)
    key = create_api_key(tenant_id, label, secret)
    return {"id": key.id, "label": key.label, "public_key": key.public_key, "secret": secret}


@admin_app.delete("/api/admin/api-keys/{key_id}")
def admin_revoke_api_key(key_id: int, _: Any = Depends(require_roles("owner", "admin"))) -> dict:
    from saas.repositories import revoke_api_key, get_api_key
    key = get_api_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="key not found")
    revoke_api_key(key_id)
    return {"ok": True}
