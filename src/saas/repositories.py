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


def create_user(tenant_id: int, email: str, password: str | None = None, display_name: str | None = None,
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


def get_templates(tenant_id: int) -> list[dict]:
    with connect() as c:
        return rows(c, "SELECT * FROM email_templates WHERE tenant_id = ?", tenant_id)


def _json(value: Any) -> str:
    import json
    return json.dumps(value or {})


def _loads(raw: str) -> dict[str, Any]:
    import json
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}
