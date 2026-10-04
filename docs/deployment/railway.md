# Railway Deployment Guide

## Prerequisites

1. Railway account (railway.app)
2. PostgreSQL plugin installed in your Railway project
3. Domain configured (e.g., app.heyjarvis.ai)

## Deployment Steps

### 1. Connect Repository

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Link to existing project or create new
railway link
```

### 2. Add PostgreSQL

In Railway dashboard:
1. Click "New" → "Database" → "PostgreSQL"
2. Railway will create a PostgreSQL instance
3. Copy the `DATABASE_URL` from the PostgreSQL service

### 3. Set Environment Variables

In Railway dashboard → Variables:

```
APP_ENV=production
DATABASE_URL=<postgresql-url-from-step-2>
JWT_SECRET=<random-64-char-string>
ENCRYPTION_KEY=<random-32-char-string>
APP_URL=https://your-app.railway.app
API_URL=https://your-app.railway.app
WIDGET_URL=https://your-app.railway.app
CORS_ORIGINS=https://your-app.railway.app,https://your-customer-site.com
AI_PROVIDER=openai
AI_API_KEY=<your-openai-key>
AI_MODEL=gpt-4o-mini
```

### 4. Configure Build

Railway auto-detects from `railway.toml`:

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uv run uvicorn saas.main:app --host 0.0.0.0 --port $PORT"
restartPolicyType = "on-failure"
restartPolicyMaxRetries = 5
healthcheckPath = "/health"
healthcheckTimeout = 30
```

### 5. Deploy

```bash
# Push to trigger deployment
git push railway main

# Or deploy via CLI
railway up
```

### 6. Run Migrations

After first deploy, run migrations:

```bash
# Via Railway shell
railway run python -c "from saas.database import connect; connect().__enter__().executescript(open('src/saas/database.py').read().split('SCHEMA = \"\"\"')[1].split('\"\"\"')[0])"

# Or create a management command
railway run python -m saas.cli migrate
```

### 7. Seed Demo Tenant (Optional)

```bash
railway run python scripts/seed_demo.py
```

### 8. Configure Custom Domain

1. Railway dashboard → Settings → Domains
2. Add custom domain: `app.heyjarvis.ai`
3. Update DNS CNAME to Railway endpoint

### 9. Verify Deployment

```bash
# Health check
curl https://your-app.railway.app/health

# Widget check
curl https://your-app.railway.app/widget.js

# API docs
open https://your-app.railway.app/docs
```

## Production Checklist

- [ ] PostgreSQL database added
- [ ] DATABASE_URL set
- [ ] JWT_SECRET set (random, 64+ chars)
- [ ] ENCRYPTION_KEY set (random, 32+ chars)
- [ ] CORS_ORIGINS set to actual domains
- [ ] AI_API_KEY set
- [ ] Health check passing
- [ ] SSL/HTTPS enabled (Railway provides automatically)
- [ ] Custom domain configured
- [ ] Environment variables secured (Railway secrets)
- [ ] Logging configured
- [ ] Error tracking configured (optional: Sentry)

## Database Migrations on Railway

Railway deployments are ephemeral except for PostgreSQL. Run migrations on deploy:

```bash
# Add to railway.toml
[deploy]
startCommand = "uv run uvicorn saas.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
```

Create a deploy hook script:
```bash
#!/bin/bash
# scripts/railway_migrate.sh
uv run python -c "
from saas.database import connect, reset_schema_cache
reset_schema_cache()
with connect() as c:
    pass  # Schema auto-creates on first connection
"
```

## Scaling

Railway automatically scales based on traffic. For higher traffic:

1. Increase worker count in start command:
   ```
   uv run uvicorn saas.main:app --host 0.0.0.0 --port $PORT --workers 4
   ```

2. Add Redis for session/cache (optional):
   ```bash
   railway add redis
   ```

3. Enable Railway's CDN for static assets

## Monitoring

- Railway provides built-in logs and metrics
- Enable Sentry for error tracking (optional)
- Monitor `/health` endpoint externally
