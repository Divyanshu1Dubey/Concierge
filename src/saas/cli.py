#!/usr/bin/env python3
"""Management CLI for HeyJarvis Concierge."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path


def migrate():
    """Run database migrations."""
    print("Running migrations...")
    from saas.database import migrate, reset_schema_cache
    migrate()
    reset_schema_cache()
    print("Migrations complete.")


def seed_demo():
    """Create demo tenant with Raleigh Dental configuration."""
    print("Seeding demo tenant...")
    from saas.repositories import create_tenant, create_api_key, get_tenant_by_slug
    import json

    slug = "raleigh-dental-demo"
    if get_tenant_by_slug(slug):
        print(f"Demo tenant '{slug}' already exists.")
        return

    tenant = create_tenant(
        slug=slug,
        name="Raleigh Comprehensive and Cosmetic Dentistry",
        metadata={"type": "dental", "city": "Raleigh"}
    )

    # Create API key
    create_api_key(tenant.id, label="demo", secret="demo-secret-change-me")

    # Configure business rules
    from saas.database import connect, now_iso
    rules = json.dumps({
        "new_patient_minutes": 90,
        "new_patient_structure": {"doctor": 30, "hygiene": 60},
        "emergency_minutes": 60,
        "emergency_same_day": True,
        "doctor_columns": 2,
        "hygiene_columns": 1,
        "confirmation_hours": 48,
        "no_show_fee": "$65",
        "financing": ["Cherry", "CareCredit"],
    })
    email_settings = json.dumps({
        "greeting": "Hi! How can we help you today?",
        "mode": "chatbot",
        "auto_open": False,
        "auto_open_delay": 0,
    })

    with connect() as c:
        c.execute(
            "INSERT INTO business_rules (tenant_id, rules, updated_at) VALUES (?, ?, ?)",
            (tenant.id, rules, now_iso())
        )
        c.execute(
            "INSERT INTO tenant_settings (tenant_id, flags, updated_at) VALUES (?, ?, ?)",
            (tenant.id, email_settings, now_iso())
        )

    print(f"Demo tenant created: {tenant.name}")
    print(f"  Slug: {tenant.slug}")
    print(f"  Tenant ID: {tenant.id}")


def build_wordpress():
    """Package the WordPress plugin into a distributable ZIP."""
    print("Building WordPress plugin ZIP...")
    ROOT = Path(__file__).resolve().parent.parent.parent
    plugin_dir = ROOT / "wordpress" / "heyjarvis-concierge"
    dist_dir = ROOT / "dist"
    dist_dir.mkdir(exist_ok=True)
    out_path = dist_dir / "heyjarvis-concierge.zip"

    if not plugin_dir.exists():
        print(f"Plugin directory not found: {plugin_dir}")
        sys.exit(1)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in plugin_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(plugin_dir))
    buf.seek(0)
    out_path.write_bytes(buf.read())
    print(f"Plugin ZIP created: {out_path}")
    print(f"  Size: {out_path.stat().st_size:,} bytes")


def reset_db():
    """Reset database (DESTRUCTIVE)."""
    confirm = input("This will DELETE ALL DATA. Type 'yes' to confirm: ")
    if confirm != "yes":
        print("Cancelled.")
        return
    from saas.database import reset_database
    reset_database()
    print("Database reset complete.")


def onboard():
    """Create a clinic: tenant, owner login, widget key, allowed domains. Prints the snippet to paste."""
    import argparse
    import secrets as _secrets

    from saas.config import get_settings
    from saas.repositories import add_domain, create_api_key, create_tenant, create_user, get_tenant_by_slug, verify_domain

    ap = argparse.ArgumentParser(prog="heyjarvis onboard")
    ap.add_argument("--slug", required=True, help="clinic id used to log in, e.g. raleigh-dentistry")
    ap.add_argument("--name", required=True, help="clinic name patients see")
    ap.add_argument("--owner-email", required=True, help="front desk owner's login email")
    ap.add_argument("--domain", action="append", default=[], help="website domain (repeatable), e.g. raleighdentistry.com")
    args = ap.parse_args(sys.argv[2:])

    if get_tenant_by_slug(args.slug):
        print(f"Clinic '{args.slug}' already exists. Nothing changed.")
        sys.exit(1)
    tenant = create_tenant(slug=args.slug, name=args.name)
    # No password: staff log in with a code emailed to them.
    create_user(tenant.id, args.owner_email.strip().lower(), display_name="Owner", password=None, role="owner")
    key = create_api_key(tenant.id, "website", _secrets.token_urlsafe(24))
    domains = []
    for d in args.domain:
        d = d.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
        for host in dict.fromkeys([d, d[4:] if d.startswith("www.") else "www." + d]):
            dom = add_domain(tenant.id, host)
            verify_domain(dom.id)
            domains.append(host)

    app_url = get_settings().app_url.rstrip("/")
    print(f"""
Clinic created: {args.name} (id {tenant.id})

Front desk:   {app_url}/frontdesk?clinic={args.slug}
  Clinic ID:  {args.slug}
  Login:      {args.owner_email}  (click "Email me a login code"; no password)
Domains:      {', '.join(domains) or '(none - add with --domain)'}
Hosted chat:  {app_url}/concierge/{args.slug}

Website snippet (paste before </body> on every page):

<script async src="{app_url}/widget.js" data-heyjarvis-client="{key.public_key}"></script>
""")


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python -m saas.cli <command>")
        print("Commands: onboard, migrate, seed-demo, build-wordpress, reset-db")
        sys.exit(1)

    command = sys.argv[1]
    commands = {
        "onboard": onboard,
        "migrate": migrate,
        "seed-demo": seed_demo,
        "build-wordpress": build_wordpress,
        "reset-db": reset_db,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(commands.keys())}")
        sys.exit(1)

    commands[command]()


if __name__ == "__main__":
    main()
