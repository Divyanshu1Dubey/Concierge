FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* ./
RUN pip install uv && uv sync --frozen --no-dev


# ── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY src/ src/
COPY config/ config/
COPY scripts/ scripts/
COPY docs/ docs/
COPY wordpress-plugin/ wordpress-plugin/

RUN mkdir -p /app/data /app/outbox \
    && chmod 755 /app/data /app/outbox

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0

EXPOSE 8000

# Default: run with SQLite. Override DATABASE_URL for Postgres.
CMD ["uvicorn", "saas.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
