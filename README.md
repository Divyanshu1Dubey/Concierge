# HeyJarvis Concierge Platform
# Multi-tenant AI front-desk assistant SaaS

## Local Setup

```bash
# Install dependencies
uv sync

# Copy environment
cp .env.example .env

# Run database migrations (automatic on first run)

# Start development server
uv run uvicorn saas.main:app --reload --port 8000

# Run tests
uv run pytest

# Run with core concierge (legacy)
uv run uvicorn concierge.api:app --port 8001
```

## Environment Variables

See `.env.example` for all available options.

Required:
- `JWT_SECRET` — random 64-char string
- `ENCRYPTION_KEY` — 32-char string for AES-GCM
- `DATABASE_URL` — SQLite path or PostgreSQL URL
- `APP_URL` — your application URL

## Architecture

```
src/saas/          # SaaS multi-tenant platform
  main.py          # Root FastAPI app
  config.py        # Configuration
  database.py      # Database layer (SQLite/PostgreSQL)
  models.py        # Pydantic models
  repositories.py  # Data access
  auth.py          # JWT authentication
  security.py      # Password hashing, encryption
  conversation.py  # Conversation engine
  emailer.py       # Email delivery
  email_templates.py
  public_api.py    # Public + admin API routes
  static/
    widget.js      # Embeddable widget
  templates/
    admin.html     # Admin dashboard
    hosted.html    # Hosted concierge page

src/concierge/     # Legacy single-tenant concierge (preserved)
tests/             # Core tests
test_saas.py       # SaaS tests
```

## Deployment

See `docs/deployment/` for Railway, Docker, and PostgreSQL guides.

## Widget Installation

```html
<script
  src="https://YOUR_DOMAIN/widget.js"
  data-heyjarvis-client="PUBLIC_CLIENT_KEY"
  async>
</script>
```

## API

### Public (widget-facing)
- `GET /api/v1/public/config?client_key=...`
- `POST /api/v1/public/conversations`
- `POST /api/v1/public/conversations/{id}/messages`

### Admin (dashboard-facing)
- `GET /api/admin/tenants`
- `GET /api/admin/tenants/{id}`
- `GET /api/admin/tenants/{id}/conversations`
- `GET /api/admin/tenants/{id}/leads`
- `PUT /api/admin/tenants/{id}/widget`
- `PUT /api/admin/tenants/{id}/email`
- And more...

## License

Proprietary — HeyJarvis
