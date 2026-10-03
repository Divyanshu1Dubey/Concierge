# HeyJarvis Concierge Platform

Multi-tenant AI concierge platform for appointment-based businesses.

## Local setup

```bash
cp .env.example .env
uv sync --dev
uv run python scripts/seed_demo.py
uv run uvicorn saas.main:app --reload
```

Open:
- http://localhost:8000/docs
- http://localhost:8000/concierge/raleigh-dental-demo

## Install on a website

```html
<script
  src="http://localhost:8000/widget.js"
  data-heyjarvis-client="pk_demo_public_key_from_seed">
</script>
```

## Run tests

```bash
uv run python -m pytest -q
```

## Railway deployment

1. Push this repo to GitHub
2. In Railway, create a new project from GitHub
3. Add environment variables from `.env.example`
4. Railway uses `railway.toml` build/deploy settings
5. After deploy, run the seed command in Railway shell:
```bash
uv run python scripts/seed_demo.py
```

## Default demo tenant

Slug: `raleigh-dental-demo`
Owner email: `owner@example.com`
Owner password: `password`

## Environment variables

See `.env.example`.
