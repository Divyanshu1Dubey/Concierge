"""Tenant administration views for HeyJarvis Concierge Cloud."""
import io
import re
import secrets
import zipfile
import csv
import logging
from html import escape as html_escape
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.utils import timezone

from .models import Practice, Domain, BookingRules, PracticeSettings, EmailProvider, EmailTemplate, AuditLog
from .serializers import (
    PracticeSerializer, DomainSerializer, BookingRulesSerializer,
    PracticeSettingsSerializer, EmailProviderSerializer, EmailTemplateSerializer,
    AuditLogSerializer, TeamMemberSerializer
)
from apps.core.permissions import (
    IsTenantViewer, IsTenantMember, IsTenantAdmin, IsTenantOwner, IsAgencyAdmin, IsPracticeAdmin,
    get_request_practice, is_agency_user, is_practice_admin_user, can_manage_user,
    PRACTICE_ASSIGNABLE_ROLES,
)
from apps.core.security import redact_dict
from apps.users.account_emails import provision_access, send_set_password_email
from apps.users.models import User
from apps.conversations.models import Conversation
from apps.appointments.models import Appointment

logger = logging.getLogger(__name__)


HOSTNAME_RE = re.compile(r'^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))*$')
# Fields a practice administrator may edit on their own practice record.
PRACTICE_ADMIN_EDITABLE_FIELDS = {
    'name', 'email', 'phone', 'address', 'city', 'state', 'zip_code', 'timezone', 'website', 'logo_url',
}


def resolve_user_practice(request):
    """Resolve practice with agency override support (agency admins fall back to the first practice)."""
    practice = get_request_practice(request)
    if practice is None and is_agency_user(request.user) and not (
        request.headers.get('X-Practice-ID') or request.query_params.get('practice_id')
    ):
        practice = Practice.objects.order_by('id').first()
    return practice


def practice_or_404(request):
    practice = resolve_user_practice(request)
    if not practice:
        return None, Response({'error': 'No practice selected or assigned to this account.'}, status=status.HTTP_404_NOT_FOUND)
    return practice, None


def audit(practice, request, action, details=None):
    """Write an audit entry with secrets redacted and values JSON-safe."""
    clean = {}
    items = details.items() if hasattr(details, 'items') else []
    for k, v in items:
        clean[str(k)] = v if isinstance(v, (str, int, float, bool, type(None), list, dict)) else str(v)
    AuditLog.objects.create(
        practice=practice,
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        details=redact_dict(clean),
        ip_address=request.META.get('REMOTE_ADDR'),
    )


def password_errors(password, user=None):
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        return list(exc.messages)
    return None


