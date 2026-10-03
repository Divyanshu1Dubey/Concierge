# Current State — HeyJarvis Concierge Platform

## Verified: All 10 SaaS tests passing

## Current Architecture

```
            HEYJARVIS CLOUD
                  |
    +-------------+-------------+
    |             |             |
 Dashboard       API       Widget CDN
 (src/saas/templates/dashboard)
  (FastAPI Jinja2)
 |             |             |
 +-------------+-------------+
            |
      Tenant Engine
  (saas/public_api.py)
            |
+-----------+-----------+
|           |           |
Conversation Engine  Business Rules    Delivery Engine
(saas/conversation.py)(saas/repos/biz)(saas/notifications)
       |           |           |
       +-----------+-----------+
                  |
            AI / Email / Webhooks
```

## Major Modules

### SaaS Backend (`src/saas/`)
- **database.py** — SQLite with WAL mode, schema migrations via `CREATE TABLE IF NOT EXISTS`, helper functions (`insert`, `rows`, `row`, `now_iso`)
- **config.py** — Pydantic Settings with `.env` file support, encrypted secrets
- **models.py** — Pydantic models: `Tenant`, `User`, `ConversationContext`, `ApiKey`, `Domain`, `Lead`
- **repositories.py** — Full data access layer: tenant CRUD, users, API keys, domains, widget settings, email settings, business rules, conversations, messages, leads, notifications, analytics events, audit logs
- **security.py** — Password hashing (argon2), JWT tokens, secret encryption (SHA256-based Fernet), redaction
- **auth.py** — OAuth2 password flow, role-based access control (owner/admin/member/viewer)
- **conversation.py** — Conversation state machine with 8 states (STARTED → SUBMITTED → CLOSED), AI field extraction, lead generation
- **notifications.py** — Email delivery engine with default SMTP and custom SMTP support, webhook delivery
- **email_templates.py** — Tenant-configurable email template engine with Jinja2
- **public_api.py** — Public widget API (no auth required, client_key only)
- **admin_api.py** — Admin dashboard API (JWT auth, role-based)
- **main.py** — FastAPI app mounting public + admin routes, health checks, hosted concierge URL

### Frontend Dashboard (`src/saas/templates/`)
- **base.html** — Dashboard shell with navigation
- **login.html** — Login page
- **dashboard.html** — Main dashboard overview with stats cards, recent conversations, leads, system status
- **tenants.html** — Tenant list management
- **tenant_detail.html** — Single tenant configuration
- **conversations.html** — Conversation list with filters
- **conversation_detail.html** — Full conversation view with transcript, lead info, status management
- **leads.html** — Lead table with status updates
- **install.html** — Installation snippet page with copy-to-clipboard
- **hosted.html** — Standalone hosted concierge page (iframe-based)

### Widget (`src/saas/static/`)
- **widget.js** — Async-loaded embeddable widget, Shadow DOM isolation, floating launcher, chat interface
- **widget.css** — Widget styling (loaded by widget.js)

## API Routes

### Public (no auth, client_key only)
- `GET /api/v1/public/config` — Tenant configuration (widget settings, greeting, AI enabled, etc.)
- `POST /api/v1/public/conversations` — Start new conversation
- `POST /api/v1/public/conversations/{id}/messages` — Send message, get AI response
- `GET /api/v1/public/leads?client_key=&lead_id=` — Lead status lookup
- `GET /widget.js` — Widget script delivery
- `POST /api/v1/public/track` — Analytics event tracking
- `GET /health` — Health check
- `GET /ready` — Readiness check
- `GET /version` — Version info

