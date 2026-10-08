"""
User service layer.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class UserService:
    """High-level user operations."""

    @staticmethod
    def get_active_staff():
        return User.objects.filter(
            user_type__in=['staff', 'admin'], is_active=True
        ).select_related('staff_profile')

    @staticmethod
    def search_users(query):
        return User.objects.filter(
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )
