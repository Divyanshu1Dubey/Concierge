"""
Custom permissions.
"""
from rest_framework import permissions


class IsStaffUser(permissions.BasePermission):
    """Allow access only to staff users."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type in ('staff', 'admin')


class IsAdminUser(permissions.BasePermission):
    """Allow access only to admin users."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'admin'


class CanManageAppointments(permissions.BasePermission):
    """Check if user can manage appointments."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.user_type == 'admin':
            return True
        try:
            return request.user.staff_profile.can_manage_appointments
        except Exception:
            return False


class CanSendEmails(permissions.BasePermission):
    """Check if user can send emails."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.user_type == 'admin':
            return True
        try:
            return request.user.staff_profile.can_send_emails
        except Exception:
            return False