### Admin (JWT auth required, role-based)
- `GET /api/admin/tenants` — List tenants
- `POST /api/admin/tenants` — Create tenant
- `GET /api/admin/tenants/{id}` — Get tenant
- `PUT /api/admin/tenants/{id}` — Update tenant
- `DELETE /api/admin/tenants/{id}` — Delete tenant
- `POST /api/admin/tenants/{id}/domains` — Add domain
- `DELETE /api/admin/domains/{id}` — Remove domain
- `POST /api/admin/domains/{id}/verify` — Verify domain
- `GET /api/admin/tenants/{id}/domains` — List domains
- `GET /api/admin/tenants/{id}/conversations` — Tenant conversations
- `GET /api/admin/conversations/{id}` — Conversation detail
- `GET /api/admin/leads` — All leads
- `PUT /api/admin/leads/{id}` — Update lead status
- `POST /api/admin/auth/token` — Login (OAuth2 password flow)
- `GET /api/admin/auth/me` — Current user info
- `POST /api/admin/analytics/events` — Track analytics event
- `GET /api/admin/analytics/summary` — Analytics summary
- `POST /api/admin/settings` — Update tenant settings
- `GET /api/admin/settings` — Get tenant settings
- `POST /api/admin/widget` — Update widget settings
- `POST /api/admin/email/test` — Test email delivery
- `POST /api/admin/email/smtp/test` — Test SMTP connection
- `POST /api/admin/api-keys` — Create API key
- `DELETE /api/admin/api-keys/{id}` — Revoke API key

### Hosted Concierge
- `GET /concierge/{tenant_slug}` — Standalone hosted Concierge page

## Database Models

### tenants
- id, slug (unique), name, enabled (bool), plan, metadata (JSON), created_at, updated_at

### users
- id, tenant_id (FK), email, display_name, hashed_password, role (owner/admin/member/viewer), created_at, updated_at, last_login_at, metadata

### memberships
- id, tenant_id (FK), user_id (FK), role, created_at (unique: tenant_id, user_id)

### domains
- id, tenant_id (FK), domain (unique per tenant), verified (bool), created_at

### api_keys
- id, tenant_id (FK), label, public_key (unique), secret_key_hash, last_used_at, created_at, revoked_at

### widget_settings
- id, tenant_id (unique FK), config (JSON), updated_at

### email_settings
- id, tenant_id (unique FK), provider (default/custom), smtp_host, smtp_port, smtp_user, smtp_password_enc (encrypted), from_name, from_email, reply_to, updated_at

### business_rules
- id, tenant_id (unique FK), rules (JSON), updated_at

### conversations
- id, tenant_id (FK), visitor_id, page_url, referrer, user_agent, status, summary, created_at, updated_at, metadata (JSON)

### messages
- id, conversation_id (FK), role (visitor/concierge/system), body, created_at, metadata

### leads
- id, tenant_id (FK), conversation_id (FK), name, email, phone, intent, service, urgency, preferred_date, preferred_time, insurance, financing, message, conversation_summary, source, page_url, status (new/contacted/qualified/booked/closed/spam), created_at, updated_at, metadata

### notifications
- id, tenant_id (FK), lead_id (FK), conversation_id (FK), channel (email/webhook/sms), status (pending/sent/failed), payload (JSON), error, created_at, sent_at

### analytics_events
- id, tenant_id (FK), event, payload (JSON), created_at

### audit_logs
- id, tenant_id (FK), actor_user_id, action, metadata (JSON), created_at

### tenant_settings
- id, tenant_id (unique FK), flags (JSON), ai_instructions (text), hours (JSON), updated_at

## Data Flow

### Widget → Backend → Front Desk
1. Visitor loads website → widget.js loads asynchronously
2. Widget fetches `/api/v1/public/config?client_key=PUBLIC_KEY`
3. Widget fetches tenant config, creates Shadow DOM widget
4. Visitor clicks launcher → widget opens with greeting
5. Visitor sends message → `POST /api/v1/public/conversations/{id}/messages`
6. Backend: validates client_key, loads tenant config, runs ConversationEngine
7. ConversationEngine: extracts fields via AI, tracks state machine
8. When SUBMITTED: creates lead, sends notification (email/webhook)
9. Front desk receives email (draft or direct, per tenant config)
10. Analytics events tracked throughout

### Admin → Backend → Database
1. Admin logs in → JWT token issued
2. Admin configures tenant → PUT/POST admin endpoints
3. Admin views conversations → GET admin endpoints
4. Admin updates lead status → PUT admin endpoints
5. All actions logged to audit_logs

## Existing Concierge Conversation Flow

