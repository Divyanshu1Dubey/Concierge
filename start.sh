#!/usr/bin/env bash
set -e

echo "==> HeyJarvis Concierge Railway Bootstrapper"
echo "==> Current working directory: $(pwd)"

if [ -f "backend/manage.py" ]; then
    echo "==> Detected project root (backend/manage.py found)"
    echo "==> Running database migrations..."
    python backend/manage.py migrate --noinput
    echo "==> Running demo seed (if enabled)..."
    python backend/manage.py seed_raleigh || true
    echo "==> Starting Gunicorn on port ${PORT:-8000}..."
    exec gunicorn --chdir backend config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-60} --access-logfile -
elif [ -f "manage.py" ]; then
    echo "==> Detected backend directory (manage.py found)"
    echo "==> Running database migrations..."
    python manage.py migrate --noinput
    echo "==> Running demo seed (if enabled)..."
    python manage.py seed_raleigh || true
    echo "==> Starting Gunicorn on port ${PORT:-8000}..."
    exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-60} --access-logfile -
else
    echo "==> ERROR: manage.py could not be found in $(pwd)"
    ls -la
    exit 1
fi
