# HeyJarvis Concierge — Current State Architecture

## Project Structure

```
concierge/
  src/saas/
    __init__.py
    auth.py              — JWT auth, roles, login
    ai_engine.py         — Gemini/Groq LLM helpers (draft_reply, summarize, classify, etc.)
    conversation.py      — ConversationEngine, state machine, field extraction
    config.py            — Settings (env vars, defaults)
    database.py          — SQLite schema, connect/row/rows helpers, now_iso
    emailer.py           — SMTP sending, test_smtp_connection, send_test_email
    email_templates.py   — Template rendering
    models.py            — SQLAlchemy-style Tenant, User, Conversation, Lead models
    public_api.py        — Public-facing API (widget, chat, embedding)
    admin_api.py         — Admin API (tenant management, dashboard pages)
    repositories.py      — Database CRUD for tenants, users, leads, conversations, etc.
    templates/
      frontdesk.html     — Single-file front desk dashboard (fetches /fd/*)
      admin.html         — Admin dashboard
      install.html       — Installation guide
  test_saas.py           — Integration tests for conversation, leads, auth
  test_saas_admin.py     — Admin API tests
  test_saas_email.py     — Email tests
  test_saas_widget.py    — Widget loading tests
```

## Current Architecture

### Two-FastAPI-App Pattern

- `public_app` — Public-facing API for widget/embed, mounted at `/`
- `admin_app` — Admin/front desk API, mounted at `/api/admin`
- Both in `src/saas/public_api.py`

### Middleware

- CORS enabled on public_app
- JWT auth via OAuth2PasswordBearer
- Role-based access: owner, admin, viewer, agent

## Major Modules

### 1. Auth (`auth.py`)
- JWT-based authentication
- Role system: owner, admin, viewer, agent
- `get_current` dependency for protected routes
- `require_roles` for role-gated endpoints
- Tenant-scoped: users belong to a tenant

### 2. Conversation Engine (`conversation.py`)
- State machine with states: STARTED, IDENTIFYING_INTENT, COLLECTING_INFORMATION, QUALIFYING, CONFIRMING, SUBMITTING, HANDOFF, CLOSED
- `ConversationEngine` orchestrates multi-turn conversations
- `ConversationContext` holds per-conversation state
- `FieldDef` defines configurable fields (type, required, hidden, AI-detectable)
- Deterministic backend controls required fields and validation
- AI assists with intent detection and field extraction

### 3. AI Engine (`ai_engine.py`)
- Provider chain: Gemini primary, Groq fallback, noop fallback
- Functions:
  - `draft_reply()` — generates front desk email drafts
  - `summarize_conversation()` — extracts structured data from conversation
  - `classify_message()` — detects intent and urgency
  - `parse_time_instruction()` — natural language time parsing
  - `generate_follow_up()` — follow-up email generation
  - `next_best_action()` — recommends front desk actions
- All AI calls go through a provider chain with fallback

### 4. Email System (`emailer.py`, `email_templates.py`)
- Tenant-level email settings (SMTP or HeyJarvis default)
- `send_lead_notification()` — sends lead notification emails
- `send_test_email()` — tests email delivery
- `test_smtp_connection()` — validates SMTP config
- Template engine with `{{variable}}` syntax
- HTML and plain-text support

### 5. Repositories (`repositories.py`)
- SQLite-based CRUD
- Functions for: tenants, users, domains, API keys, conversations, messages, leads, notifications, templates, business rules, settings

## API Routes

### Public API (public_app)
- `GET /widget.js` — Widget JavaScript bundle
- `POST /api/chat` — Chat message endpoint (widget conversations)
- `POST /api/conversations` — Create conversation
- `POST /api/conversations/{id}/messages` — Append message
- `GET /api/conversations/{id}` — Get conversation
- `POST /api/auth/login` — JWT login
- `POST /api/auth/token` — OAuth2 token endpoint
- `GET /api/health` — Health check

### Admin API (admin_app, mounted at /api/admin)
- `POST /api/admin/auth/login` — Admin login
- `GET /api/admin/dashboard/{tenant_id}` — Dashboard stats
- `GET/PUT /api/admin/tenants/{tenant_id}/widget` — Widget config
- `GET/PUT /api/admin/tenants/{tenant_id}/email` — Email settings
- `POST /api/admin/tenants/{tenant_id}/email/test` — Test email
- `POST /api/admin/tenants/{tenant_id}/email/test-smtp` — Test SMTP
- `GET /api/admin/tenants/{tenant_id}/templates` — List templates
- `PUT /api/admin/tenants/{tenant_id}/templates/{name}` — Update template
- `GET /api/admin/template-variables` — Available template variables
- `GET/PUT /api/admin/tenants/{tenant_id}/business-rules` — Business rules
- `GET/PUT /api/admin/tenants/{tenant_id}/settings` — Tenant settings
- `GET /api/admin/tenants/{tenant_id}/members` — Team members
- `POST /api/admin/tenants/{tenant_id}/members` — Add member
- `GET/POST /api/admin/conversations` — List/create conversations
- `GET /api/admin/conversations/{id}/messages` — Get messages
- `GET /api/admin/leads` — List leads
- `GET /api/admin/tenants/{tenant_id}/audit` — Audit log
- `POST /api/admin/tenants/{tenant_id}/api-keys` — Create API key
- `DELETE /api/admin/api-keys/{key_id}` — Revoke API key
- `GET /api/admin/tenants/{tenant_id}/integration/wordpress` — WordPress plugin download

