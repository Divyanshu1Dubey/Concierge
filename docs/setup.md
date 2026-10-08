# HeyJarvis — Setup Guide

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) >= 20.10
- [Docker Compose](https://docs.docker.com/compose/install/) >= 2.0
- [Git](https://git-scm.com/downloads)

## Quick Start (Docker)

### 1. Clone the repository

```bash
git clone <repository-url> concierge_religh
cd concierge_religh
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set the required values:

```bash
# On Windows
notepad .env

# On macOS / Linux
nano .env
```

**Minimum required changes:**
- `SECRET_KEY` — Generate a secure random string
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` — Your AI provider key
- `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` — For Gmail integration
- `GMAIL_REFRESH_TOKEN` — For sending emails via Gmail API

### 3. Start all services

```bash
docker compose up -d
```

This starts:
- PostgreSQL on port 5432
- Redis on port 6379
- Django backend on port 8000
- Celery worker
- Celery beat scheduler
- Nginx frontend on port 3001
- Flower (Celery monitor) on port 5555

### 4. Run database migrations

```bash
docker compose exec backend python manage.py migrate
```

### 5. Create a superuser

```bash
docker compose exec backend python manage.py createsuperuser
```

### 6. Seed initial data (Raleigh Dentistry)

```bash
docker compose exec backend python manage.py seed_raleigh
```

### 7. Access the application

- **Frontend:** http://localhost:3001
- **Backend API:** http://localhost:8000/api/
- **Admin Panel:** http://localhost:8000/admin/
- **Flower (Celery monitor):** http://localhost:5555

## Development Setup (Without Docker)

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements/development.txt

# Configure environment
cp ../.env.example ../.env
# Edit .env with local settings

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Seed data
python manage.py seed_raleigh

# Run server
python manage.py runserver
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

### Widget

```bash
cd widget

# Install dependencies
npm install

# Run development server
npm run dev
```

## Useful Commands

### Docker Compose

```bash
# Start all services
docker compose up -d

# View logs (all services)
docker compose logs -f

# View logs (specific service)
docker compose logs -f backend

# Stop all services
docker compose down

# Stop and remove volumes (WARNING: deletes data)
docker compose down -v

# Restart a service
docker compose restart backend

# Rebuild a service after code changes
docker compose up -d --build backend
```

### Django Management Commands

```bash
# Run migrations
docker compose exec backend python manage.py migrate

# Create superuser
docker compose exec backend python manage.py createsuperuser

# Seed demo data
docker compose exec backend python manage.py seed_raleigh

# Open Django shell
docker compose exec backend python manage.py shell

# Collect static files (for production)
docker compose exec backend python manage.py collectstatic --noinput
```

### Testing

```bash
# Run all tests
docker compose exec backend pytest

# Run with coverage
docker compose exec backend pytest --cov=apps

# Run specific test file
docker compose exec backend pytest tests/test_models.py

# Run specific test
docker compose exec backend pytest tests/test_models.py::test_practice_creation
```

## Database Access

### PostgreSQL CLI

```bash
docker compose exec postgres psql -U heyjarvis -d heyjarvis
```

### Redis CLI

```bash
docker compose exec redis redis-cli
```

## Troubleshooting

### Backend won't start

Check the logs:
```bash
docker compose logs backend
```

Common issues:
- Database not ready: wait a few seconds and retry
- Missing migrations: run `docker compose exec backend python manage.py migrate`
- Missing environment variables: check `.env` file

### Frontend shows blank page

Check that the backend is running and CORS is configured:
```bash
docker compose logs frontend
```

### Port already in use

Change ports in `docker-compose.yml`:
```yaml
services:
  frontend:
    ports:
      - "3002:80"  # Change 3001 to 3002
  backend:
    ports:
      - "8001:8000"  # Change 8000 to 8001
```

### Celery tasks not running

Check Celery and Redis:
```bash
docker compose logs celery
docker compose exec redis redis-cli ping
```

## Production Deployment

For production deployment:

1. Set `DEBUG=False` in `.env`
2. Generate a strong `SECRET_KEY`
3. Configure proper `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`
4. Use environment-specific `.env` files (not committed to Git)
5. Set up SSL/TLS termination (e.g., with Caddy or Nginx proxy)
6. Configure regular database backups
7. Set up monitoring and alerting

Example production `.env`:
```env
DEBUG=False
SECRET_KEY=<generated-with-django.core.management.utils.get_random_secret_key>
DATABASE_URL=postgres://user:pass@db-host:5432/heyjarvis
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com
```
