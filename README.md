# HeyJarvis — AI Dental Concierge

AI-powered appointment scheduling for dental practices. Built for Raleigh Comprehensive & Cosmetic Dentistry.

## Features (V1)

- 🤖 AI Chat Concierge — Patients request appointments via website chat
- 📧 Semi-Automated Email — Front desk reviews AI drafts and sends with one click
- 📋 Cadence Management — Follow-up sequences with patient response tracking
- 🔐 Google OAuth — Secure practice authentication

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16+
- Redis 7+

### Setup

```bash
# Clone
git clone <repo-url> && cd concierge_religh

# Copy environment
cp .env.example .env

# Start with Docker
make docker-up

# Or manual setup
make setup
```

### Docker (Recommended)

```bash
make docker-up
```

Backend: http://localhost:8000
Frontend: http://localhost:3000

## Project Structure

```
backend/       — Django REST API
frontend/      — React + TypeScript dashboard
widget/        — Embeddable chat widget
wordpress/     — WordPress plugin
docker/        — Docker & nginx config
tests/         — Test suite
docs/          — Documentation
```

## License

Proprietary — HeyJarvis
