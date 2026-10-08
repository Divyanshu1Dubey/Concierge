@echo off
echo Starting HeyJarvis development environment...

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is not running. Please start Docker and try again.
    pause
    exit /b 1
)

REM Start PostgreSQL and Redis
echo Starting PostgreSQL and Redis...
docker compose -f docker/docker-compose.yml up -d postgres redis

echo.
echo Development environment is starting...
echo PostgreSQL: localhost:5432
echo Redis: localhost:6379
echo.
echo Next steps:
echo   1. Backend: cd backend ^&^& python -m venv venv ^&^& venv\Scripts\activate ^&^& pip install -r requirements.txt
echo   2. Backend: cp .env.example .env ^&^& python manage.py migrate ^&^& python manage.py createsuperuser
echo   3. Backend: python manage.py runserver
echo   4. Frontend: cd frontend ^&^& npm install ^&^& npm run dev
echo.
pause
