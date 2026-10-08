"""HeyJarvis - Pytest configuration and shared fixtures."""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.practices.models import Practice

User = get_user_model()


@pytest.fixture
def api_client():
    """Return an unauthenticated API client."""
    return APIClient()


@pytest.fixture
def practice():
    """Create and return a test practice."""
    return Practice.objects.create(
        name="Raleigh Comprehensive & Cosmetic Dentistry",
        slug="raleigh-dentistry",
        email="info@raleighdentistry.com",
        phone="(919) 555-0100",
        address="123 Dental Ave, Raleigh, NC 27601",
        timezone="America/New_York",
        website="https://raleighdentistry.com",
    )


@pytest.fixture
def owner_user(practice):
    """Create and return an OWNER user for the practice."""
    return User.objects.create_user(
        email="owner@test.com",
        password="testpass123",
        name="Dr. Owner",
        role="OWNER",
        practice=practice,
    )


@pytest.fixture
def admin_user(practice):
    """Create and return an ADMIN user for the practice."""
    return User.objects.create_user(
        email="admin@test.com",
        password="testpass123",
        name="Office Admin",
        role="ADMIN",
        practice=practice,
    )


@pytest.fixture
def front_desk_user(practice):
    """Create and return a FRONT_DESK user for the practice."""
    return User.objects.create_user(
        email="frontdesk@test.com",
        password="testpass123",
        name="Front Desk Staff",
        role="FRONT_DESK",
        practice=practice,
    )


@pytest.fixture
def authenticated_client(api_client, owner_user):
    """Return an API client authenticated as the OWNER user."""
    api_client.force_authenticate(user=owner_user)
    return api_client


@pytest.fixture
def authenticated_admin_client(api_client, admin_user):
    """Return an API client authenticated as the ADMIN user."""
    api_client.force_authenticate(user=admin_user)
    return api_client
