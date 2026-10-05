"""Repositories for SaaS entities."""

from __future__ import annotations

import secrets
from typing import Any

from saas.database import connect, insert, now_iso, row, rows
from saas.models import ApiKey, Domain, Tenant, User
from saas.security import hash_password


# --- tenants ---------------------------------------------------------------------------


def create_tenant(slug: str, name: str, metadata: dict[str, Any] | None = None) -> Tenant:
    with connect() as c:
        tid = c.execute("INSERT INTO tenants (slug, name, created_at, updated_at, metadata) VALUES (?, ?, ?, ?, ?)",
                        (slug, name, now_iso(), now_iso(), _json(metadata))).lastrowid
    return get_tenant(tid)


def get_tenant(tid: int) -> Tenant | None:
    with connect() as c:
        r = row(c, "SELECT * FROM tenants WHERE id = ?", tid)
    return _tenant_from(r) if r else None


def get_tenant_by_slug(slug: str) -> Tenant | None:
    with connect() as c:
        r = row(c, "SELECT * FROM tenants WHERE slug = ?", slug)
    return _tenant_from(r) if r else None


def _tenant_from(r: dict) -> Tenant:
    return Tenant(id=r["id"], slug=r["slug"], name=r["name"], enabled=bool(r["enabled"]), plan=r["plan"],
                  metadata=_loads(r["metadata"]))


def update_tenant(tid: int, **fields) -> None:
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [tid]
    with connect() as c:
        c.execute(f"UPDATE tenants SET {sets} WHERE id = ?", vals)


def list_tenants(limit: int = 100, offset: int = 0) -> list[Tenant]:
    with connect() as c:
        return [_tenant_from(r) for r in rows(c, "SELECT * FROM tenants ORDER BY id LIMIT ? OFFSET ?", limit, offset)]


# --- users / memberships ---------------------------------------------------------------------------


def create_user(tenant_id: int, email: str, display_name: str | None = None, password: str | None = None,
                role: str = "owner") -> User:
    with connect() as c:
        uid = c.execute(
            "INSERT INTO users (tenant_id, email, display_name, hashed_password, role, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, email, display_name, hash_password(password) if password else None, role, now_iso(), now_iso())
        ).lastrowid
        c.execute("INSERT OR IGNORE INTO memberships (tenant_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
                  (tenant_id, uid, role, now_iso()))
    return get_user(uid)


def get_user(uid: int) -> User | None:
    with connect() as c:
        r = row(c, "SELECT * FROM users WHERE id = ?", uid)
    return _user_from(r) if r else None


def get_user_by_email(tenant_id: int, email: str) -> User | None:
    with connect() as c:
        r = row(c, "SELECT * FROM users WHERE tenant_id = ? AND lower(email) = lower(?)", tenant_id, email)
    return _user_from(r) if r else None


def _user_from(r: dict) -> User:
    return User(id=r["id"], tenant_id=r["tenant_id"], email=r["email"], display_name=r["display_name"],
                hashed_password=r.get("hashed_password"), role=r["role"], metadata=_loads(r["metadata"]))


# --- domains ---------------------------------------------------------------------------


def add_domain(tenant_id: int, domain: str) -> Domain:
    with connect() as c:
        did = c.execute("INSERT INTO domains (tenant_id, domain, created_at) VALUES (?, ?, ?)",
                        (tenant_id, domain.strip().lower(), now_iso())).lastrowid
    return get_domain(did)


def list_domains(tenant_id: int) -> list[Domain]:
    with connect() as c:
        return [Domain(id=r["id"], tenant_id=r["tenant_id"], domain=r["domain"], verified=bool(r["verified"]))
                for r in rows(c, "SELECT * FROM domains WHERE tenant_id = ? ORDER BY id", tenant_id)]


def get_domain(did: int) -> Domain | None:
    with connect() as c:
        r = row(c, "SELECT * FROM domains WHERE id = ?", did)
    return Domain(id=r["id"], tenant_id=r["tenant_id"], domain=r["domain"], verified=bool(r["verified"])) if r else None


def verify_domain(did: int) -> None:
    with connect() as c:
        c.execute("UPDATE domains SET verified = 1 WHERE id = ?", (did,))


