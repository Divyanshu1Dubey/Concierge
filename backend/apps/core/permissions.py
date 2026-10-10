"""Tenant and Role-based permissions for multi-tenant isolation.
Hierarchy:
  Level 1: AGENCY_ADMIN (Platform-wide administration, practice onboarding, global settings)
  Level 2: PRACTICE_ADMIN (Practice settings, staff, templates, clinic configuration)
  Level 3: FRONT_DESK (Operational daily workflows: Inbox, Patients, Appointments, AI Assistant)
"""
from rest_framework import permissions


class IsAgencyAdmin(permissions.BasePermission):
    """Allows access exclusively to Platform / Agency Administrators."""
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return bool(user.is_superuser or (user.role or '').upper() == 'AGENCY_ADMIN')


class IsPracticeAdmin(permissions.BasePermission):
    """Allows access to Agency Admins, Practice Admins, and Owners."""
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser or (user.role or '').upper() == 'AGENCY_ADMIN':
            return True
        if not user.practice:
            return False
        return (user.role or '').upper() in ('PRACTICE_ADMIN', 'ADMIN', 'OWNER')


class IsTenantAdmin(IsPracticeAdmin):
    """Backward-compatible alias for IsPracticeAdmin."""
    pass


class IsTenantOwner(permissions.BasePermission):
    """Allows access exclusively to Tenant Owners or Agency Admins."""
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser or (user.role or '').upper() == 'AGENCY_ADMIN':
            return True
        return user.practice is not None and (user.role or '').upper() == 'OWNER'


class IsTenantMember(permissions.BasePermission):
    """Allows access to all authenticated staff (Front Desk, Practice Admin, Agency Admin)."""
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser or user.role == 'AGENCY_ADMIN':
            return True
        return user.practice is not None


class IsTenantViewer(IsTenantMember):
    """Allows viewing access to any authenticated tenant staff."""
    pass


class TenantIsolationMixin:
    """
    QuerySet mixin ensuring queries are strictly filtered by the authenticated user's practice.
    Prevents cross-tenant data leaks.
    - Agency Admins can inspect any practice (with optional X-Practice-ID scope)
    - Practice Admins and Front Desk users are strictly restricted to request.user.practice
    """
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (user and user.is_authenticated):
            return qs.none()

        # Check if the model has a direct 'practice' field
        if hasattr(qs.model, 'practice'):
            if user.is_superuser or user.role == 'AGENCY_ADMIN':
                practice_id = (
                    self.request.headers.get('X-Practice-ID') or
                    self.request.query_params.get('practice_id')
                )
                if practice_id:
                    practice = get_request_practice(self.request)
                    return qs.filter(practice=practice) if practice else qs.none()
                # If agency admin has a default practice, scope to it when requested
                scoped = self.request.query_params.get('scoped')
                if scoped and user.practice:
                    return qs.filter(practice=user.practice)
                return qs

            # Strict isolation for tenant staff
            if not user.practice:
                return qs.none()
            return qs.filter(practice=user.practice)

        return qs


PRACTICE_ADMIN_ROLES = ('PRACTICE_ADMIN', 'ADMIN', 'OWNER')
# Roles a practice administrator may assign inside their own practice.
PRACTICE_ASSIGNABLE_ROLES = ('PRACTICE_ADMIN', 'FRONT_DESK', 'OWNER', 'ADMIN')


def is_agency_user(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or (user.role or '').upper() == 'AGENCY_ADMIN'))


def is_practice_admin_user(user) -> bool:
    if not (user and user.is_authenticated):
        return False
    if is_agency_user(user):
        return True
    return bool(user.practice_id) and (user.role or '').upper() in PRACTICE_ADMIN_ROLES


def get_request_practice(request):
    """
    Resolve the tenant for a request from trusted server-side state.

    Tenant staff are always pinned to ``request.user.practice``; any client-supplied
    practice id is ignored. Agency admins may scope to a practice with the
    ``X-Practice-ID`` header or ``practice_id`` query param, falling back to their
    own assigned practice.
    """
    from apps.practices.models import Practice

    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated):
        return None
    if is_agency_user(user):
        practice_id = request.headers.get('X-Practice-ID') or request.GET.get('practice_id')
        if practice_id:
            try:
                return Practice.objects.filter(id=int(practice_id)).first()
            except (TypeError, ValueError):
                return None
        return user.practice
    return user.practice


def can_manage_user(actor, target) -> bool:
    """Whether ``actor`` may modify ``target`` (password reset, role change, deactivate)."""
    if is_agency_user(actor):
        return True
    if is_agency_user(target):
        # Practice-level admins can never act on platform administrators.
        return False
    return is_practice_admin_user(actor) and actor.practice_id is not None and actor.practice_id == target.practice_id
