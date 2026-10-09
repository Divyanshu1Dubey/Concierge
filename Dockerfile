FROM python:3.12-slim

# Build tools for any dependency without a prebuilt wheel
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
# APP_ENV is baked in so a deleted/missing platform variable fails closed (no demo clinic or logins,
# strong secrets required at boot) instead of silently starting in development mode.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

# Dependencies only (cached between deploys). The app runs from src/ via PYTHONPATH,
# so nothing is installed or synced at startup.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY config/ ./config/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, os; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://localhost:{port}/health')"

# One worker: the mailbox/follow-up scheduler runs inside the web process.
# No access log: URLs such as /api/admin/fd/search?q= carry patient names, emails and phone numbers.
CMD ["sh", "-c", "uvicorn saas.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips '*' --no-access-log"]
