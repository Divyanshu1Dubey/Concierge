# HeyJarvis Concierge — Target Architecture

**Date:** 2025-01-06
**Version:** 1.0.0

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      HEYJARVIS CLOUD                                 │
│                    (Production Deployment)                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────────────────┐   │
│   │   CDN /     │   │   Dashboard │   │     API Gateway         │   │
│   │  Widget     │   │   Frontend  │   │   (FastAPI + Uvicorn)   │   │
│   │  widget.js  │   │  (HTML/JS)  │   │   /api/v1/public/*      │   │
│   │             │   │             │   │   /api/v1/admin/*       │   │
│   └──────┬──────┘   └──────┬──────┘   │   /api/v1/auth/*        │   │
│          │                 │          └───────────┬─────────────┘   │
│          └─────────────────┼────────────────────┘                  │
│                            │                                       │
│                    ┌───────▼────────┐                              │
│                    │  Tenant Engine │                              │
│                    │                │                              │
│                    │ ┌────────────┐ │                              │
│                    │ │Convo Engine│ │                              │
│                    │ └────────────┘ │                              │
│                    │ ┌────────────┐ │                              │
│                    │ │Config      │ │                              │
│                    │ │Engine      │ │                              │
│                    │ └────────────┘ │                              │
│                    │ ┌────────────┐ │                              │
│                    │ │Delivery    │ │                              │
│                    │ │Engine      │ │                              │
│                    │ └────────────┘ │                              │
│                    └───────┬────────┘                              │
│                            │                                       │
│          ┌─────────────────┼─────────────────┐                     │
│          │                 │                 │                     │
│   ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐              │
│   │  AI / LLM  │  │  Email /    │  │  Webhooks   │              │
│   │  Provider  │  │  SMTP       │  │  / Integr.  │              │
│   └────────────┘  └─────────────┘  └─────────────┘              │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                    PostgreSQL Database                      │  │
│   │  (multi-tenant, connection pooled, production-grade)        │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## What Is Already Working (Do Not Change)

| Component | Status | Notes |
|-----------|--------|-------|
| Conversation state machine | ✅ | STARTED → COLLECTING → CONFIRMING → SUBMITTED |
| AI field extraction | ✅ | Intent + entity extraction from free text |
| Lead creation | ✅ | Structured lead with all fields |
| Email delivery | ✅ | email_draft / direct / SMTP modes |
| Business rules | ✅ | JSON-based per-tenant rules |
| Widget JS | ✅ | Shadow DOM, async, isolated |
| Hosted Concierge | ✅ | /concierge/{slug} page |
| Admin dashboard | ✅ | Served HTML with full API |
| Multi-tenancy | ✅ | Tenant-scoped queries |
| Authentication | ✅ | JWT + Argon2 |
| API keys | ✅ | Public + secret |
| Domains | ✅ | Add/verify/remove |
| Audit logging | ✅ | Action tracking |
| Analytics | ✅ | Event tracking |
| 22 tests | ✅ | All passing |

## What Needs to Be Added / Completed

| Component | Status | Priority |
|-----------|--------|----------|
| PostgreSQL migration | 🔲 | HIGH |
| Docker/containerization | 🔲 | HIGH |
| Background email queue | 🔲 | MEDIUM |
| Rate limiting | 🔲 | HIGH |
| Request ID tracking | 🔲 | MEDIUM |
| Structured logging | 🔲 | MEDIUM |
| WordPress plugin | 🔲 | MEDIUM |
| Installation documentation | 🔲 | HIGH |
| Production deployment docs | 🔲 | HIGH |
| Security hardening | 🔲 | HIGH |
| E2E tests | 🔲 | MEDIUM |
| Widget responsive polish | 🔲 | LOW |
| Dashboard UX polish | 🔲 | LOW |

## Key Architectural Decisions

### 1. Single Codebase, Multi-Tenant
- One FastAPI application serves ALL tenants
- Tenant isolation via database queries (tenant_id in every table)
- No per-tenant deployments

### 2. Public vs Admin Separation
- `/api/v1/public/*` — widget-facing, client_key auth
- `/api/v1/admin/*` — dashboard-facing, JWT auth
- Never mix these

### 3. Widget Independence
- widget.js knows nothing about the dashboard
- widget.js only knows: client_key, API base URL
- All tenant config comes from `/api/v1/public/config`

### 4. Configuration Driven
- Every behavior is configurable per tenant
- No hardcoded business logic for specific tenants
- Raleigh = one tenant's configuration, not global code

### 5. Graceful Degradation
- AI unavailable → deterministic flow still works
- SMTP unavailable → fallback to managed email
- Widget config unavailable → default UI still loads
- Never show errors to website visitors

## Data Model (Current → Target)

### Current Tables (All Exist)
- tenants
- users
- memberships
- api_keys
- domains
- conversations
- messages
- leads
- notifications
- email_settings
- widget_settings
- business_rules
- tenant_settings
- analytics_events
- audit_logs

### Tables to Add
- email_templates (for template editor)
- integration_settings (for future CRM/SMS)
- rate_limit_entries (for rate limiting)

## API Surface

### Public API (widget-facing)
```
GET    /api/v1/public/config?client_key=...
POST   /api/v1/public/conversations
POST   /api/v1/public/conversations/{id}/messages
GET    /api/v1/public/widget-config/{slug}
GET    /health
```

### Admin API (dashboard-facing)
```
GET    /api/admin/tenants
GET    /api/admin/tenants/{id}
PATCH  /api/admin/tenants/{id}
GET    /api/admin/tenants/{id}/conversations
GET    /api/admin/conversations/{id}/messages
GET    /api/admin/tenants/{id}/leads
PUT    /api/admin/leads/{id}
GET    /api/admin/tenants/{id}/widget
PUT    /api/admin/tenants/{id}/widget
GET    /api/admin/tenants/{id}/email
PUT    /api/admin/tenants/{id}/email
POST   /api/admin/tenants/{id}/email/test
POST   /api/admin/tenants/{id}/smtp/test
GET    /api/admin/tenants/{id}/templates
POST   /api/admin/tenants/{id}/templates
PUT    /api/admin/templates/{id}
DELETE /api/admin/templates/{id}
GET    /api/admin/tenants/{id}/business-rules
PUT    /api/admin/tenants/{id}/business-rules
GET    /api/admin/tenants/{id}/settings
PUT    /api/admin/tenants/{id}/settings
GET    /api/admin/tenants/{id}/domains
POST   /api/admin/tenants/{id}/domains
POST   /api/admin/domains/{id}/verify
DELETE /api/admin/domains/{id}
GET    /api/admin/analytics
GET    /api/admin/tenants/{id}/audit-log
POST   /api/admin/tenants/{id}/api-keys
DELETE /api/admin/api-keys/{id}
```

## Deployment Targets

### Development
- SQLite + WAL
- uv run python -m saas.main
- Port 8000

### Production (Railway)
- PostgreSQL
- Gunicorn/Uvicorn workers
- Environment variables
- Health checks
- Persistent storage for media if needed

### Widget CDN
- Static file serving
- Cache headers
- Gzip/Brotli compression

## Security Model

| Concern | Solution |
|---------|----------|
| Widget auth | Public client key (not secret) |
| Dashboard auth | JWT + Argon2 passwords |
| Secrets | AES-GCM encrypted at rest |
| Tenant isolation | Every query scoped by tenant_id |
| Domain validation | Origin checked against tenant domains |
| Rate limiting | Per-IP, per-client-key limits |
| Input validation | Pydantic schemas |
| XSS | HTML sanitization on all user input |
| CSRF | Same-site cookies where applicable |
| Audit | All admin actions logged |

## What "Done" Looks Like

1. New tenant signs up → gets client key in 60 seconds
2. Pastes one script snippet → widget appears
3. Visitor interacts → lead created → front desk notified
4. Admin sees conversation + lead in dashboard
5. Admin can configure everything without code changes
6. System scales to hundreds of tenants
7. No tenant can access another tenant's data
8. No secrets exposed to browser
9. Production deployment is one-click
10. All tests pass
