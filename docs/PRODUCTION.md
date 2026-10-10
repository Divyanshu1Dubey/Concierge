# Production readiness notes

## Required configuration
See `.env.example`. At minimum in production:

| Variable | Why |
|---|---|
| `DJANGO_ENV=production` | Selects `config/settings/production.py` (DEBUG off, HTTPS, secure cookies). Without it the **development** settings run. |
| `DJANGO_SECRET_KEY` | Startup fails without a strong key. It signs JWTs and derives the key that encrypts stored SMTP passwords; rotating it invalidates sessions and stored SMTP passwords (re-enter them). |
| `DJANGO_ALLOWED_HOSTS`, `APP_PUBLIC_URL` | Host-header and CORS/CSRF origin allow-lists (no wildcards). |
| `DATABASE_URL` | Use PostgreSQL on Railway. SQLite works for a single small instance but is not backed up by the platform; migrations have only been validated on SQLite so far (see *Known limitations*). |
| `EMAIL_*` or `SMTP_*` | Staff alerts, staff replies, invites and password resets. `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD` (e.g. a Gmail app password; port 465 → SSL) are accepted as an alternative to `EMAIL_*`. Without credentials, sends fail and are reported as failed. |
| `GEMINI_API_KEY` / `GROQ_API_KEY` (optional) | AI answers to open questions. Order: Gemini (`CONCIERGE_MODEL`, then `CONCIERGE_FALLBACK_MODEL`), then Groq (`CONCIERGE_GROQ_MODEL`). Without a key the concierge runs fully rule-based. `AI_PROVIDER=none` disables AI. |
| `AI_DAILY_LIMIT_PER_PRACTICE` (optional, default 300) | Cost cap on AI replies per practice per day. |
| `SENTRY_DSN` (optional) | Error monitoring (no request bodies or user PII are sent). |
| `FRONTEND_URL` / `APP_PUBLIC_URL` | Used to build invite and password-reset links. |

**Local `.env` files.** Only AI and email keys are read from `.env` (and real environment
variables always win). Database, secret-key, host and CORS settings must be set as real
environment variables (Railway → Variables). Set `DJANGO_LOAD_ENV_FILE=false` to disable.

`ENABLE_DEMO_ACCOUNTS` must stay `false` unless you are deliberately running a public demo:
demo logins use well-known passwords.

## Start-up / migrations
```
python backend/manage.py migrate --noinput
python backend/manage.py collectstatic --noinput
gunicorn --chdir backend config.wsgi:application --bind 0.0.0.0:$PORT   --workers ${WEB_CONCURRENCY:-3} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-60} --access-logfile -
```
`seed_raleigh` (run by the Procfile) does nothing unless `ENABLE_DEMO_ACCOUNTS=true`, so
production never gets demo practices or demo logins.

**Railway, step by step**
1. New project → deploy from the GitHub repo (`nixpacks.toml` is used).
2. Add a PostgreSQL service; Railway provides `DATABASE_URL`.
3. Variables: `DJANGO_ENV=production`, `DJANGO_SECRET_KEY` (64+ random chars), `DJANGO_ALLOWED_HOSTS=<your domain>`,
   `APP_PUBLIC_URL=https://<your domain>`, `ENABLE_DEMO_ACCOUNTS=false`, email (`SMTP_*` or `EMAIL_*`), optional AI keys, optional `SENTRY_DSN`.
4. Deploy; check `https://<domain>/ready` returns `ready`.
5. Create the first agency admin inside the running container (`railway run` executes on your own machine and cannot reach the volume): `railway ssh`, then `python backend/manage.py createsuperuser`. A superuser already has agency-admin access.
6. Follow `docs/ONBOARDING.md` for each practice.

Migrations in this release are additive (new nullable columns, the `token_blacklist`
tables, and new third-party (django-allauth) migrations). One allauth migration
(`account.0008_emailaddress_unique_primary_email_fixup`) normalises email-address rows.
**Take a database backup before deploying.**

## Health checks
- `GET /health` – liveness (process + DB connectivity), 200/503
- `GET /ready` – readiness (DB reachable **and** no unapplied migrations), 200/503
Both are exempt from the HTTPS redirect for platform probes.

## Backups & recovery
- `python manage.py backup_db` writes a verified SQLite copy to `./backups/` (keeps 14). On PostgreSQL it prints the `pg_dump`/`pg_restore` commands.
- SQLite restore: stop the app, copy the chosen backup over the database file, start the app, run `migrate`.
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

## Data retention & deletion
- Patient deletion requests: practice admin → request → **Delete** (optionally with the conversation). Audit-logged without patient details.
- Retention: `python manage.py purge_old_data --days <N>` shows counts (dry run); add `--confirm` to delete conversations, requests and email threads older than N days (`DATA_RETENTION_DAYS` sets the default). Schedule it (e.g. Railway cron) once a policy is chosen.

## Accounts
- New staff get an invite email to set their own password; password reset is self-service (**Forgot password?**).
- Suspending a practice (agency → Dental Practices) blocks its staff immediately (login and existing sessions) and stops its widget.

## AI behaviour
- AI is only used for open questions; booking, emergencies and handoffs follow the deterministic flow.
- The assistant receives only the practice's configured facts and is instructed never to quote prices, insurance, availability or clinical advice; failures fall back to an honest "our front desk will help" reply.
- 15 s timeout per call, a model that fails is skipped for 10 minutes, a daily per-practice cap, and usage is logged per practice (token counts only, never message text).
