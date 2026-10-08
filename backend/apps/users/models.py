"""
User model and related models.
"""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    """Custom user model for HeyJarvis."""
    ROLE_CHOICES = [
        ('AGENCY_ADMIN', 'Agency Admin'),
        ('PRACTICE_ADMIN', 'Practice Admin'),
        ('FRONT_DESK', 'Front Desk'),
        ('OWNER', 'Owner'),
        ('ADMIN', 'Admin'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    google_id = models.CharField(max_length=255, blank=True, db_index=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='FRONT_DESK')
    # Legacy DB column kept for SQLite schema compatibility
    user_type = models.CharField(max_length=20, default='staff', blank=True)
    practice = models.ForeignKey(
        'practices.Practice',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='users'
    )
    avatar_url = models.URLField(blank=True)
    is_verified = models.BooleanField(default=False)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['practice', 'role']),
        ]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_agency_admin(self):
        return self.is_superuser or (self.role or '').upper() == 'AGENCY_ADMIN'

    @property
    def is_practice_admin(self):
        return self.is_agency_admin or (self.role or '').upper() in ('PRACTICE_ADMIN', 'ADMIN', 'OWNER')

    @property
    def normalized_role(self):
        if self.is_superuser or (self.role or '').upper() == 'AGENCY_ADMIN':
            return 'AGENCY_ADMIN'
        if (self.role or '').upper() in ('PRACTICE_ADMIN', 'ADMIN', 'OWNER'):
            return 'PRACTICE_ADMIN'
        return 'FRONT_DESK'