## Database Models

### Core Tables
- `tenants` — Multi-tenant root (slug, name, plan, enabled, metadata)
- `users` — User accounts (role-based, hashed_password)
- `memberships` — Tenant-user relationships
- `domains` — Verified domains per tenant
- `api_keys` — Public/secret key pairs for embed authentication

### Conversation Tables
- `conversations` — Chat sessions (tenant-scoped, status, summary, metadata)
- `messages` — Individual messages in conversations (role, body, metadata)
- `conversation_fields` — Extracted structured fields per conversation (field_key, field_value)

### Lead Tables
- `leads` — Structured lead data (name, email, phone, intent, service, urgency, preferred_date/time, insurance, financing, message, conversation_summary, source, status)
- `notifications` — Email delivery tracking (channel, status, payload, error, sent_at)

### Configuration Tables
- `widget_settings` — Per-tenant widget configuration (config JSON)
- `email_settings` — SMTP/default email config (provider, smtp_*, from_*, delivery_mode)
- `business_rules` — JSON blob of tenant-specific rules
- `tenant_settings` — Flags, AI instructions, business hours
- `email_templates` — Per-tenant email templates (name, subject, body, intent)
- `integration_settings` — Webhook/CRM config

### Front Desk Tables
- `frontdesk_notes` — Notes on leads/conversations
- `frontdesk_tasks` — Follow-up task tracking
- `ai_drafts` — AI-generated email drafts (pending/sent/failed)

### Analytics
- `analytics_events` — Event tracking
- `audit_logs` — Audit trail

## Data Flow

```
Visitor → Website → Widget loads (widget.js)
  → Creates/joins conversation (public API)
  → Messages exchanged (AI-assisted state machine)
  → Fields extracted (intent, name, email, phone, etc.)
  → Lead created when sufficient data collected
  → Notification sent to front desk (email/webhook)
  → Front desk views/manages in dashboard (/fd/*)
  → AI drafts reply → front desk reviews/sends
```

## Concierge Conversation Flow

1. Widget loads on visitor's browser
2. Visitor sends first message
3. Engine creates conversation (if needed)
4. AI classifies intent and urgency
5. State machine progresses through required field collection
6. AI extracts fields from free-form responses
7. Duplicate field detection (avoids re-asking)
8. Lead created when form-equivalent data collected
9. Notification dispatched to front desk
10. Conversation enters CONFIRMING/SUBMITTING state

## Email-Generation Flow

1. Lead created/updated
2. `send_lead_notification()` called
3. Looks up tenant email settings
4. Selects template (by intent or default)
5. Renders template with lead data
6. Sends via SMTP or HeyJarvis default provider
7. Records notification in DB
8. Front desk sees notification in dashboard

## Current Configuration Mechanism

- Environment variables via `config.py`
- `CONCIERGE_SECRET_KEY` — JWT signing
- `CONCIERGE_DATABASE_URL` — SQLite path
- `CONCIERGE_ALLOW_REMOTE_DASHBOARD` — Remote access flag
- Per-tenant config stored in DB tables (widget_settings, email_settings, business_rules, tenant_settings)

## Current Deployment Assumptions

- Railway deployment (Procfile, nixpacks.toml)
- SQLite database (file-based)
- Single-process deployment
- Front desk dashboard served as static HTML from templates

## Current Limitations

1. **No /fd/* API routes** — Dashboard HTML references them but they don't exist
2. **No notes system** — No front desk notes on leads
3. **No task management** — No follow-up task tracking
4. **No AI draft management** — Drafts generated but not tracked/managed
5. **Some hardcoded assumptions** — Raleigh-specific defaults remain
6. **No draft tracking** — Email drafts generated but not persisted as managed objects

## Current Tests

- `test_saas.py` — Conversation engine, lead creation, auth
- `test_saas_admin.py` — Admin API endpoints
- `test_saas_email.py` — Email sending
- `test_saas_widget.py` — Widget loading and initialization
- Tests use SQLite in-memory DB, isolated per test via fixtures
