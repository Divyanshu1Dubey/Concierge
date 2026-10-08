#!/bin/bash
set -e

echo "🚀 Deploying HeyJarvis Raleigh V1..."

# Build and start services
docker-compose -f docker/docker-compose.prod.yml down
docker-compose -f docker/docker-compose.prod.yml build
docker-compose -f docker/docker-compose.prod.yml up -d

# Wait for postgres
echo "Waiting for database..."
sleep 10

# Run migrations
docker-compose -f docker/docker-compose.prod.yml exec backend python manage.py migrate --noinput

# Collect static files
docker-compose -f docker/docker-compose.prod.yml exec backend python manage.py collectstatic --noinput

# Create superuser if needed (interactive)
# docker-compose -f docker/docker-compose.prod.yml exec backend python manage.py createsuperuser

echo "✅ Deployment complete!"
echo "🌐 Frontend: https://app.heyjarvis.com"
echo "🔌 API: https://api.heyjarvis.com"
echo "🔘 Widget: https://widget.heyjarvis.com"
