#!/bin/bash
set -e

echo "🚀 Starting HeyJarvis development environment..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Start PostgreSQL and Redis
echo "📦 Starting PostgreSQL and Redis..."
docker compose -f docker/docker-compose.yml up -d postgres redis

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL..."
until docker exec heyjarvis-postgres pg_isready -U heyjarvis > /dev/null 2>&1; do
    sleep 2
done
echo "✅ PostgreSQL is ready"

# Wait for Redis to be ready
echo "⏳ Waiting for Redis..."
until docker exec heyjarvis-redis redis-cli ping > /dev/null 2>&1; do
    sleep 2
done
echo "✅ Redis is ready"

echo ""
echo "🎉 Development environment is ready!"
echo ""
echo "Next steps:"
echo "  1. Backend: cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
echo "  2. Backend: cp .env.example .env && python manage.py migrate && python manage.py createsuperuser"
echo "  3. Backend: python manage.py runserver"
echo "  4. Frontend: cd frontend && npm install && npm run dev"
echo ""
echo "Services running:"
echo "  - PostgreSQL: localhost:5432"
echo "  - Redis: localhost:6379"
echo "  - Backend: http://localhost:8000 (when running)"
echo "  - Frontend: http://localhost:5173 (when running)"
