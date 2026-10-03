"""Seed demo data for local development."""

from __future__ import annotations

import secrets

from saas.config import get_settings
from saas.database import connect, now_iso
from saas.repositories import (
    add_domain,
    create_api_key,
    create_tenant,
    create_user,
    get_tenant_by_slug,
)
from saas.security import encrypt_value

settings = get_settings()


def seed() -> None:
    tenant = get_tenant_by_slug("raleigh-dental-demo")
    if tenant:
        print(f"Demo tenant exists: id={tenant.id}")
        return
    with connect() as c:
        tid = c.execute(
            "INSERT INTO tenants (slug, name, created_at, updated_at, metadata) VALUES (?, ?, ?, ?, ?)",
            ("raleigh-dental-demo", "Raleigh Dental Demo", now_iso(), now_iso(), "{}"),
        ).lastrowid
    tenant = get_tenant_by_slug("raleigh-dental-demo")
    print(f"Created tenant: {tenant.id} {tenant.slug}")

    create_user(tenant.id, "owner@example.com", password="password", display_name="Demo Owner", role="owner")

    api_key = create_api_key(tenant.id, "demo-site", "super-secret-demo-key")
    print(f"Created API key public={api_key.public_key}")

    secret = "super-secret-demo-key"
    enc = encrypt_value(secret)
    with connect() as c:
        c.execute(
            "INSERT INTO email_settings (tenant_id, provider, smtp_host, smtp_port, smtp_user, smtp_password_enc, from_name, from_email, reply_to, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tenant.id, "default", None, None, None, enc, "Raleigh Dental", "frontdesk@raleighdental.example", "frontdesk@raleighdental.example", now_iso()),
        )
    add_domain(tenant.id, "localhost")
    add_domain(tenant.id, "127.0.0.1")
    print("Seeded domains, owner, API key, and default email settings.")


if __name__ == "__main__":
    seed()
