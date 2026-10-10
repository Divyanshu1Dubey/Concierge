# Production readiness notes

## Required configuration
See `.env.example`. At minimum in production:

| Variable | Why |
|---|---|
| `DJANGO_ENV=production` | Selects `config/settings/production.py` (DEBUG off, HTTPS, secure cookies). Without it the **development** settings run. |
| `DJANGO_SECRET_KEY` | Startup fails without a strong key. It signs JWTs and derives the key that encrypts stored SMTP passwords; rotating it invalidates sessions and stored SMTP passwords (re-enter them). |
| `DJANGO_ALLOWED_HOSTS`, `APP_PUBLIC_URL` | Host-header and CORS/CSRF origin allow-lists (no wildcards). |
| `DATABASE_URL` | Use PostgreSQL. SQLite is for local development only. |
| `EMAIL_*` | Staff notifications and practice email. Without SMTP, sends fail and are reported as failed (never shown as delivered). |

`ENABLE_DEMO_ACCOUNTS` must stay `false` unless you are deliberately running a public demo:
demo logins use well-known passwords.

## Start-up / migrations
```
python backend/manage.py migrate --noinput
python backend/manage.py collectstatic --noinput
gunicorn --chdir backend config.wsgi:application --bind 0.0.0.0:$PORT
```
`seed_raleigh` (run by the Procfile) only creates the demo practices; it creates demo user
accounts only when `ENABLE_DEMO_ACCOUNTS=true`.

Migrations in this release are additive (new nullable columns, the `token_blacklist`
tables, and new third-party (django-allauth) migrations). One allauth migration
(`account.0008_emailaddress_unique_primary_email_fixup`) normalises email-address rows.
**Take a database backup before deploying.**

## Health checks
- `GET /health` – liveness (process + DB connectivity), 200/503
- `GET /ready` – readiness (DB reachable **and** no unapplied migrations), 200/503
Both are exempt from the HTTPS redirect for platform probes.

## Backups & recovery
- Enable automated daily PostgreSQL backups (point-in-time recovery if available) and test a restore.
- Before every deploy that includes migrations: take an on-demand snapshot.
- Restore: provision a new database from the snapshot, point `DATABASE_URL` at it, run `migrate`.

## Tests
```
cd backend && python -m pytest          # unit/API/tenant-isolation suite (config.settings.testing)
cd frontend && npx tsc --noEmit && npm run build
python scripts/e2e_smoke.py             # browser smoke test against a LOCAL dev server only
```

## Healthcare / HIPAA
The code now enforces tenant isolation, role-based access, audit logging of
administrative actions, secret redaction, and encrypted SMTP credentials. That is
**not** HIPAA compliance by itself. Before handling real PHI you still need, at least:
signed BAAs with the hosting provider, database/backup provider, email/SMTP provider and
any AI provider that receives patient messages; encryption at rest on the database and
backups; documented data-retention and deletion procedures (there is currently no
automated retention/purge job); access-review and incident-response policies; and a
risk assessment. Patient chat content is sent to the configured AI provider when one is set.

## Known limitations
- Frontend uses react-router 6.x, which has two moderate advisories (open redirect via
  backslash paths in `<Link>`/`navigate` with untrusted input, and an SSR-only issue). The
  app does not navigate to user-controlled paths or use SSR; upgrading to v7 is a breaking change.
- JWTs are stored in `localStorage` (XSS would expose them). There is no
  `dangerouslySetInnerHTML` in the app, but an httpOnly-cookie session would be stronger.
- No account lockout beyond IP-based login throttling; no MFA.
- Rate limits use the Django cache; set `REDIS_URL` so limits are shared across workers.
- Gmail/Outlook provider classes in `apps/emails/providers.py` are unimplemented stubs
  (not used by any flow); email goes through SMTP / Django's email backend.
