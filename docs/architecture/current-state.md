# HeyJarvis Concierge — Current State

Date: 2025-10-04

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         CLIENT SITES                         │
│  (WordPress, Webflow, Wix, Squarespace, React, plain HTML)  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                     widget-loader.js
                    (universal embed snippet)
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   SAAS BACKEND (FastAPI)                     │
│                    Port 8000                                 │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐ │
│  │ Public API  │  │ Admin API    │  │ Conversation      │ │
│  │ /v1/public/ │  │ /v1/admin/   │  │ Engine            │ │
│  └──────┬──────┘  └──────┬───────┘  └────────┬──────────┘ │
│         │                │                    │            │
│  ┌──────▼────────────────▼────────────────────▼──────────┐ │
│  │                   Services Layer                        │ │
│  │  • Lead Management  • Email Notifications  • Analytics │ │
│  └───────────────────────────┬────────────────────────────┘ │
│                              │                              │
│  ┌───────────────────────────▼────────────────────────────┐ │
│  │                   SQLite Database                       │ │
│  │  tenants, api_keys, conversations, messages,           │ │
│  │  leads, notifications, events, domains                  │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Major Modules

### Backend (`src/saas/`)

| Module | File | Purpose |
|--------|------|---------|
| Main app | `main.py` | FastAPI app, middleware, startup |
| Database | `database.py` | SQLite connection, schema, migrations |
| Repositories | `repositories.py` | Data access layer (CRUD) |
| Public API | `public_api.py` | Widget-facing endpoints |
| Admin API | `admin_api.py` | Dashboard-facing endpoints |
| Conversation engine | `conversation.py` | Multi-turn state machine |
| Email system | `emailer.py` | SMTP + notification delivery |
| Front desk | `front_desk.py` | Email draft generation |
| Billing | `billing.py` | Stripe integration (placeholder) |
| Auth | `auth.py` | Session + JWT auth |
| Middleware | `middleware.py` | Tenant isolation, rate limiting |

### Frontend / Widget

| Component | File | Purpose |
|-----------|------|---------|
| Widget | `widget-loader.js` | Universal embeddable chat widget |
| Dashboard | `admin_ui/` | Admin dashboard (basic) |
| Front desk | `front_desk/` | Email draft review UI |

## API Routes

### Public API (`/api/v1/public/`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/conversations` | Start new conversation |
| POST | `/conversations/{id}/messages` | Send message, get reply |
| GET | `/leads` | Get lead status |
| GET | `/config` | Get tenant config (colors, fields) |
| GET | `/widget.js` | Serve widget script |

### Admin API (`/api/v1/admin/`)

| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/tenants` | Tenant management |
| GET/PUT | `/settings` | Tenant settings |
| GET/PUT | `/business-rules` | Business rules |
| GET/POST | `/fields` | Field configuration |
| GET/POST | `/email` | Email settings |
| GET/PUT | `/widget` | Widget customization |
| GET | `/conversations` | Conversation list |
| GET | `/leads` | Lead list |
| GET/POST | `/integrations` | Integration settings |

## Database Models

### tenants
- id, name, slug, status, created_at, updated_at

### api_keys
- id, tenant_id, key_type (public/secret), key_hash, label, revoked_at

### tenant_settings
- id, tenant_id, flags (JSON), ai_instructions

### conversations
- id, tenant_id, visitor_id, page_url, referrer, user_agent, status, summary, created_at, updated_at, metadata

### messages
- id, conversation_id, role (user/assistant), body, created_at, metadata

### leads
- id, tenant_id, conversation_id, name, email, phone, intent, service, urgency, preferred_date, preferred_time, insurance, financing, message, conversation_summary, source, page_url, status, created_at, updated_at

### notifications
- id, tenant_id, lead_id, type, status, payload, sent_at, error

### events
- id, tenant_id, event_type, payload, created_at

### domains
- id, tenant_id, domain, verified_at

## Data Flow

### Conversation Flow

```
Visitor opens website
       │
       ▼
Widget loads → GET /api/v1/public/config?client_key=xxx
       │
       ▼