1. **STARTED** — Conversation created, greeting sent
2. **IDENTIFYING_INTENT** — AI determines visitor intent (appointment_request, emergency, question, etc.)
3. **COLLECTING_INFORMATION** — System collects fields based on tenant configuration
4. **QUALIFYING** — Additional qualification if needed
5. **CONFIRMING** — Summary of collected information
6. **SUBMITTING** — Lead created, notification triggered
7. **SUBMITTED** — Final state, lead ready for front desk
8. **HANDOFF** — Human handoff requested
9. **CLOSED** — Conversation ended

AI assists with: intent detection, field extraction, natural language understanding, summarization, response generation.
Backend controls: required fields, tenant rules, validation, submission, notification, rate limiting, permissions, conversation lifecycle.

## Email Generation Flow

1. Lead created → `create_lead()` in repositories.py
2. `send_lead_notification()` called with tenant_id and lead_id
3. Notification engine checks tenant email settings
4. If `provider == "default"` → uses HeyJarvis managed email (SMTP from platform env)
5. If `provider == "custom"` → uses tenant's SMTP credentials (decrypted from encrypted storage)
6. Email template loaded from `email_settings` (subject + body templates)
7. Template rendered with Jinja2 using lead data + tenant variables
8. Email sent via SMTP or queued for delivery
9. Notification record created with status (pending/sent/failed)
10. Front desk receives email with lead details

**Notification modes:**
- `EMAIL_DRAFT` — Creates email for front desk review (Raleigh default, preserves existing workflow)
- `DIRECT_EMAIL` — Sends email immediately

## Current Configuration Mechanism

Tenant settings stored in `tenant_settings` table as JSON `flags` column:
- Widget appearance (position, colors, theme, avatar, etc.)
- Behavior flags (ai_enabled, chatbot_enabled, lead_collection_enabled, email_enabled, human_handoff_enabled, etc.)
- Timing settings (auto_open_delay, welcome_message, offline_message, etc.)

Additional configuration tables:
- `widget_settings` — Full widget configuration as JSON
- `email_settings` — SMTP and email provider settings
- `business_rules` — Business-specific rules as JSON
- `tenant_settings.ai_instructions` — Tenant-specific AI instructions
- `tenant_settings.hours` — Business hours configuration

Configuration precedence:
1. Global platform defaults (code)
2. Tenant defaults (seed data)
3. Tenant custom configuration (dashboard settings)
4. Context-specific rules (page-level overrides if implemented)
5. System safety rules (never overridable)

## Current Deployment Assumptions

- **Database**: SQLite (file-based, suitable for single-server deployment)
- **Backend**: FastAPI (Python 3.12)
- **Frontend**: Jinja2 templates (server-rendered dashboard)
- **Widget**: Vanilla JavaScript with Shadow DOM (no framework dependencies)
- **Email**: SMTP (default platform SMTP or tenant-configured)
- **AI**: Configurable provider (OpenAI-compatible API)
- **Process**: Single uvicorn process serving both API and dashboard
- **Static files**: Served from `src/saas/static/`
- **Environment**: `.env` file-based configuration

## Current Limitations

1. **SQLite only** — Not suitable for multi-server horizontal scaling
2. **No background job queue** — Email delivery happens synchronously
3. **No file upload** — Widget doesn't support attachments
4. **Limited CRM integration** — Only webhook-based
5. **No SMS integration** — Architecture ready but not implemented
6. **Single-region** — No CDN for widget.js
7. **No rate limiting** — Not yet implemented at the API level
8. **No request ID tracking** — Structured logging present but no request correlation
9. **Widget only supports chat mode** — Form mode not yet implemented
10. **No WordPress plugin** — Architecture ready but plugin not built
11. **No mobile app** — Dashboard is web-only, responsive but not native
12. **No payment processing** — Billing UI present but no payment integration
13. **No calendar integration** — Can't check real availability
14. **Limited analytics** — Basic event tracking only

## Current Tests