def remove_domain(did: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM domains WHERE id = ?", (did,))


# --- API keys ---------------------------------------------------------------------------


def create_api_key(tenant_id: int, label: str, secret: str) -> ApiKey:
    public = _public_key()
    secret_hash = hash_password(secret)
    with connect() as c:
        kid = c.execute(
            "INSERT INTO api_keys (tenant_id, label, public_key, secret_key_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (tenant_id, label, public, secret_hash, now_iso())).lastrowid
    return get_api_key(kid)


def get_api_key(kid: int) -> ApiKey | None:
    with connect() as c:
        r = row(c, "SELECT * FROM api_keys WHERE id = ?", kid)
    return _api_key_from(r) if r else None


def get_api_key_by_public(public_key: str) -> ApiKey | None:
    with connect() as c:
        r = row(c, "SELECT * FROM api_keys WHERE public_key = ?", public_key)
    return _api_key_from(r) if r else None


def revoke_api_key(kid: int) -> None:
    with connect() as c:
        c.execute("UPDATE api_keys SET revoked_at = ? WHERE id = ?", (now_iso(), kid))


def _api_key_from(r: dict) -> ApiKey:
    return ApiKey(id=r["id"], tenant_id=r["tenant_id"], label=r["label"], public_key=r["public_key"],
                  secret_key_hash=r["secret_key_hash"], last_used_at=r["last_used_at"], revoked_at=r["revoked_at"])


def _public_key() -> str:
    return "pk_" + secrets.token_urlsafe(18)


# --- conversations / leads / analytics ---------------------------------------------------------------------------


def create_conversation(tenant_id: int, page_url: str | None, referrer: str | None, user_agent: str | None,
                        visitor_id: str | None) -> dict:
    with connect() as c:
        cid = insert(c, "conversations", tenant_id=tenant_id, visitor_id=visitor_id, page_url=page_url,
                     referrer=referrer, user_agent=user_agent, created_at=now_iso(), updated_at=now_iso())
    return {"id": cid, "tenant_id": tenant_id}


def append_message(conversation_id: int, role: str, body: str, metadata: dict[str, Any] | None = None) -> dict:
    with connect() as c:
        mid = insert(c, "messages", conversation_id=conversation_id, role=role, body=body, created_at=now_iso(),
                     metadata=_json(metadata))
    return {"id": mid, "conversation_id": conversation_id, "role": role, "body": body}


def complete_conversation(conversation_id: int, summary: str | None, status: str = "completed") -> None:
    with connect() as c:
        c.execute("UPDATE conversations SET status = ?, summary = ?, updated_at = ? WHERE id = ?",
                  (status, summary, now_iso(), conversation_id))


def create_lead(tenant_id: int, lead: dict[str, Any]) -> dict:
    with connect() as c:
        lid = insert(c, "leads", tenant_id=tenant_id, conversation_id=lead.get("conversation_id"), name=lead.get("name"),
                     email=lead.get("email"), phone=lead.get("phone"), intent=lead.get("intent"), service=lead.get("service"),
                     urgency=lead.get("urgency"), preferred_date=lead.get("preferredDate"), preferred_time=lead.get("preferredTime"),
                     insurance=lead.get("insurance"), financing=lead.get("financing"), message=lead.get("message"),
                     conversation_summary=lead.get("conversationSummary"), source=lead.get("source"), page_url=lead.get("pageUrl"),
                     status=lead.get("status", "new"), created_at=now_iso(), updated_at=now_iso(), metadata=_json(lead.get("metadata")))
    return {"id": lid, "tenant_id": tenant_id}


def list_leads(tenant_id: int, status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    sql = "SELECT * FROM leads WHERE tenant_id = ?"
    args: list[Any] = [tenant_id]
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    args.extend([limit, offset])
    with connect() as c:
        return rows(c, sql, *args)


def update_lead(lid: int, **fields) -> None:
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [lid]
    with connect() as c:
        c.execute(f"UPDATE leads SET {sets} WHERE id = ?", vals)


def track_event(tenant_id: int, event: str, payload: dict[str, Any] | None = None) -> None:
    with connect() as c:
        insert(c, "analytics_events", tenant_id=tenant_id, event=event, payload=_json(payload), created_at=now_iso())


def audit(tenant_id: int | None, actor_user_id: int | None, action: str, metadata: dict[str, Any] | None = None) -> None:
    with connect() as c:
        insert(c, "audit_logs", tenant_id=tenant_id, actor_user_id=actor_user_id, action=action,
               metadata=_json(metadata), created_at=now_iso())


# --- helpers ---------------------------------------------------------------------------


def get_lead(lid: int) -> dict | None:
    with connect() as c:
        return row(c, "SELECT * FROM leads WHERE id = ?", lid)


def get_conversation(conv_id: int) -> dict | None:
    with connect() as c:
        return row(c, "SELECT * FROM conversations WHERE id = ?", conv_id)


def get_tenant_email(tenant_id: int) -> dict | None:
    with connect() as c:
        r = row(c, "SELECT * FROM email_settings WHERE tenant_id = ?", tenant_id)
    if not r:
        return None
    return {
        "from_name": r.get("from_name"),
        "from_email": r.get("from_email"),
        "reply_to": r.get("reply_to"),
        "front_desk_email": r.get("front_desk_email"),
        "backup_email": r.get("backup_email"),
        "smtp_host": r.get("smtp_host"),
        "smtp_port": r.get("smtp_port"),
        "smtp_username": r.get("smtp_user"),
        "smtp_password": r.get("smtp_password_enc"),
        "smtp_security": r.get("provider", "tls"),
    }


def get_notification(nid: int) -> dict | None:
    with connect() as c:
        r = row(c, "SELECT * FROM notifications WHERE id = ?", nid)
    return r


def create_notification(tenant_id: int, lead_id: int, channel: str, status: str, payload: dict | None = None, error: str | None = None) -> dict:
    with connect() as c:
        nid = insert(c, "notifications", tenant_id=tenant_id, lead_id=lead_id, channel=channel, status=status,
                     payload=_json(payload), error=error or "", created_at=now_iso(), sent_at=now_iso() if status == "sent" else None)
    return {"id": nid, "tenant_id": tenant_id, "status": status}


def get_templates(tenant_id: int) -> list[dict]:
    with connect() as c:
        return rows(c, "SELECT * FROM email_templates WHERE tenant_id = ?", tenant_id)


def create_or_update_email(tenant_id: int, **fields) -> None:
    fields["updated_at"] = now_iso()
    with connect() as c:
        existing = rows(c, "SELECT id FROM email_settings WHERE tenant_id = ?", tenant_id)
        if existing:
            sets = ", ".join(f"{k} = ?" for k in fields)
            vals = list(fields.values()) + [tenant_id]
            c.execute(f"UPDATE email_settings SET {sets} WHERE tenant_id = ?", vals)
        else:
            keys = ", ".join(["tenant_id"] + list(fields.keys()) + ["updated_at"])
            marks = ", ".join(["?"] * (len(fields) + 2))
            c.execute(f"INSERT INTO email_settings ({keys}) VALUES ({marks})", [tenant_id] + list(fields.values()) + [now_iso()])


def create_or_update_business_rules(tenant_id: int, rules: dict[str, Any]) -> dict:
    import json as _json
    payload = _json.dumps(rules or {})
    with connect() as c:
        existing = rows(c, "SELECT id FROM business_rules WHERE tenant_id = ?", tenant_id)
        now = now_iso()
        if existing:
            c.execute("UPDATE business_rules SET rules = ?, updated_at = ? WHERE tenant_id = ?", (payload, now, tenant_id))
        else:
            c.execute("INSERT INTO business_rules (tenant_id, rules, updated_at) VALUES (?, ?, ?)", (tenant_id, payload, now))
    return rules


def get_business_rules(tenant_id: int) -> dict | None:
    with connect() as c:
        r = row(c, "SELECT rules FROM business_rules WHERE tenant_id = ?", tenant_id)
    if not r:
        return None
    import json as _json
    try:
        return _json.loads(r["rules"] or "{}")
    except Exception:
        return {}


# ── Front Desk ─────────────────────────────────────────────────────────────

def create_frontdesk_note(tenant_id: int, note: str, lead_id: int | None = None,
                          conversation_id: int | None = None, created_by: int | None = None) -> dict:
    now = now_iso()
    with connect() as c:
        cur = c.execute(
            "INSERT INTO frontdesk_notes (tenant_id, lead_id, conversation_id, note, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, lead_id, conversation_id, note, created_by, now, now),
        )
        nid = cur.lastrowid
        return row(c, "SELECT * FROM frontdesk_notes WHERE id = ?", nid)


def get_frontdesk_notes(tenant_id: int, lead_id: int | None = None, limit: int = 50) -> list[dict]:
    with connect() as c:
        if lead_id is not None:
            return rows(c,
                "SELECT * FROM frontdesk_notes WHERE tenant_id = ? AND lead_id = ? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, lead_id, limit))
        return rows(c,
            "SELECT * FROM frontdesk_notes WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit))


def create_frontdesk_task(tenant_id: int, title: str, priority: str = "medium",
                          lead_id: int | None = None, description: str | None = None,
                          due_at: str | None = None, created_by: int | None = None) -> dict:
    now = now_iso()
    with connect() as c:
        cur = c.execute(
            "INSERT INTO frontdesk_tasks (tenant_id, lead_id, title, description, priority, status, due_at, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)",
            (tenant_id, lead_id, title, description, priority, due_at, created_by, now, now),
        )
        tid = cur.lastrowid
        return row(c, "SELECT * FROM frontdesk_tasks WHERE id = ?", tid)


def get_frontdesk_tasks(tenant_id: int, status: str | None = None, limit: int = 50) -> list[dict]:
    with connect() as c:
        if status:
            return rows(c,
                "SELECT * FROM frontdesk_tasks WHERE tenant_id = ? AND status = ? ORDER BY "
                "CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, "
                "due_at IS NOT NULL DESC, created_at DESC LIMIT ?",
                (tenant_id, status, limit))
        return rows(c,
            "SELECT * FROM frontdesk_tasks WHERE tenant_id = ? ORDER BY "
            "CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, "
            "due_at IS NOT NULL DESC, created_at DESC LIMIT ?",
            (tenant_id, limit))


def complete_frontdesk_task(task_id: int, tenant_id: int) -> dict | None:
    now = now_iso()
    with connect() as c:
        r = row(c, "SELECT * FROM frontdesk_tasks WHERE id = ? AND tenant_id = ?", task_id, tenant_id)
        if not r:
            return None
        c.execute("UPDATE frontdesk_tasks SET status = 'completed', completed_at = ?, updated_at = ? WHERE id = ?",
                  (now, now, task_id))
        return row(c, "SELECT * FROM frontdesk_tasks WHERE id = ?", task_id)


def create_ai_draft(tenant_id: int, lead_id: int | None = None, conversation_id: int | None = None,
                    subject: str | None = None, body: str = "", html_body: str | None = None) -> dict:
    now = now_iso()
    with connect() as c:
        cur = c.execute(
            "INSERT INTO ai_drafts (tenant_id, lead_id, conversation_id, subject, body, html_body, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (tenant_id, lead_id, conversation_id, subject, body, html_body, now, now),
        )
        did = cur.lastrowid
        return row(c, "SELECT * FROM ai_drafts WHERE id = ?", did)


def get_ai_drafts(tenant_id: int, lead_id: int | None = None, status: str | None = None,
                  limit: int = 50) -> list[dict]:
    with connect() as c:
        q = "SELECT * FROM ai_drafts WHERE tenant_id = ?"
        params: list = [tenant_id]
        if lead_id is not None:
            q += " AND lead_id = ?"
            params.append(lead_id)
        if status is not None:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return rows(c, q, tuple(params))


def mark_draft_sent(draft_id: int, tenant_id: int) -> dict | None:
    now = now_iso()
    with connect() as c:
        r = row(c, "SELECT * FROM ai_drafts WHERE id = ? AND tenant_id = ?", draft_id, tenant_id)
        if not r:
            return None
        c.execute("UPDATE ai_drafts SET status = 'sent', sent_at = ?, updated_at = ? WHERE id = ?",
                  (now, now, draft_id))
        return row(c, "SELECT * FROM ai_drafts WHERE id = ?", draft_id)


def mark_draft_failed(draft_id: int, tenant_id: int, error: str) -> dict | None:
    now = now_iso()
    with connect() as c:
        r = row(c, "SELECT * FROM ai_drafts WHERE id = ? AND tenant_id = ?", draft_id, tenant_id)
        if not r:
            return None
        c.execute("UPDATE ai_drafts SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                  (error, now, draft_id))
        return row(c, "SELECT * FROM ai_drafts WHERE id = ?", draft_id)


def get_frontdesk_dashboard(tenant_id: int) -> dict:
    with connect() as c:
        total_conv = row(c, "SELECT COUNT(*) AS n FROM conversations WHERE tenant_id = ?", tenant_id)["n"]
        new_leads = row(c, "SELECT COUNT(*) AS n FROM leads WHERE tenant_id = ? AND status = 'new'", tenant_id)["n"]
        contacted = row(c, "SELECT COUNT(*) AS n FROM leads WHERE tenant_id = ? AND status = 'contacted'", tenant_id)["n"]
        booked = row(c, "SELECT COUNT(*) AS n FROM leads WHERE tenant_id = ? AND status = 'booked'", tenant_id)["n"]
        pending_drafts = row(c, "SELECT COUNT(*) AS n FROM ai_drafts WHERE tenant_id = ? AND status = 'pending'", tenant_id)["n"]
        open_tasks = row(c, "SELECT COUNT(*) AS n FROM frontdesk_tasks WHERE tenant_id = ? AND status = 'open'", tenant_id)["n"]
        overdue_tasks = row(c,
            "SELECT COUNT(*) AS n FROM frontdesk_tasks WHERE tenant_id = ? AND status = 'open' AND due_at IS NOT NULL AND due_at < ?",
            (tenant_id, now_iso()))
        total_notes = row(c, "SELECT COUNT(*) AS n FROM frontdesk_notes WHERE tenant_id = ?", tenant_id)["n"]

        intents_rows = rows(c,
            "SELECT intent, COUNT(*) AS cnt FROM leads WHERE tenant_id = ? AND intent IS NOT NULL GROUP BY intent ORDER BY cnt DESC LIMIT 5",
            (tenant_id,))
        top_intents = [r["intent"] for r in intents_rows]

        insights: list[str] = []
        if new_leads > 0:
            insights.append(f"{new_leads} new lead{'s' if new_leads != 1 else ''} awaiting response")
        if int(overdue_tasks["n"]) > 0:
            insights.append(f"{overdue_tasks['n']} overdue task{'s' if int(overdue_tasks['n']) != 1 else ''}")
        if pending_drafts > 0:
            insights.append(f"{pending_drafts} AI draft{'s' if pending_drafts != 1 else ''} ready to send")

    return {
        "tenant_id": tenant_id,
        "total_conversations": total_conv,
        "new_leads": new_leads,
        "contacted_leads": contacted,
        "booked_leads": booked,
        "pending_drafts": pending_drafts,
        "open_tasks": open_tasks,
        "overdue_tasks": int(overdue_tasks["n"]),
        "total_notes": total_notes,
        "top_intents": top_intents,
        "insights": insights,
    }


def get_fd_lead_detail(tenant_id: int, lead_id: int) -> dict | None:
    with connect() as c:
        lead = row(c, "SELECT * FROM leads WHERE id = ? AND tenant_id = ?", lead_id, tenant_id)
        if not lead:
            return None
        conv = None
        if lead.get("conversation_id"):
            conv = row(c, "SELECT * FROM conversations WHERE id = ?", lead["conversation_id"])
        msgs = []
        if conv:
            msgs = rows(c, "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC", conv["id"])
        notes = rows(c, "SELECT * FROM frontdesk_notes WHERE lead_id = ? ORDER BY created_at DESC", lead_id)
        tasks = rows(c, "SELECT * FROM frontdesk_tasks WHERE lead_id = ? ORDER BY created_at DESC", lead_id)
        drafts = rows(c, "SELECT * FROM ai_drafts WHERE lead_id = ? ORDER BY created_at DESC", lead_id)
        return {
            "lead": lead,
            "conversation": conv,
            "messages": msgs,
            "notes": notes,
            "tasks": tasks,
            "drafts": drafts,
        }


def save_template(tenant_id: int, name: str, subject: str, body: str) -> None:
    import json as _json
    now = now_iso()
    with connect() as c:
        existing = rows(c, "SELECT id FROM tenant_settings WHERE tenant_id = ? AND key = 'email_templates'", tenant_id)
        if existing:
            current = {}
            try:
                current = _json.loads(existing[0].get("value") or "{}")
            except Exception:
                pass
            current[name] = {"subject": subject, "body": body}
            c.execute("UPDATE tenant_settings SET value = ?, updated_at = ? WHERE tenant_id = ? AND key = 'email_templates'",
                      (_json.dumps(current), now, tenant_id))
        else:
            c.execute("INSERT INTO tenant_settings (tenant_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
                      (tenant_id, "email_templates", _json.dumps({name: {"subject": subject, "body": body}}), now))


def _json(value: Any) -> str:
    import json
    return json.dumps(value or {})


def _loads(raw: str) -> dict[str, Any]:
    import json
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}