def csv_safe(value):
    """Neutralise spreadsheet formula injection in exported cells."""
    if value is None:
        return ''
    text = str(value)
    if text and text[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + text
    return text


def normalize_team_role(value):
    """Map a requested team role onto an allowed practice-level role (never AGENCY_ADMIN)."""
    role = str(value or '').strip().upper()
    legacy = {'MEMBER': 'FRONT_DESK', 'VIEWER': 'FRONT_DESK', 'DOCTOR': 'PRACTICE_ADMIN'}
    role = legacy.get(role, role)
    return role if role in PRACTICE_ASSIGNABLE_ROLES else None


class CurrentTenantView(APIView):
    """Retrieve or update current tenant business information."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        practice = resolve_user_practice(request)
        if not practice:
            return Response({'error': 'No practice assigned to user'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PracticeSerializer(practice)
        return Response(serializer.data)

    def put(self, request):
        practice = resolve_user_practice(request)
        if not practice:
            return Response({'error': 'No practice assigned to user'}, status=status.HTTP_404_NOT_FOUND)
        if not is_practice_admin_user(request.user):
            return Response({'error': 'Practice administrator permissions required'}, status=status.HTTP_403_FORBIDDEN)

        data = dict(request.data.items())
        if not is_agency_user(request.user):
            # Practice admins cannot change tenant status, subscription or slug.
            data = {k: v for k, v in data.items() if k in PRACTICE_ADMIN_EDITABLE_FIELDS}
        serializer = PracticeSerializer(practice, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        audit(practice, request, 'BUSINESS_SETTINGS_UPDATED', data)
        return Response(serializer.data)

    def patch(self, request):
        return self.put(request)


class AgencyPracticeListView(APIView):
    """List all practices for Agency Admin, or onboard/create a new practice."""
    permission_classes = [permissions.IsAuthenticated, IsAgencyAdmin]

    def get(self, request):
        practices = Practice.objects.all().order_by('-created_at')
        results = []
        for p in practices:
            admin_user = p.users.filter(role__in=['PRACTICE_ADMIN', 'ADMIN', 'OWNER']).first()
            staff_count = p.users.count()
            conv_count = Conversation.objects.filter(practice=p).count()
            appt_count = Appointment.objects.filter(practice=p).count()
            results.append({
                'id': p.id,
                'name': p.name,
                'slug': p.slug,
                'email': p.email,
                'phone': p.phone,
                'city': p.city,
                'state': p.state,
                'active': p.active,
                'subscription_status': p.subscription_status,
                'client_key': p.api_key,
                'admin_name': admin_user.full_name if admin_user else 'Unassigned',
                'admin_email': admin_user.email if admin_user else 'None',
                'staff_count': staff_count,
                'conversation_count': conv_count,
                'appointment_count': appt_count,
                'created_at': p.created_at.isoformat(),
            })
        return Response({'count': len(results), 'results': results})

    def post(self, request):
        data = request.data
        name = str(data.get('name', '')).strip()
        email = str(data.get('email', '')).strip().lower()
        if not name or not email:
            return Response({'error': 'Practice name and email are required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_email(email)
        except DjangoValidationError:
            return Response({'error': 'Enter a valid practice email address.'}, status=status.HTTP_400_BAD_REQUEST)

        admin_email = str(data.get('admin_email', '')).strip().lower()
        admin_name = str(data.get('admin_name', '')).strip()
        admin_password = str(data.get('admin_password', '') or '')
        if admin_email:
            try:
                validate_email(admin_email)
            except DjangoValidationError:
                return Response({'error': 'Enter a valid administrator email address.'}, status=status.HTTP_400_BAD_REQUEST)
            if User.objects.filter(email__iexact=admin_email).exists():
                return Response({'error': f"A user with email '{admin_email}' already exists."}, status=status.HTTP_400_BAD_REQUEST)
            if admin_password:
                errors = password_errors(admin_password, User(email=admin_email))
                if errors:
                    return Response({'error': ' '.join(errors)}, status=status.HTTP_400_BAD_REQUEST)

        slug = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower()).strip('-')
        base_slug = slug or 'practice'
        c = 1
        while Practice.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{c}"
            c += 1

        with transaction.atomic():
            practice = self._create_practice(request, data, name, slug, email, admin_email, admin_name, admin_password)

        data_out = PracticeSerializer(practice).data
        if admin_email:
            admin_user = User.objects.filter(email__iexact=admin_email, practice=practice).first()
            if admin_user:
                data_out['admin_access'] = provision_access(admin_user, admin_password, request)
        return Response(data_out, status=status.HTTP_201_CREATED)

    def _create_practice(self, request, data, name, slug, email, admin_email, admin_name, admin_password):
        practice = Practice.objects.create(
            name=name,
            slug=slug,
            email=email,
            phone=data.get('phone', '919-555-0100'),
            address=data.get('address', '100 Medical Park Blvd'),
            city=data.get('city', 'Raleigh'),
            state=data.get('state', 'NC'),
            zip_code=data.get('zip_code', '27601'),
            timezone=data.get('timezone', 'America/New_York'),
            website=data.get('website', ''),
            active=str(data.get('active', True)).lower() not in ('false', '0'),
            subscription_status=data.get('subscription_status', 'active'),
        )

        BookingRules.objects.get_or_create(practice=practice)
        PracticeSettings.objects.get_or_create(
            practice=practice,
            defaults={
                'widget_title': f"{name} Concierge",
                'default_from_name': name,
                'default_from_email': email,
            }
        )

        if admin_email:
            first_name = admin_name.split()[0] if admin_name else 'Admin'
            last_name = ' '.join(admin_name.split()[1:]) if ' ' in admin_name else ''
            User.objects.create_user(
                email=admin_email,
                username=admin_email,
                password=admin_password or None,
                first_name=first_name,
                last_name=last_name,
                role='PRACTICE_ADMIN',
                practice=practice,
                is_active=True,
            )

        audit(practice, request, 'PRACTICE_ONBOARDED', {
            'created_by': request.user.email, 'practice': name, 'admin_email': admin_email or None,
        })
        return practice


class AgencyPracticeToggleStatusView(APIView):
    """Enable or disable practice account."""
    permission_classes = [permissions.IsAuthenticated, IsAgencyAdmin]

    def post(self, request, id):
        practice = get_object_or_404(Practice, id=id)
        practice.active = not practice.active
        practice.save(update_fields=['active', 'updated_at'])
        AuditLog.objects.create(
            practice=practice,
            actor=request.user,
            action='PRACTICE_STATUS_TOGGLED',
            details={'active': practice.active},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return Response({'id': practice.id, 'active': practice.active, 'name': practice.name})


class AgencyPracticeUsersView(APIView):
    """List or add doctors and front-desk staff to a specific dentistry practice."""
    permission_classes = [permissions.IsAuthenticated]

    def _get_practice(self, request, practice_id):
        user = request.user
        if user.is_superuser or (user.role or '').upper() == 'AGENCY_ADMIN':
            return get_object_or_404(Practice, id=practice_id)
        if user.practice and user.practice.id == practice_id and (user.role or '').upper() in ('PRACTICE_ADMIN', 'ADMIN', 'OWNER'):
            return user.practice
        return None

    def get(self, request, practice_id):
        practice = self._get_practice(request, practice_id)
        if not practice:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        users = practice.users.all().order_by('-created_at')
        results = []
        for u in users:
            results.append({
                'id': str(u.id),
                'email': u.email,
                'first_name': u.first_name,
                'last_name': u.last_name,
                'full_name': u.full_name,
                'phone': u.phone,
                'role': u.role,
                'normalized_role': u.normalized_role,
                'is_active': u.is_active,
                'created_at': u.created_at.isoformat(),
                'last_login': u.last_login.isoformat() if u.last_login else None,
            })
        return Response({
            'count': len(results),
            'results': results,
            'practice': {'id': practice.id, 'name': practice.name, 'slug': practice.slug, 'client_key': practice.api_key}
        })

    def post(self, request, practice_id):
        practice = self._get_practice(request, practice_id)
        if not practice:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        email = str(data.get('email', '')).strip().lower()
        password = str(data.get('password', '') or '')
        first_name = str(data.get('first_name', '')).strip()
        last_name = str(data.get('last_name', '')).strip()
        role = str(data.get('role', 'FRONT_DESK') or 'FRONT_DESK').upper()
        phone = str(data.get('phone', '')).strip()

        if not email:
            return Response({'error': 'Email (login ID) is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_email(email)
        except DjangoValidationError:
            return Response({'error': 'Enter a valid email address.'}, status=status.HTTP_400_BAD_REQUEST)
        if password:
            errors = password_errors(password, User(email=email, first_name=first_name, last_name=last_name))
            if errors:
                return Response({'error': ' '.join(errors)}, status=status.HTTP_400_BAD_REQUEST)

        if role not in PRACTICE_ASSIGNABLE_ROLES:
            return Response({'error': 'Invalid role. Choose PRACTICE_ADMIN or FRONT_DESK.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email__iexact=email).exists():
            return Response({'error': f"User with email '{email}' already exists."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            email=email,
            username=email,
            password=password or None,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=role,
            practice=practice,
            is_active=True
        )

        audit(practice, request, 'USER_CREATED_BY_AGENCY', {'email': email, 'role': role, 'created_by': request.user.email})
        access = provision_access(user, password, request)

        return Response({
            **access,
            'id': str(user.id),
            'email': user.email,
            'full_name': user.full_name,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.role,
            'normalized_role': user.normalized_role,
            'is_active': user.is_active,
            'practice_id': practice.id,
            'message': (
                f"Invite email sent to {email}." if access.get('invite_sent')
                else f"Account for {email} created."
            ),
        }, status=status.HTTP_201_CREATED)


class AgencyPracticeUserActionView(APIView):
    """Reset password, toggle status, or remove a doctor/staff user in a dentistry practice."""
    permission_classes = [permissions.IsAuthenticated]

    def _get_target(self, request, practice_id, user_id):
        user = request.user
        is_agency = user.is_superuser or (user.role or '').upper() == 'AGENCY_ADMIN'
        if is_agency:
            practice = get_object_or_404(Practice, id=practice_id)
        elif user.practice and user.practice.id == practice_id and (user.role or '').upper() in ('PRACTICE_ADMIN', 'ADMIN', 'OWNER'):
            practice = user.practice
        else:
            return None, None
        target_user = get_object_or_404(User, id=user_id, practice=practice)
        if not can_manage_user(user, target_user):
            return None, None
        return practice, target_user

    def post(self, request, practice_id, user_id):
        action = request.data.get('action') or request.query_params.get('action')
        practice, target_user = self._get_target(request, practice_id, user_id)
        if not target_user:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        if action == 'send_password_link':
            invite = not target_user.has_usable_password()
            if not send_set_password_email(target_user, request, invite=invite):
                return Response({'success': False, 'error': 'The email could not be sent. Check the server email settings.'},
                                status=status.HTTP_502_BAD_GATEWAY)
            audit(practice, request, 'USER_PASSWORD_LINK_SENT', {'target_email': target_user.email})
            return Response({'success': True, 'message': f"A {'set-password' if invite else 'password reset'} link was emailed to {target_user.email}."})

        if action == 'reset_password':
            new_password = str(request.data.get('password', '') or '')
            if not new_password:
                return Response({'error': 'New password is required.'}, status=status.HTTP_400_BAD_REQUEST)
            errors = password_errors(new_password, target_user)
            if errors:
                return Response({'error': ' '.join(errors)}, status=status.HTTP_400_BAD_REQUEST)
            target_user.set_password(new_password)
            target_user.save()
            audit(practice, request, 'USER_PASSWORD_RESET', {'target_email': target_user.email, 'reset_by': request.user.email})
            return Response({'success': True, 'message': f"Password for {target_user.email} updated successfully."})

        elif action == 'toggle_status':
            if target_user == request.user:
                return Response({'error': 'You cannot deactivate your own account.'}, status=status.HTTP_400_BAD_REQUEST)
            target_user.is_active = not target_user.is_active
            target_user.save(update_fields=['is_active'])
            audit(practice, request, 'USER_STATUS_TOGGLED', {'target_email': target_user.email, 'is_active': target_user.is_active})
            return Response({'id': str(target_user.id), 'is_active': target_user.is_active, 'email': target_user.email})

        return Response({'error': 'Invalid action. Supported actions: send_password_link, reset_password, toggle_status'}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, practice_id, user_id):
        practice, target_user = self._get_target(request, practice_id, user_id)
        if not target_user:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        if target_user == request.user:
            return Response({'error': 'Cannot delete your own account.'}, status=status.HTTP_400_BAD_REQUEST)

        target_user.is_active = False
        target_user.save(update_fields=['is_active'])
        audit(practice, request, 'USER_DEACTIVATED', {'target_email': target_user.email})
        return Response({'status': 'deactivated', 'id': str(target_user.id)})


class AgencyPracticeIntegrationView(APIView):
    """Retrieve full embed instructions, script tags, and WordPress plugin link for a specific practice."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, practice_id):
        user = request.user
        is_agency = user.is_superuser or (user.role or '').upper() == 'AGENCY_ADMIN'
        if is_agency:
            practice = get_object_or_404(Practice, id=practice_id)
        elif user.practice and user.practice.id == practice_id:
            practice = user.practice
        else:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        backend_url = (getattr(settings, 'APP_PUBLIC_URL', None) or request.build_absolute_uri('/')).rstrip('/')
        frontend_url = (getattr(settings, 'FRONTEND_URL', None) or backend_url).rstrip('/')

        script_tag = f'<script async src="{backend_url}/widget.js" data-api-url="{backend_url}" data-practice="{practice.slug}" data-heyjarvis-client="{practice.api_key}"></script>'
        iframe_tag = f'<iframe src="{frontend_url}/concierge/{practice.slug}" width="100%" height="700" frameborder="0" style="border:none;border-radius:16px;"></iframe>'

        return Response({
            'practice_id': practice.id,
            'practice_name': practice.name,
            'practice_slug': practice.slug,
            'client_key': practice.api_key,
            'embed_script': script_tag,
            'iframe_snippet': iframe_tag,
            'hosted_concierge_url': f"{frontend_url}/concierge/{practice.slug}",
            'wordpress_download_url': f"/api/practices/{practice.id}/integration/wordpress/",
            'quick_instructions': {
                'wordpress': "1. Download the custom WordPress Plugin ZIP for this dentistry. 2. In WordPress Admin, go to Plugins > Add New > Upload Plugin. 3. Activate the plugin. The client key is pre-configured!",
                'script': "Paste the async JavaScript snippet before the closing </body> tag on any website (Squarespace, Wix, Webflow, Shopify, HTML).",
                'iframe': "Embed the 24/7 AI Concierge inside any website page or modal container.",
                'direct_link': "Use this hosted link directly in SMS reminders, marketing campaigns, or a 'Book Appointment Online' button."
            }
        })


class RegenerateClientKeyView(APIView):
    """Regenerate public client key with security warning."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def post(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        new_key = practice.regenerate_api_key(
            actor=request.user,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return Response({
            'client_key': new_key,
            'warning': 'Existing website installations using the old key will stop working until updated with this new key.',
            'timestamp': timezone.now().isoformat()
        })


class DomainListCreateView(APIView):
    """List or add allowed domains for widget origin validation."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        serializer = DomainSerializer(practice.domains.all(), many=True)
        return Response(serializer.data)

    def post(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        hostname = str(request.data.get('hostname', '')).strip().lower()
        if not hostname:
            return Response({'error': 'Hostname is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Clean protocol / path / port if present
        from urllib.parse import urlparse
        if '://' in hostname:
            hostname = urlparse(hostname).hostname or ''
        hostname = hostname.split('/')[0].split(':')[0].strip('.')
        if not HOSTNAME_RE.match(hostname):
            return Response({'error': 'Enter a valid domain name, e.g. www.example.com'}, status=status.HTTP_400_BAD_REQUEST)

        domain, created = Domain.objects.get_or_create(
            practice=practice,
            hostname=hostname,
            defaults={'status': 'CONNECTED'}
        )

        if created:
            audit(practice, request, 'DOMAIN_ADDED', {'hostname': hostname})
        serializer = DomainSerializer(domain)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class DomainDeleteView(APIView):
    """Remove an allowed domain."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def delete(self, request, id):
        practice, error = practice_or_404(request)
        if error:
            return error
        domain = get_object_or_404(Domain, id=id, practice=practice)
        hostname = domain.hostname
        domain.delete()
        audit(practice, request, 'DOMAIN_REMOVED', {'hostname': hostname})
        return Response({'status': 'deleted', 'hostname': hostname})


class BookingRulesView(APIView):
    """Retrieve or update booking rules and business hours."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        rules, _ = BookingRules.objects.get_or_create(practice=practice)
        data = BookingRulesSerializer(rules).data
        data['hours'] = data.get('business_hours') or {}
        return Response(data)

    def put(self, request):
        if not is_practice_admin_user(request.user):
            return Response({'error': 'Practice administrator permissions required'}, status=status.HTTP_403_FORBIDDEN)
        practice, error = practice_or_404(request)
        if error:
            return error
        rules, _ = BookingRules.objects.get_or_create(practice=practice)
        payload = dict(request.data.items())
        if 'hours' in payload and 'business_hours' not in payload:
            payload['business_hours'] = payload.pop('hours')
        serializer = BookingRulesSerializer(rules, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(practice, request, 'BOOKING_RULES_UPDATED', payload)
        data = serializer.data
        data['hours'] = data.get('business_hours') or {}
        return Response(data)

    def patch(self, request):
        return self.put(request)


class TenantSettingsView(APIView):
    """Retrieve or update practice settings (AI, notification toggles, widget appearance)."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        st, _ = PracticeSettings.objects.get_or_create(practice=practice)
        return Response(PracticeSettingsSerializer(st).data)

    def put(self, request):
        if not is_practice_admin_user(request.user):
            return Response({'error': 'Practice administrator permissions required'}, status=status.HTTP_403_FORBIDDEN)
        practice, error = practice_or_404(request)
        if error:
            return error
        st, _ = PracticeSettings.objects.get_or_create(practice=practice)
        serializer = PracticeSettingsSerializer(st, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(practice, request, 'SETTINGS_UPDATED', request.data)
        return Response(serializer.data)

    def patch(self, request):
        return self.put(request)


class EmailConfigView(APIView):
    """Retrieve or configure email provider (Managed vs Custom SMTP)."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        provider = practice.email_providers.first()
        if not provider:
            provider = EmailProvider.objects.create(
                practice=practice,
                provider_type='managed',
                is_active=True,
                is_default=True,
                from_name=practice.name,
                from_email=practice.email,
            )
        data = dict(EmailProviderSerializer(provider).data)
        # Lets the UI show whether platform ("managed") email can actually send.
        data['platform_email_configured'] = bool(getattr(settings, 'EMAIL_CONFIGURED', False))
        return Response(data)

    def put(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        provider = practice.email_providers.first()
        if not provider:
            provider = EmailProvider(practice=practice)

        data = dict(request.data.items())
        raw_pwd = data.pop('smtp_password', None)
        if isinstance(raw_pwd, list):
            raw_pwd = raw_pwd[0] if raw_pwd else None
        effective_type = data.get('provider_type', provider.provider_type)
        if effective_type == 'smtp':
            if not (data.get('smtp_host') or provider.smtp_host) or not (data.get('smtp_port') or provider.smtp_port):
                return Response({'error': 'SMTP host and port are required for custom SMTP.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = EmailProviderSerializer(provider, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        if raw_pwd:
            provider.set_smtp_password(raw_pwd)
            provider.save(update_fields=['smtp_password'])

        audit(practice, request, 'EMAIL_CONFIG_UPDATED', {'provider_type': provider.provider_type, 'from_email': provider.from_email})
        return Response(EmailProviderSerializer(provider).data)

    def patch(self, request):
        return self.put(request)


class TestEmailConnectionView(APIView):
    """Test SMTP or Managed email delivery."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def post(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        provider = practice.email_providers.first()
        if not provider:
            # Same default the Email Settings page creates: HeyJarvis managed email.
            provider = EmailProvider.objects.create(
                practice=practice, provider_type='managed', is_active=True, is_default=True,
                from_name=practice.name, from_email=practice.email,
            )

        test_result = provider.test_connection(send_to=request.user.email)
        audit(practice, request, 'EMAIL_TEST_SENT', {'success': test_result.get('success'), 'to': request.user.email})
        return Response(test_result)


class EmailTemplateListView(generics.ListCreateAPIView):
    """List or create tenant email templates."""
    serializer_class = EmailTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    DEFAULT_TEMPLATES = [
        {
            'template_type': 'new_patient',
            'subject': 'Your appointment request with {{practice}}',
            'body': "Hi {{patient_name}},\n\nThank you for your request. We have you down for {{preferred_date}} "
                    "({{preferred_time}}) and our front desk will confirm the exact time with you shortly.\n\n"
                    "Thank you,\n{{practice}}",
        },
        {
            'template_type': 'question',
            'subject': 'Your visit to {{practice}}',
            'body': "Hi {{patient_name}},\n\nThank you for reaching out to us. We would be delighted to coordinate your visit.\n\n"
                    "Best regards,\n{{practice}} Front Desk",
        },
    ]

    def get_queryset(self):
        practice = resolve_user_practice(self.request)
        if not practice:
            return EmailTemplate.objects.none()
        qs = EmailTemplate.objects.filter(practice=practice)
        if not qs.exists():
            # Seed sensible starting templates the first time a practice opens the page.
            for tpl in self.DEFAULT_TEMPLATES:
                EmailTemplate.objects.get_or_create(practice=practice, template_type=tpl['template_type'], defaults=tpl)
            qs = EmailTemplate.objects.filter(practice=practice)
        return qs

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.filter_queryset(self.get_queryset()), many=True)
        return Response({'templates': serializer.data, 'results': serializer.data, 'count': len(serializer.data)})

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError, NotFound
        practice = resolve_user_practice(self.request)
        if not practice:
            raise NotFound('No practice selected or assigned to this account.')
        template_type = serializer.validated_data.get('template_type')
        if EmailTemplate.objects.filter(practice=practice, template_type=template_type).exists():
            raise ValidationError({'template_type': ['A template of this type already exists. Edit the existing one instead.']})
        serializer.save(practice=practice)


class EmailTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, or delete a tenant email template."""
    serializer_class = EmailTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]
    lookup_field = 'id'

    def get_queryset(self):
        return EmailTemplate.objects.filter(practice=resolve_user_practice(self.request))

    def perform_update(self, serializer):
        from rest_framework.exceptions import ValidationError
        instance = serializer.instance
        template_type = serializer.validated_data.get('template_type', instance.template_type)
        if EmailTemplate.objects.filter(practice=instance.practice, template_type=template_type).exclude(id=instance.id).exists():
            raise ValidationError({'template_type': ['A template of this type already exists.']})
        serializer.save()


class TeamListView(APIView):
    """List or invite team members for the practice."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        members = User.objects.filter(practice=practice).order_by('-created_at')
        data = TeamMemberSerializer(members, many=True).data
        return Response({'team': data, 'results': data, 'count': len(data)})

    def post(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        email = str(request.data.get('email', '')).strip().lower()
        role = normalize_team_role(request.data.get('role') or 'FRONT_DESK')
        first_name = str(request.data.get('first_name', '')).strip()
        last_name = str(request.data.get('last_name', '')).strip()
        password = str(request.data.get('password', '') or '')

        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_email(email)
        except DjangoValidationError:
            return Response({'error': 'Enter a valid email address.'}, status=status.HTTP_400_BAD_REQUEST)
        if role is None:
            return Response({'error': 'Invalid role. Choose PRACTICE_ADMIN or FRONT_DESK.'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email__iexact=email).exists():
            return Response({'error': 'User with this email already exists'}, status=status.HTTP_400_BAD_REQUEST)

        if password:
            errors = password_errors(password, User(email=email, first_name=first_name, last_name=last_name))
            if errors:
                return Response({'error': ' '.join(errors)}, status=status.HTTP_400_BAD_REQUEST)

        new_user = User.objects.create_user(
            email=email,
            username=email,
            password=password or None,
            first_name=first_name,
            last_name=last_name,
            role=role,
            practice=practice,
            is_active=True
        )
        audit(practice, request, 'TEAM_MEMBER_INVITED', {'email': email, 'role': role})
        data = TeamMemberSerializer(new_user).data
        # invite_sent, or a one-time temporary_password when the invite email could not be sent.
        data.update(provision_access(new_user, password, request))
        return Response(data, status=status.HTTP_201_CREATED)


class TeamMemberDetailView(APIView):
    """Update role or remove team member."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def _member(self, request, id):
        practice = resolve_user_practice(request)
        member = get_object_or_404(User, id=id, practice=practice)
        if not can_manage_user(request.user, member):
            return practice, None
        return practice, member

    def put(self, request, id):
        practice, member = self._member(request, id)
        if member is None:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        if member == request.user:
            return Response({'error': 'You cannot change your own role.'}, status=status.HTTP_400_BAD_REQUEST)
        new_role = normalize_team_role(request.data.get('role'))
        if not new_role:
            return Response({'error': 'Invalid role'}, status=status.HTTP_400_BAD_REQUEST)
        member.role = new_role
        member.save(update_fields=['role'])
        audit(practice, request, 'TEAM_MEMBER_ROLE_CHANGED', {'email': member.email, 'role': new_role})
        return Response(TeamMemberSerializer(member).data)

    def patch(self, request, id):
        return self.put(request, id)

    def delete(self, request, id):
        practice, member = self._member(request, id)
        if member is None:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        if member == request.user:
            return Response({'error': 'Cannot remove yourself'}, status=status.HTTP_400_BAD_REQUEST)
        member.is_active = False
        member.save(update_fields=['is_active'])
        audit(practice, request, 'TEAM_MEMBER_DISABLED', {'email': member.email})
        return Response({'status': 'disabled', 'id': str(member.id)})


class AuditLogListView(generics.ListAPIView):
    """Retrieve audit log for current tenant."""
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get_queryset(self):
        return AuditLog.objects.filter(practice=resolve_user_practice(self.request)).select_related('actor').order_by('-created_at')


class TenantMetricsView(APIView):
    """Real metrics for dashboard overview."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        practice = resolve_user_practice(request)
        if not practice:
            return Response({})

        conv_qs = Conversation.objects.filter(practice=practice)
        appt_qs = Appointment.objects.filter(practice=practice)

        total_conv = conv_qs.count()
        total_leads = appt_qs.count()
        completed = appt_qs.filter(status__in=['confirmed', 'completed', 'contacted']).count()
        emergency = appt_qs.filter(urgency='URGENT').count()
        appointment_reqs = appt_qs.filter(intent__in=['new_patient', 'cleaning', 'appointment']).count()
        handoffs = conv_qs.filter(status='handoff').count()

        conv_rate = round((total_leads / total_conv * 100), 1) if total_conv > 0 else 0.0

        from apps.emails.models import Email
        email_qs = Email.objects.filter(thread__practice=practice, direction=Email.DIRECTION_OUTGOING)
        emails_sent = email_qs.filter(status=Email.STATUS_SENT).count()
        emails_failed = email_qs.filter(status=Email.STATUS_FAILED).count()
        attempted = emails_sent + emails_failed
        email_delivery = round(emails_sent / attempted * 100, 1) if attempted else None

        return Response({
            'conversations': total_conv,
            'new_leads': total_leads,
            'completed_requests': completed,
            'emergency_requests': emergency,
            'appointment_requests': appointment_reqs,
            'human_handoffs': handoffs,
            'completion_rate': f"{conv_rate}%",
            'emails_sent': emails_sent,
            'emails_failed': emails_failed,
            'email_delivery': email_delivery,
            'system_status': 'operational',
            'client_key': practice.api_key,
            'practice_name': practice.name,
            'practice_slug': practice.slug,
        })


class WordPressDownloadView(APIView):
    """Dynamically build and return the configured WordPress plugin zip."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request, tenant_id=None):
        if tenant_id:
            if request.user.is_agency_admin or request.user.is_superuser:
                practice = get_object_or_404(Practice, id=tenant_id)
            elif request.user.practice and str(request.user.practice.id) == str(tenant_id):
                practice = request.user.practice
            else:
                return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        elif resolve_user_practice(request):
            practice = resolve_user_practice(request)
        else:
            return Response({'error': 'No practice associated with your account.'}, status=status.HTTP_400_BAD_REQUEST)

        if not practice:
            return Response({'error': 'No practice found.'}, status=status.HTTP_404_NOT_FOUND)

        client_key = practice.api_key
        slug = practice.slug
        # The name is interpolated into PHP source: keep only safe characters so a
        # crafted practice name can never inject PHP/HTML into the generated plugin.
        practice_name = html_escape(re.sub(r"[^\w\s&.,()-]", '', practice.name))

        base_url = (getattr(settings, 'APP_PUBLIC_URL', '') or request.build_absolute_uri('/')).rstrip('/')

        # PHP plugin code
        plugin_php = f"""<?php
/**
 * Plugin Name: HeyJarvis Concierge - {practice_name}
 * Plugin URI: {base_url}
 * Description: Real AI Dental Concierge for {practice_name}. Connects your WordPress site directly to your front desk.
 * Version: 1.0.0
 * Author: HeyJarvis
 * License: Proprietary
 */

if (!defined('ABSPATH')) exit;

define('HEYJARVIS_CLIENT_KEY', '{client_key}');
define('HEYJARVIS_PUBLIC_URL', '{base_url}');
define('HEYJARVIS_PRACTICE_SLUG', '{slug}');

add_action('wp_enqueue_scripts', function() {{
    $client_key = get_option('heyjarvis_client_key', HEYJARVIS_CLIENT_KEY);
    $public_url = get_option('heyjarvis_public_url', HEYJARVIS_PUBLIC_URL);

    wp_enqueue_script(
        'heyjarvis-concierge-widget',
        $public_url . '/widget.js',
        array(),
        '1.0.0',
        true
    );
}});

// wp_script_add_data() does not render data-* attributes, so add them to the tag here.
add_filter('script_loader_tag', function($tag, $handle, $src) {{
    if ($handle !== 'heyjarvis-concierge-widget') return $tag;
    $client_key = get_option('heyjarvis_client_key', HEYJARVIS_CLIENT_KEY);
    $public_url = get_option('heyjarvis_public_url', HEYJARVIS_PUBLIC_URL);
    return sprintf(
        '<script async src="%s" data-api-url="%s" data-practice="%s" data-heyjarvis-client="%s"></script>' . "\n",
        esc_url($src), esc_attr($public_url), esc_attr(HEYJARVIS_PRACTICE_SLUG), esc_attr($client_key)
    );
}}, 10, 3);

add_action('admin_menu', function() {{
    add_options_page('HeyJarvis Concierge', 'HeyJarvis', 'manage_options', 'heyjarvis-settings', function() {{
        if (isset($_POST['heyjarvis_save'])) {{
            check_admin_referer('heyjarvis_nonce');
            update_option('heyjarvis_client_key', sanitize_text_field($_POST['client_key']));
            echo '<div class="notice notice-success"><p>Settings saved!</p></div>';
        }}
        $current_key = get_option('heyjarvis_client_key', HEYJARVIS_CLIENT_KEY);
        ?>
        <div class="wrap">
            <h1>HeyJarvis Concierge Settings</h1>
            <p>Your site is configured for <strong>{practice_name}</strong>.</p>
            <form method="post">
                <?php wp_nonce_field('heyjarvis_nonce'); ?>
                <table class="form-table">
                    <tr>
                        <th scope="row">Public Client Key</th>
                        <td><input type="text" name="client_key" value="<?php echo esc_attr($current_key); ?>" class="regular-text" style="font-family:monospace;" /></td>
                    </tr>
                </table>
                <p class="submit"><input type="submit" name="heyjarvis_save" class="button-primary" value="Save Changes" /></p>
            </form>
        </div>
        <?php
    }});
}});
"""

        readme_txt = f"""=== HeyJarvis Concierge ===
Tags: ai, chat, dental, concierge, appointments
Requires at least: 5.8
Tested up to: 6.5
Stable tag: 1.0.0

HeyJarvis Concierge delivers intelligent AI front-desk coordination for {practice_name}.
"""

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('heyjarvis-concierge/heyjarvis-concierge.php', plugin_php)
            zip_file.writestr('heyjarvis-concierge/readme.txt', readme_txt)

        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="heyjarvis-concierge-{slug}.zip"'
        return response


class ExportDataView(APIView):
    """Export tenant leads or conversations as CSV."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get(self, request, export_type):
        practice = resolve_user_practice(request)

        if not practice:
            return Response({'error': 'No practice selected or found for export.'}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(content_type='text/csv')

        if export_type in ('leads', 'conversations'):
            audit(practice, request, 'DATA_EXPORTED', {'export_type': export_type})

        if export_type == 'leads':
            response['Content-Disposition'] = f'attachment; filename="leads-{practice.slug}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Patient Name', 'Email', 'Phone', 'Service', 'Intent', 'Preferred Date', 'Preferred Time', 'Status', 'Urgency', 'Created At'])
            for a in Appointment.objects.filter(practice=practice):
                writer.writerow([csv_safe(v) for v in (a.patient_name, a.patient_email, a.patient_phone, a.service_name, a.intent, a.preferred_date, a.preferred_time, a.status, a.urgency, a.created_at.strftime('%Y-%m-%d %H:%M'))])
            return response

        elif export_type == 'conversations':
            response['Content-Disposition'] = f'attachment; filename="conversations-{practice.slug}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Conversation ID', 'Patient Name', 'Email', 'Phone', 'Intent', 'State', 'Status', 'Started At', 'Summary'])
            for c in Conversation.objects.filter(practice=practice):
                writer.writerow([csv_safe(v) for v in (str(c.id), c.patient_name, c.patient_email, c.patient_phone, c.intent, c.state, c.status, c.started_at.strftime('%Y-%m-%d %H:%M'), c.summary)])
            return response

        return Response({'error': 'Invalid export type. Use "leads" or "conversations"'}, status=status.HTTP_400_BAD_REQUEST)


class AccessRequestCreateView(APIView):
    """Public: a practice asks to be onboarded. Stored for agency review; no account is created."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    from rest_framework.throttling import ScopedRateThrottle as _ScopedRateThrottle
    throttle_classes = [_ScopedRateThrottle]
    throttle_scope = 'auth'

    LIMITS = {'practice_name': 200, 'contact_name': 200, 'email': 254, 'phone': 40, 'website': 300, 'message': 2000}

    def post(self, request):
        from .models import AccessRequest
        data = {k: str(request.data.get(k) or '').strip()[:n] for k, n in self.LIMITS.items()}
        # Hidden field real visitors never fill in; bots usually do.
        if str(request.data.get('company_fax') or '').strip():
            return Response({'status': 'received'}, status=status.HTTP_201_CREATED)
        errors = {}
        for field in ('practice_name', 'contact_name', 'email'):
            if not data[field]:
                errors[field] = 'This field is required.'
        if data['email'] and 'email' not in errors:
            try:
                validate_email(data['email'])
            except DjangoValidationError:
                errors['email'] = 'Enter a valid email address.'
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        req = AccessRequest.objects.create(**data)
        _notify_agency_of_access_request(req)
        return Response({'status': 'received'}, status=status.HTTP_201_CREATED)


def _notify_agency_of_access_request(req):
    """Best-effort email to agency admins; the request is already stored either way."""
    if not getattr(settings, 'EMAIL_CONFIGURED', False):
        return
    from django.core.mail import send_mail
    from django.db.models import Q
    recipients = list(
        User.objects.filter(Q(is_superuser=True) | Q(role='AGENCY_ADMIN'), is_active=True)
        .exclude(email='').values_list('email', flat=True)
    )
    if not recipients:
        return
    base = (getattr(settings, 'APP_PUBLIC_URL', '') or '').rstrip('/')
    body = (
        f"New onboarding request from {req.practice_name}.\n\n"
        f"Contact: {req.contact_name} <{req.email}> {req.phone}\nWebsite: {req.website}\n\n{req.message}\n\n"
        f"Review it in Concierge: {base}/dashboard/practices\n"
    )
    try:
        send_mail(f"Access request: {req.practice_name}", body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    except Exception as exc:
        logger.warning("Access request notification failed: %s", type(exc).__name__)


class AccessRequestListView(APIView):
    """Agency admins: review onboarding requests."""
    permission_classes = [permissions.IsAuthenticated, IsAgencyAdmin]

    def get(self, request):
        from .models import AccessRequest
        rows = AccessRequest.objects.select_related('handled_by')[:200]
        return Response({'results': [
            {
                'id': r.id, 'practice_name': r.practice_name, 'contact_name': r.contact_name, 'email': r.email,
                'phone': r.phone, 'website': r.website, 'message': r.message, 'status': r.status,
                'handled_by': r.handled_by.email if r.handled_by else None, 'created_at': r.created_at,
            } for r in rows
        ]})


class AccessRequestDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAgencyAdmin]

    def patch(self, request, id):
        from .models import AccessRequest
        req = get_object_or_404(AccessRequest, pk=id)
        new_status = request.data.get('status')
        if new_status not in dict(AccessRequest.STATUS_CHOICES):
            return Response({'status': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)
        req.status = new_status
        req.handled_by = request.user
        req.save(update_fields=['status', 'handled_by', 'updated_at'])
        return Response({'id': req.id, 'status': req.status})


# ── Practice knowledge ────────────────────────────────────────────────────────

def _knowledge_row(e):
    return {
        'id': e.id, 'category': e.category, 'title': e.title, 'content': e.content, 'is_active': e.is_active,
        'updated_at': e.updated_at, 'updated_by': (e.updated_by.get_full_name() or e.updated_by.email) if e.updated_by else '',
    }


def _clean_knowledge(data, partial=False):
    from .models import KnowledgeEntry
    out, errors = {}, {}
    if 'category' in data or not partial:
        cat = str(data.get('category') or 'faq')
        if cat not in dict(KnowledgeEntry.CATEGORY_CHOICES):
            errors['category'] = 'Unknown category.'
        out['category'] = cat
    if 'title' in data or not partial:
        title = str(data.get('title') or '').strip()
        if not title:
            errors['title'] = 'Add a short question or title.'
        out['title'] = title[:200]
    if 'content' in data or not partial:
        content = str(data.get('content') or '').strip()
        if not content:
            errors['content'] = 'Add the answer patients should get.'
        out['content'] = content[:3000]
    if 'is_active' in data:
        out['is_active'] = bool(data.get('is_active'))
    return out, errors


class KnowledgeListView(APIView):
    """Practice knowledge entries: everyone on the team can read; practice admins edit."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        from .models import KnowledgeEntry
        practice, error = practice_or_404(request)
        if error:
            return error
        rows = KnowledgeEntry.objects.filter(practice=practice).select_related('updated_by')
        return Response({'results': [_knowledge_row(e) for e in rows]})

    def post(self, request):
        from .models import KnowledgeEntry
        if not is_practice_admin_user(request.user):
            return Response({'error': 'Only practice administrators can edit knowledge.'}, status=status.HTTP_403_FORBIDDEN)
        practice, error = practice_or_404(request)
        if error:
            return error
        data, errors = _clean_knowledge(request.data)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        entry = KnowledgeEntry.objects.create(practice=practice, updated_by=request.user, **data)
        audit(practice, request, 'KNOWLEDGE_ADDED', {'id': entry.id, 'category': entry.category})
        return Response(_knowledge_row(entry), status=status.HTTP_201_CREATED)


class KnowledgeDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def _entry(self, request, id):
        from .models import KnowledgeEntry
        practice, error = practice_or_404(request)
        if error:
            return None, error
        return get_object_or_404(KnowledgeEntry, pk=id, practice=practice), None

    def patch(self, request, id):
        if not is_practice_admin_user(request.user):
            return Response({'error': 'Only practice administrators can edit knowledge.'}, status=status.HTTP_403_FORBIDDEN)
        entry, error = self._entry(request, id)
        if error:
            return error
        data, errors = _clean_knowledge(request.data, partial=True)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        for k, v in data.items():
            setattr(entry, k, v)
        entry.updated_by = request.user
        entry.save()
        return Response(_knowledge_row(entry))

    def delete(self, request, id):
        if not is_practice_admin_user(request.user):
            return Response({'error': 'Only practice administrators can edit knowledge.'}, status=status.HTTP_403_FORBIDDEN)
        entry, error = self._entry(request, id)
        if error:
            return error
        audit(entry.practice, request, 'KNOWLEDGE_DELETED', {'id': entry.id})
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnansweredQuestionListView(APIView):
    """Questions patients asked that Concierge had to pass to the front desk."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        from .models import UnansweredQuestion
        practice, error = practice_or_404(request)
        if error:
            return error
        rows = UnansweredQuestion.objects.filter(practice=practice, status='open')[:100]
        return Response({'results': [
            {'id': q.id, 'question': q.question, 'times_asked': q.times_asked, 'last_asked_at': q.last_asked_at}
            for q in rows
        ]})


class UnansweredQuestionActionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def post(self, request, id):
        from .models import KnowledgeEntry, UnansweredQuestion
        if not is_practice_admin_user(request.user):
            return Response({'error': 'Only practice administrators can answer questions.'}, status=status.HTTP_403_FORBIDDEN)
        practice, error = practice_or_404(request)
        if error:
            return error
        q = get_object_or_404(UnansweredQuestion, pk=id, practice=practice)
        action = request.data.get('action')
        if action == 'dismiss':
            q.status = 'dismissed'
            q.save(update_fields=['status'])
            return Response({'id': q.id, 'status': q.status})
        if action == 'answer':
            data, errors = _clean_knowledge({
                'category': request.data.get('category') or 'faq',
                'title': request.data.get('title') or q.question,
                'content': request.data.get('content'),
            })
            if errors:
                return Response(errors, status=status.HTTP_400_BAD_REQUEST)
            entry = KnowledgeEntry.objects.create(practice=practice, updated_by=request.user, **data)
            q.status, q.answer_entry = 'answered', entry
            q.save(update_fields=['status', 'answer_entry'])
            audit(practice, request, 'KNOWLEDGE_ADDED', {'id': entry.id, 'from_question': q.id})
            return Response({'id': q.id, 'status': q.status, 'entry': _knowledge_row(entry)})
        return Response({'error': 'Unknown action.'}, status=status.HTTP_400_BAD_REQUEST)

class PracticeInsightsView(APIView):
    """What needs attention, what is not set up yet, and the last 30 days - all from real records."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        from datetime import timedelta
        from statistics import median
        from apps.appointments.models import AppointmentOffer
        from apps.conversations.state_machine import office_open_at
        from apps.emails.models import Email
        from .models import KnowledgeEntry, UnansweredQuestion

        practice = resolve_user_practice(request)
        if not practice:
            return Response({})
        now = timezone.now()
        since = now - timedelta(days=30)
        appts = Appointment.objects.filter(practice=practice).exclude(status='spam')

        # Needs attention
        stale_qs = appts.filter(status='pending', response_sent_at__isnull=True,
                                created_at__lt=now - timedelta(hours=24)).order_by('created_at')
        stale = [{
            'id': str(a.id), 'name': (a.patient_name or 'Patient').split(' ')[0],
            'hours_waiting': int((now - a.created_at).total_seconds() // 3600),
        } for a in stale_qs[:5]]
        attention = {
            'waiting_over_24h': stale_qs.count(),
            'waiting_examples': stale,
            'asked_for_new_time': AppointmentOffer.objects.filter(
                practice=practice, status=AppointmentOffer.STATUS_RESCHEDULE, appointment__status='pending').count(),
            'failed_emails_7d': Email.objects.filter(thread__practice=practice, direction=Email.DIRECTION_OUTGOING,
                                                     status=Email.STATUS_FAILED, created_at__gte=now - timedelta(days=7)).count(),
            'unanswered_questions': UnansweredQuestion.objects.filter(practice=practice, status='open').count(),
        }

        # Setup checklist
        provider = practice.email_providers.filter(is_active=True).first()
        custom = bool(provider and provider.provider_type == 'smtp' and provider.smtp_host)
        if custom:
            email_ok = provider.last_test_status == 'SUCCESS'
            email_detail = 'Your mail server passed its last test.' if email_ok else (
                'Your mail server failed its last test.' if provider.last_test_status == 'FAILED'
                else 'Send a test email to confirm your mail server works.')
        else:
            email_ok = bool(getattr(settings, 'EMAIL_CONFIGURED', False))
            email_detail = 'Platform email is ready.' if email_ok else 'Email is not set up yet, so patient replies cannot be sent.'
        hours_set = office_open_at(practice) is not None
        knowledge_count = KnowledgeEntry.objects.filter(practice=practice, is_active=True).count()
        widget_chats = Conversation.objects.filter(practice=practice, started_at__gte=since).count()
        team_size = User.objects.filter(practice=practice, is_active=True).count()
        replies_on = bool(getattr(settings, 'IMAP_HOST', ''))
        setup = [
            {'key': 'email', 'label': 'Email can be sent', 'done': email_ok, 'detail': email_detail, 'link': '/dashboard/email-settings'},
            {'key': 'hours', 'label': 'Office hours are set', 'done': hours_set,
             'detail': 'Concierge knows when you are open.' if hours_set else 'Add your hours so patients get accurate answers.',
             'link': '/dashboard/business-rules'},
            {'key': 'knowledge', 'label': 'Patient answers added', 'done': knowledge_count >= 3,
             'detail': f'{knowledge_count} approved answer{"" if knowledge_count == 1 else "s"}.' + ('' if knowledge_count >= 3 else ' Add at least 3 common questions.'),
             'link': '/dashboard/knowledge'},
            {'key': 'widget', 'label': 'Chat is live on your website', 'done': widget_chats > 0,
             'detail': f'{widget_chats} conversation{"" if widget_chats == 1 else "s"} in the last 30 days.' if widget_chats else 'Add the chat script to your website.',
             'link': '/dashboard/installation'},
            {'key': 'team', 'label': 'Front desk invited', 'done': team_size >= 2,
             'detail': f'{team_size} team member{"" if team_size == 1 else "s"}.' if team_size >= 2 else 'Invite the person who answers patient requests.',
             'link': '/dashboard/team'},
            {'key': 'replies', 'label': 'Patient email replies are collected', 'done': replies_on,
             'detail': 'Replies appear on each request automatically.' if replies_on else 'Ask your HeyJarvis agency to turn on reply collection.',
             'link': None},
        ]

        # Last 30 days
        recent = list(appts.filter(created_at__gte=since).values('created_at', 'response_sent_at'))
        after_hours = None
        if hours_set:
            after_hours = sum(1 for a in recent if office_open_at(practice, a['created_at']) is False)
        waits = [(a['response_sent_at'] - a['created_at']).total_seconds() / 60 for a in recent if a['response_sent_at']]
        results = {
            'inquiries': widget_chats,
            'requests': len(recent),
            'after_hours_requests': after_hours,
            'replied': len(waits),
            'median_minutes_to_reply': round(median(waits)) if waits else None,
            'patient_confirmations': AppointmentOffer.objects.filter(
                practice=practice, status=AppointmentOffer.STATUS_CONFIRMED, responded_at__gte=since).count(),
        }
        return Response({'attention': attention, 'setup': setup, 'results_30d': results,
                         'setup_complete': all(item['done'] for item in setup)})

# ── Practice branding ─────────────────────────────────────────────────────────

def _branding_payload(practice, request):
    from .branding import doctors_payload, social_links
    ps = getattr(practice, 'settings', None)
    logo = practice.brand_assets.filter(kind='logo').order_by('-created_at').first()
    return {
        'practice_name': practice.name,
        'logo_url': practice.logo_url,
        'logo_uploaded': bool(logo and practice.logo_url and str(logo.id) in practice.logo_url),
        'tagline': getattr(ps, 'brand_tagline', '') if ps else '',
        'primary_color': getattr(ps, 'widget_primary_color', '#0d9488') if ps else '#0d9488',
        'social_links': social_links(practice),
        'doctors': doctors_payload(practice, request),
    }


class BrandingView(APIView):
    """Practice identity used across the widget, patient emails and patient pages."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        practice, error = practice_or_404(request)
        if error:
            return error
        return Response(_branding_payload(practice, request))

    def patch(self, request):
        from .branding import SOCIAL_KEYS, clean_link
        if not is_practice_admin_user(request.user):
            return Response({'error': 'Only practice administrators can change branding.'}, status=status.HTTP_403_FORBIDDEN)
        practice, error = practice_or_404(request)
        if error:
            return error
        ps, _ = PracticeSettings.objects.get_or_create(practice=practice)
        if 'tagline' in request.data:
            ps.brand_tagline = str(request.data.get('tagline') or '').strip()[:120]
        if 'social_links' in request.data:
            raw = request.data.get('social_links') or {}
            if not isinstance(raw, dict):
                return Response({'social_links': 'Invalid links.'}, status=status.HTTP_400_BAD_REQUEST)
            links, errors = {}, {}
            for key in SOCIAL_KEYS:
                try:
                    value = clean_link(str(raw.get(key) or ''))
                except ValueError as exc:
                    errors[key] = str(exc)
                    continue
                if value:
                    links[key] = value
            if errors:
                return Response({'social_links': errors}, status=status.HTTP_400_BAD_REQUEST)
            ps.social_links = links
        ps.save()
        audit(practice, request, 'BRANDING_UPDATED', {'fields': sorted(k for k in request.data.keys())})
        return Response(_branding_payload(practice, request))


class _AdminUploadMixin:
    from rest_framework.parsers import MultiPartParser as _MP, FormParser as _FP, JSONParser as _JP
    parser_classes = [_MP, _FP, _JP]
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def admin_practice(self, request):
        if not is_practice_admin_user(request.user):
            return None, Response({'error': 'Only practice administrators can change branding.'}, status=status.HTTP_403_FORBIDDEN)
        return practice_or_404(request)


class BrandLogoView(_AdminUploadMixin, APIView):
    def post(self, request):
        from .branding import ImageError, asset_url, process_logo, store_asset
        practice, error = self.admin_practice(request)
        if error:
            return error
        try:
            asset = store_asset(practice, 'logo', process_logo(request.FILES.get('file')))
        except ImageError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        practice.brand_assets.filter(kind='logo').exclude(pk=asset.pk).delete()
        practice.logo_url = asset_url(asset, request)
        practice.save(update_fields=['logo_url'])
        audit(practice, request, 'LOGO_UPDATED', {'width': asset.width, 'height': asset.height})
        return Response(_branding_payload(practice, request), status=status.HTTP_201_CREATED)

    def delete(self, request):
        practice, error = self.admin_practice(request)
        if error:
            return error
        practice.brand_assets.filter(kind='logo').delete()
        practice.logo_url = ''
        practice.save(update_fields=['logo_url'])
        audit(practice, request, 'LOGO_REMOVED', {})
        return Response(_branding_payload(practice, request))


def _doctor_fields(data, partial=False):
    out, errors = {}, {}
    if 'name' in data or not partial:
        name = str(data.get('name') or '').strip()[:120]
        if not name:
            errors['name'] = 'Add the name patients should see.'
        out['name'] = name
    if 'credentials' in data:
        out['credentials'] = str(data.get('credentials') or '').strip()[:120]
    if 'bio' in data:
        out['bio'] = str(data.get('bio') or '').strip()[:400]
    if 'is_active' in data:
        out['is_active'] = bool(data.get('is_active'))
    return out, errors


class BrandTeamListView(_AdminUploadMixin, APIView):
    def get(self, request):
        from .branding import doctors_payload
        practice, error = practice_or_404(request)
        if error:
            return error
        return Response({'results': doctors_payload(practice, request)})

    def post(self, request):
        from .models import PracticeDoctor
        practice, error = self.admin_practice(request)
        if error:
            return error
        if practice.doctors.count() >= 12:
            return Response({'error': 'You can introduce up to 12 team members.'}, status=status.HTTP_400_BAD_REQUEST)
        data, errors = _doctor_fields(request.data)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        doc = PracticeDoctor.objects.create(practice=practice, position=practice.doctors.count(), **data)
        return Response({'id': doc.id}, status=status.HTTP_201_CREATED)


class BrandTeamMemberView(_AdminUploadMixin, APIView):
    def _doc(self, request, id):
        from .models import PracticeDoctor
        practice, error = self.admin_practice(request)
        if error:
            return None, error
        return get_object_or_404(PracticeDoctor, pk=id, practice=practice), None

    def patch(self, request, id):
        doc, error = self._doc(request, id)
        if error:
            return error
        data, errors = _doctor_fields(request.data, partial=True)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        for k, v in data.items():
            setattr(doc, k, v)
        doc.save()
        return Response({'id': doc.id})

    def delete(self, request, id):
        doc, error = self._doc(request, id)
        if error:
            return error
        if doc.photo_id:
            doc.photo.delete()
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BrandTeamMemberPhotoView(_AdminUploadMixin, APIView):
    def post(self, request, id):
        from .branding import ImageError, asset_url, process_photo, store_asset
        from .models import PracticeDoctor
        practice, error = self.admin_practice(request)
        if error:
            return error
        doc = get_object_or_404(PracticeDoctor, pk=id, practice=practice)
        try:
            asset = store_asset(practice, 'photo', process_photo(request.FILES.get('file')))
        except ImageError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        old = doc.photo
        doc.photo = asset
        doc.save(update_fields=['photo'])
        if old:
            old.delete()
        return Response({'id': doc.id, 'photo_url': asset_url(asset, request)})

    def delete(self, request, id):
        from .models import PracticeDoctor
        practice, error = self.admin_practice(request)
        if error:
            return error
        doc = get_object_or_404(PracticeDoctor, pk=id, practice=practice)
        if doc.photo_id:
            old = doc.photo
            doc.photo = None
            doc.save(update_fields=['photo'])
            old.delete()
        return Response({'id': doc.id, 'photo_url': ''})


class BrandEmailPreviewView(APIView):
    """The branded email a patient receives for a normal staff reply (sample text, nothing is sent)."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def post(self, request):
        from apps.emails.branded import render_branded_message
        practice, error = practice_or_404(request)
        if error:
            return error
        body = str(request.data.get('body') or '').strip() or (
            "Hi Alex,\n\nThank you for reaching out to us. We'd be happy to help you schedule your visit.\n\n"
            "Please reply to this email with a couple of days and times that suit you, and our team will confirm "
            "an appointment with you.")
        return Response({'html': render_branded_message(practice, body[:4000])})


class PublicBrandAssetView(APIView):
    """Public, cacheable logo/team images (branding is public by nature; IDs are random)."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, asset_id, digest, ext):
        from django.http import Http404
        from .models import BrandAsset
        asset = BrandAsset.objects.select_related('practice').filter(pk=asset_id, digest=digest).first()
        if not asset or not asset.practice.active:
            raise Http404()
        resp = HttpResponse(bytes(asset.content), content_type=asset.content_type)
        resp['Cache-Control'] = 'public, max-age=31536000, immutable'
        resp['X-Content-Type-Options'] = 'nosniff'
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Cross-Origin-Resource-Policy'] = 'cross-origin'
        return resp