All 10 SaaS tests passing:
- `test_tenant_creation` — Tenant CRUD operations
- `test_api_key_lifecycle` — Public/secret API key generation and revocation
- `test_domain_workflow` — Domain addition, verification, removal
- `test_enable_disable` — Tenant enable/disable toggle
- `test_public_requires_client_key` — Unauthenticated access rejection
- `test_public_conversation_flow` — Full conversation lifecycle via public API
- `test_tenant_isolation` — Cross-tenant data access prevention
- `test_auth_password_flow` — Password authentication
- `test_health_public` — Health endpoint
- `test_track_event_writes` — Analytics event tracking

## Environment Variables

```
# Database
DATABASE_URL=data/saas.db

# App
APP_URL=http://localhost:8000
API_URL=http://localhost:8000/api
WIDGET_URL=http://localhost:8000/static/widget.js

# Security
JWT_SECRET=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRES_MINUTES=1440
ENCRYPTION_KEY=your-32-char-encryption-key-here

# AI
AI_PROVIDER=openai
AI_API_KEY=sk-...
AI_MODEL=gpt-4o-mini
AI_BASE_URL=https://api.openai.com/v1
AI_TEMPERATURE=0.7
AI_MAX_TOKENS=500

# Email (Default)
SMTP_HOST=smtp.yourprovider.com
SMTP_PORT=587
SMTP_USER=heyjarvis@yourdomain.com
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_NAME=HeyJarvis
SMTP_FROM_EMAIL=noreply@heyjarvis.ai
SMTP_REPLY_TO=support@heyjarvis.ai

# CORS
CORS_ORIGINS=*

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60
```

## How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations (automatic on first run)
python -c "from saas.database import connect; connect()"

# Start server
uvicorn saas.main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
python -m pytest test_saas.py -v
```

## How to Deploy

1. Set environment variables in `.env` or hosting platform
2. Ensure `data/` directory exists and is writable
3. Run database initialization: `python -c "from saas.database import connect; connect()"`
4. Deploy with uvicorn/Gunicorn + Nginx reverse proxy
5. Configure SSL/TLS (HTTPS required for widget)
6. Set `APP_URL`, `API_URL`, `WIDGET_URL` to production URLs
7. Configure default SMTP settings for HeyJarvis-managed email

## Widget Installation Snippet

```html
<script
  src="https://YOUR-HOSTED-DOMAIN/widget.js"
  data-heyjarvis-client="PUBLIC_CLIENT_KEY"
  async>
</script>
```

## Hosted Concierge URL

```
https://YOUR-HOSTED-DOMAIN/concierge/tenant-slug
```

## What Can Be Reused

- **Conversation engine** — Core state machine works for any tenant
- **Email system** — Template engine + delivery layer is tenant-agnostic
- **Notification system** — Webhook + email delivery works for all tenants
- **AI field extraction** — Generic enough for any business type
- **Lead object** — Universal structured lead format
- **Security layer** — JWT auth, password hashing, encryption work for multi-tenant
- **Dashboard framework** — Jinja2 base templates can be extended

## What Needs to Change (for production)

1. **Database** — Migrate from SQLite to PostgreSQL for production scale
2. **Background jobs** — Add Celery/RQ for async email delivery
3. **Widget CDN** — Serve widget.js from CDN (Cloudflare, Vercel Edge)
4. **Monitoring** — Add health checks, logging aggregation, error tracking
5. **Backup** — Automated database backups
6. **Scaling** — Add Redis for sessions/caching, horizontal API scaling
7. **CI/CD** — Automated testing + deployment pipeline
8. **SSL** — Ensure HTTPS everywhere (required for widget)
9. **Rate limiting** — Add per-tenant rate limits
10. **WordPress plugin** — Package widget as distributable plugin

## Production Checklist

- [ ] All 10 SaaS tests passing ✅
- [ ] Environment variables configured
- [ ] Database migrated to PostgreSQL
- [ ] SMTP configured (default or tenant-specific)
- [ ] SSL/TLS certificates installed
- [ ] Domain allowlist configured for each tenant
- [ ] Widget CDN configured
- [ ] Monitoring/alerting set up
- [ ] Backup strategy implemented
- [ ] Rate limiting enabled
- [ ] WordPress plugin built (optional)
- [ ] Demo tenant seeded
