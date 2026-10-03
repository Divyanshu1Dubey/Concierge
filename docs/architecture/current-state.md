# Current State Architecture

## Overview

HeyJarvis Concierge is a multi-tenant AI chatbot platform for appointment-based businesses (currently configured for a dental clinic). It has two layers:

1. **Original Concierge** (`src/concierge/`) — single-tenant, clinic-specific, proven working logic
2. **SaaS Platform** (`src/saas/`) — multi-tenant wrapper that adds auth, tenants, dashboards, widget API

## Current Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: SQLite (two separate DBs: `data/concierge.db` for original, `data/saas.db` for SaaS)
- **Auth**: JWT (python-jose) + Argon2 password hashing (passlib)
- **AI/LLM**: Google Gemini (primary) → Gemini fallback → Groq → keyword rules (heuristic fallback)
- **Email**: SMTP with dry-run mode (saves .eml files to `outbox/sent/`)
- **Frontend**: Vanilla JS widget + static HTML dashboards
- **Package Manager**: uv (Python)
- **Testing**: pytest + httpx TestClient
- **Deployment**: Railway (railway.toml) / any Uvicorn host

## Entrypoints

| Entrypoint | File | Purpose |
|---|---|---|
| `concierge.api:app` | `src/concierge/api.py` | Original single-tenant app (port 8000) |
| `saas.main:app` | `src/saas/main.py` | Multi-tenant SaaS app (port 8002) |
| `concierge serve` | `src/concierge/cli.py` | CLI to run original app |
| `scripts/seed_demo.py` | `scripts/seed_demo.py` | Seeds demo tenant |

## API Routes

### Original Concierge (`concierge.api:app`)
- `POST /requests` — server-to-server webhook (token auth)
- `POST /public/requests` — public form (CORS, honeypot, rate limit)
- `GET /widget.js` — original form widget
- `GET /` — demo landing page
- `GET /desk` — front desk dashboard
- `GET /ops` — operations dashboard
- `GET /api/status` — SMTP/AI status
- `POST /api/simulate` — simulate intake
- `GET /api/requests` — list requests
- `GET /api/requests/{id}` — request detail
- `GET /api/requests/{id}/events` — event stream
- `GET /api/requests/{id}/slots` — slot suggestions
- `POST /api/requests/{id}/send` — send email from desk
- `POST /api/requests/{id}/dismiss` — mark done
- `GET /api/schedule` — day view
- `GET /api/confirmations` — 48h confirmation queue
- `POST /api/confirmations/send` — send confirmations
- `GET /api/patients` — patient search
- `GET /api/patients/{id}` — patient detail
- `POST /api/patients/{id}` — edit patient
- `POST /api/patients/{id}/email` — email patient
- `POST /api/patients/{id}/log` — log contact
- `GET /api/stats` — ops stats

### SaaS Platform (`saas.main:app`)
- Mounted at `/api` → `public_app`
- Mounted at `/api/admin` → `admin_app`
- `GET /health` — health check
- `GET /` — platform info
- `GET /concierge/{tenant_slug}` — hosted concierge page
- `GET /static/widget.js` — universal embeddable widget

### Public API (`public_app`)
- `GET /api/v1/public/config?client_key=` — tenant config + domain validation
- `POST /api/v1/public/conversations?client_key=` — start conversation
- `POST /api/v1/public/conversations/{id}/messages?client_key=` — send message
- `GET /api/v1/public/leads?client_key=&lead_id=` — lead status
- `GET /widget.js` — widget script

### Admin API (`admin_app`)
- `GET /api/admin/tenants` — list tenants
- `POST /api/admin/tenants/{id}/domains` — add domain
- `POST /api/admin/domains/{id}/verify` — verify domain
- `DELETE /api/admin/domains/{id}` — remove domain
- `GET /api/admin/tenants/{id}/domains` — list domains

## Database Models

### Original Concierge (`data/concierge.db`)
- `requests` — patient requests
- `events` — AI trace events
- `appointments` — bookings with column-aware segments
- `patients` — patient records
- `contacts` — contact log

