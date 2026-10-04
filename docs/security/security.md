# HeyJarvis Concierge — Security

## Authentication & Authorization

### JWT Tokens
- Algorithm: HS256
- Expiry: 24 hours (configurable)
- Contains: sub (user ID), tid (tenant ID), role
- Verified server-side on every request

### Password Hashing
- Algorithm: Argon2 (via passlib)
- Minimum length: 8 characters
- Never store plaintext passwords
- Never log passwords

### Role-Based Access Control

| Role | Permissions |
|------|------------|
| OWNER | Full access |
| ADMIN | Configuration + operations |
| MEMBER | Conversations + leads |
| VIEWER | Read-only |

## Tenant Isolation

Every database query is scoped by `tenant_id`:

```python
# All repository functions require tenant_id
def get_conversations(tenant_id: int) -> list:
    return rows(c, "SELECT * FROM conversations WHERE tenant_id = ?", tenant_id)
```

### Isolation Rules
1. Tenant A cannot read Tenant B's conversations
2. Tenant A cannot read Tenant B's leads
3. Tenant A cannot read Tenant B's credentials
4. Tenant A cannot read Tenant B's settings
5. Tenant A cannot read Tenant B's analytics
6. Tenant A cannot read Tenant B's API keys

### Admin Endpoints
- `/api/admin/*` requires JWT authentication
- Each endpoint validates `tenant_id` matches authenticated user
- Cross-tenant access returns 403 Forbidden

## Secret Protection

### Secrets Never Exposed
- SMTP passwords encrypted with AES-GCM at rest
- API secrets hashed (never stored in plaintext)
- Webhook secrets encrypted
- Integration configs encrypted
- Never returned to frontend
- Never logged
- Never included in error messages

### Public vs Secret Keys
- Public client key (`pk_*`): safe for browser
- Secret API key (`sk_*`): server-to-server only
- Secret key hash stored, never plaintext

## Domain Security

### Origin Validation
Widget requests validate origin against tenant's allowed domains:

```python
def validate_domain(tenant_id, origin):
    with connect() as c:
        domain = rows(c, "SELECT 1 FROM domains WHERE tenant_id = ? AND domain = ?",
                      tenant_id, origin)
    return bool(domain)
```

### Rules
- Public client key is not a secret
- Tenant secrets never shipped to browser
- Browser cannot call privileged APIs
- Domain validation on widget config endpoint

## Input Validation

- All inputs validated via Pydantic schemas
- HTML sanitized before storage
- No raw user input in SQL queries
- No raw user input in email templates
- No raw user input in LLM prompts without sanitization

## Rate Limiting

### Public Endpoints
- 60 requests/minute per client key (configurable)
- Implemented via `rate_limit_entries` table
- Returns 429 with Retry-After header
- Per-IP + per-client key

### Protected Endpoints
- Standard rate limiting via infrastructure
- No special limits on admin endpoints (authenticated)

## CORS

### Public API
- Restricted to allowed origins
- Methods: GET, POST, OPTIONS
- Headers: Authorization, Content-Type

### Admin API
- Not exposed to browser
- Server-to-server only

## Audit Logging

All administrative actions logged:
- Settings changed
- Business rules changed
- Widget configuration changed
- Email settings changed
- Domain added/removed
- Team member added
- API key created/revoked
- SMTP settings changed

### Log Fields
- actor_user_id
- tenant_id
- action
- metadata (JSON)
- created_at (timestamp)

### Never Logged
- SMTP passwords
- API secrets
- Authentication tokens
- Full payment data
- Unnecessary sensitive user data

## XSS Protection

- All user input sanitized before storage
- HTML escaped in widget display
- Content Security Policy headers (where applicable)
- No `innerHTML` with unsanitized input
- Template engine escapes variables

## CSRF Protection

- Admin endpoints require CSRF token where applicable
- Public widget endpoints: CSRF not applicable (read-only public data)
- State-changing admin endpoints: CSRF tokens required

## Error Handling

### Production Error Responses
- No stack traces in public API responses
- No database details in errors
- No internal paths in errors
- Front desk receives generic error message

### Error Tracking
- Request ID in all logs
- Structured logging with context
- Errors tracked but not exposed to users

## Security Headers (Production)

Recommended headers:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; script-src 'self' https://app.heyjarvis.ai
```

## Dependency Security

- Keep dependencies updated
- Use `uv` for reproducible installs (uv.lock)
- Scan for vulnerabilities periodically
- Minimal dependency footprint

## Backup & Recovery

- Database backups before migrations
- Encrypted backups in transit
- Point-in-time recovery capability (PostgreSQL)
- Tested restore procedure