Visitor clicks launcher
       │
       ▼
POST /api/v1/public/conversations → Creates conversation, returns greeting
       │
       ▼
Visitor sends message
       │
       ▼
POST /api/v1/public/conversations/{id}/messages
       │
       ├── ConversationEngine processes message
       │   ├── Extract fields (name, email, intent, etc.)
       │   ├── Check missing required fields
       │   ├── Generate reply / next prompt
       │   └── Update state
       │
       ├── If SUBMITTED state:
       │   ├── Create lead record
       │   ├── Send notification email
       │   └── Track event
       │
       ▼
Reply returned to widget → Display to visitor
```

### Lead Notification Flow

```
Lead created (conversation submitted)
       │
       ▼
send_lead_notification(tenant_id, lead_id)
       │
       ├── Get tenant email settings
       │
       ├── Render email template with lead data
       │
       ├── If SMTP configured:
       │   └── Send via tenant SMTP
       │
       └── If no SMTP:
           └── Send via HeyJarvis default mailer
```

## Widget Conversation Flow

1. **Greeting**: Widget shows "Hi! Welcome to Raleigh Dentistry. How can we help you today?"
2. **User responds**: Free-form message
3. **Widget extracts**:
   - Intent (new_patient, cleaning, emergency, etc.)
   - Name, email, phone from text
   - Preferred date/time keywords
4. **Widget asks** next required field if missing
5. **All fields collected**: Shows review form for final submission
6. **Submit**: Sends lead to backend, triggers email notification

## Email System

- Tenant-configurable SMTP settings
- Email templates with variable substitution
- Delivery via tenant SMTP or HeyJarvis managed
- Support for test emails and connection testing
- Notification status tracking

## Current Configuration Mechanism

- Tenant settings stored in `tenant_settings` table as JSON flags
- Widget configuration loaded from API endpoint
- Business rules stored in tenant settings flags
- Email settings stored separately per tenant

## Current Deployment

- Development: Uvicorn on port 8000
- Front desk UI: Separate server on port 8002
- Database: SQLite file (`data/concierge.db`)
- No containerization yet
- No production deployment configured

## Current Limitations

1. **No real AI/LLM integration** - Uses rule-based extraction
2. **No persistent conversation state** - Fields not persisted between turns (widget-local only)
3. **No conversation_fields table** - Extracted data not stored per turn
4. **No tenant onboarding flow** - Manual setup only
5. **No billing integration** - Stripe placeholder only
6. **No OAuth/magic links** - Email/password only
7. **No WordPress plugin distributable** - Widget only
8. **No production deployment** - Local dev only
9. **Limited analytics** - Event tracking exists but no dashboard
10. **No multi-tenant field isolation** - Shared database schema

## Current Tests

- No automated tests found in repository
- Manual testing via browser and curl
- Widget tested via Chrome DevTools

## Widget Installation

```html
<script async src="widget-loader.js"
        data-heyjarvis-api="http://localhost:8000"
        data-heyjarvis-client="pk_Jq2tg3A_e5VLBfez651UR9z1">
</script>
```

## Key Features Working

- ✅ Multi-tenant API with client key authentication
- ✅ Conversation state machine (started, collecting, submitted, handoff)
- ✅ Field extraction from free-form text (name, email, phone, intent)
- ✅ Lead creation on submission
- ✅ Email notification to front desk
- ✅ Widget loads asynchronously without blocking
- ✅ Chat mode with typing indicator
- ✅ Form fallback mode
- ✅ Intent detection (new_patient, cleaning, emergency, etc.)
- ✅ Required field collection
- ✅ Raleigh Dentistry branding/colors

## Key Files Modified in This Session

- `widget-loader.js` - Complete rewrite with tenant configurable widget
- `src/saas/conversation.py` - Conversation engine with field extraction
- `src/saas/public_api.py` - Public API with lead creation and notifications
- `src/saas/database.py` - Added conversation_fields table migration
- `scripts/migrate_add_conversation_fields.py` - Migration script