### SaaS Platform (`data/saas.db`)
- `tenants` — business accounts
- `users` — team members
- `memberships` — tenant-user roles
- `domains` — allowed website domains
- `api_keys` — public/secret keys per tenant
- `widget_settings` — per-tenant widget config (JSON)
- `email_settings` — per-tenant SMTP config
- `business_rules` — per-tenant booking rules (JSON)
- `conversations` — chat conversations
- `messages` — chat messages
- `leads` — structured lead objects
- `notifications` — delivery attempts
- `analytics_events` — event tracking
- `audit_logs` — admin action log
- `tenant_settings` — flags, AI instructions, hours

## Data Flow

### Original Concierge
```
Form submission → /public/requests → receive() → triage() → rules → schedule → compose → draft
                                          ↓
                                    Front Desk reads draft, picks time, sends email
```

### SaaS Widget
```
Visitor opens widget → start conversation → send message → AI extract fields → submit → lead created → email notification
```

## Email Flow

### Original
- SMTP credentials from environment variables
- Dry-run mode: saves .eml files to `outbox/sent/`
- Front desk dashboard shows drafts with `>>> ... <<<` slot markers
- Desk replaces slot with time, hits send

### SaaS
- Per-tenant email settings (encrypted SMTP passwords)
- Default provider fallback (HeyJarvis-managed)
- Dry-run mode when no SMTP configured
- `send_lead_notification()` creates notification record (currently placeholder)

## Concierge Conversation Flow (Original)

1. Patient submits form (message + name + email + phone)
2. `receive()` stores request, creates/upserts patient
3. `triage()` classifies request type (AI chain or keyword fallback)
4. `plan_booking()` applies clinic rules
5. `schedule.suggest()` finds available slots
6. `compose()` generates email draft with `>>> ... <<<` booking slot
7. Front desk opens draft, fills time, sends

## Current Configuration Mechanism

- Original: TOML config file (`config/concierge.toml`) — hardcoded for Raleigh
- SaaS: Per-tenant JSON in `tenant_settings.flags` + `business_rules.rules`

## Current Deployment Assumptions

- Railway (nixpacks builder, uvicorn)
- Single process
- SQLite files on local disk
- No background workers (uses FastAPI BackgroundTasks)
- Port 8000 for original, 8002 for SaaS

## Current Limitations

1. Dashboard is a static stub (`admin.html`) — not functional
2. Widget is basic form + simple chat, not full conversational AI
3. No email template management UI
4. No business rules configuration UI
5. No installation guide page
6. Conversation engine doesn't use LLM for field extraction
7. No human handoff
8. No business hours configuration UI
9. Analytics events tracked but no dashboard to view them
10. No WordPress plugin
11. No iframe embed option
12. Domain validation is basic (just checks origin header)
13. No rate limiting on public widget API
14. No request ID tracking
15. No structured error responses
16. No retry logic for email delivery

## Current Tests (10 passing)

1. `test_tenant_creation` — tenant CRUD
2. `test_api_key_lifecycle` — key creation/retrieval
3. `test_domain_workflow` — add/remove domains
4. `test_enable_disable` — tenant toggle
5. `test_public_requires_client_key` — auth enforcement
6. `test_public_conversation_flow` — start + message flow
7. `test_tenant_isolation` — cross-tenant access blocked
8. `test_auth_password_flow` — password hashing/verification
9. `test_health_public` — health endpoint
10. `test_track_event_writes` — analytics persistence

## What Can Be Reused

- Original concierge pipeline (`pipeline.py`, `triage.py`, `rules.py`, `schedule.py`, `compose.py`) — proven AI triage + booking logic
- Email sending (`mailer.py`) — SMTP + dry-run
- SaaS multi-tenant models + database + auth + security
- Widget JS loader architecture
- Test infrastructure (pytest + TestClient)

## What Needs to Change

1. Build functional admin dashboard (replace stub)
2. Enhance widget to full conversational mode with AI field extraction
3. Add email template management
4. Add business rules configuration
5. Add installation guide
6. Add more tests (email, authz, widget, E2E)
7. Add rate limiting to public API
8. Add request ID tracking
9. Add human handoff
10. Add business hours UI
11. Add analytics dashboard
12. Add WordPress plugin structure
