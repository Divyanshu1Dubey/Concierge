"""Tenant administration views for HeyJarvis Concierge Cloud."""
import io
import zipfile
import csv
import logging
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.utils import timezone

from .models import Practice, Domain, BookingRules, PracticeSettings, EmailProvider, EmailTemplate, AuditLog
from .serializers import (
    PracticeSerializer, DomainSerializer, BookingRulesSerializer,
    PracticeSettingsSerializer, EmailProviderSerializer, EmailTemplateSerializer,
    AuditLogSerializer, TeamMemberSerializer
)
from apps.core.permissions import IsTenantViewer, IsTenantMember, IsTenantAdmin, IsTenantOwner, IsAgencyAdmin, IsPracticeAdmin
from apps.users.models import User
from apps.conversations.models import Conversation
from apps.appointments.models import Appointment

logger = logging.getLogger(__name__)


def resolve_user_practice(request):
    """Resolve practice with agency override support."""
    user = request.user
    if not (user and user.is_authenticated):
        return None
    if user.is_superuser or user.role == 'AGENCY_ADMIN':
        p_id = request.headers.get('X-Practice-ID') or request.query_params.get('practice_id')
        if p_id:
            p = Practice.objects.filter(id=p_id).first()
            if p:
                return p
        if user.practice:
            return user.practice
        return Practice.objects.first()
    return user.practice


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
        if not (request.user.is_superuser or request.user.role in ('AGENCY_ADMIN', 'PRACTICE_ADMIN', 'ADMIN', 'OWNER')):
            return Response({'error': 'Practice administrator permissions required'}, status=status.HTTP_403_FORBIDDEN)

        serializer = PracticeSerializer(practice, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        AuditLog.objects.create(
            practice=practice,
            actor=request.user,
            action='BUSINESS_SETTINGS_UPDATED',
            details=request.data,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return Response(serializer.data)


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
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        if not name or not email:
            return Response({'error': 'Practice name and email are required.'}, status=status.HTTP_400_BAD_REQUEST)

        import re
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower()).strip('-')
        base_slug = slug or 'practice'
        c = 1
        while Practice.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{c}"
            c += 1

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
            active=data.get('active', True),
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

        admin_email = data.get('admin_email', '').strip()
        admin_name = data.get('admin_name', '').strip()
        admin_password = data.get('admin_password', 'Password123!')
        if admin_email:
            first_name = admin_name.split()[0] if admin_name else 'Admin'
            last_name = ' '.join(admin_name.split()[1:]) if ' ' in admin_name else 'Dentist'
            admin_user, created = User.objects.get_or_create(
                email=admin_email,
                defaults={
                    'username': admin_email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'role': 'PRACTICE_ADMIN',
                    'practice': practice,
                    'is_active': True,
                }
            )
            if created:
                admin_user.set_password(admin_password)
                admin_user.save()
            else:
                admin_user.practice = practice
                admin_user.role = 'PRACTICE_ADMIN'
                admin_user.save(update_fields=['practice', 'role'])

        AuditLog.objects.create(
            practice=practice,
            actor=request.user,
            action='PRACTICE_ONBOARDED',
            details={'created_by': request.user.email, 'practice': name},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        serializer = PracticeSerializer(practice)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


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
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        role = data.get('role', 'FRONT_DESK').upper()
        phone = data.get('phone', '').strip()

        if not email:
            return Response({'error': 'Email (login ID) is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not password:
            return Response({'error': 'Password is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if role not in ('PRACTICE_ADMIN', 'FRONT_DESK', 'OWNER', 'ADMIN'):
            role = 'FRONT_DESK'

        if User.objects.filter(email=email).exists():
            return Response({'error': f"User with email '{email}' already exists."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            email=email,
            username=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=role,
            practice=practice,
            is_active=True
        )

        AuditLog.objects.create(
            practice=practice,
            actor=request.user,
            action='USER_CREATED_BY_AGENCY',
            details={'email': email, 'role': role, 'created_by': request.user.email},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return Response({
            'id': str(user.id),
            'email': user.email,
            'full_name': user.full_name,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.role,
            'normalized_role': user.normalized_role,
            'is_active': user.is_active,
            'practice_id': practice.id,
            'message': f"Doctor / Staff account for {email} created successfully."
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
        return practice, target_user

    def post(self, request, practice_id, user_id):
        action = request.data.get('action') or request.query_params.get('action')
        practice, target_user = self._get_target(request, practice_id, user_id)
        if not target_user:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        if action == 'reset_password':
            new_password = request.data.get('password', '').strip()
            if not new_password:
                return Response({'error': 'New password is required.'}, status=status.HTTP_400_BAD_REQUEST)
            target_user.set_password(new_password)
            target_user.save()
            AuditLog.objects.create(
                practice=practice,
                actor=request.user,
                action='USER_PASSWORD_RESET',
                details={'target_email': target_user.email, 'reset_by': request.user.email},
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return Response({'success': True, 'message': f"Password for {target_user.email} updated successfully."})

        elif action == 'toggle_status':
            target_user.is_active = not target_user.is_active
            target_user.save(update_fields=['is_active'])
            AuditLog.objects.create(
                practice=practice,
                actor=request.user,
                action='USER_STATUS_TOGGLED',
                details={'target_email': target_user.email, 'is_active': target_user.is_active},
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return Response({'id': str(target_user.id), 'is_active': target_user.is_active, 'email': target_user.email})

        return Response({'error': 'Invalid action. Supported actions: reset_password, toggle_status'}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, practice_id, user_id):
        practice, target_user = self._get_target(request, practice_id, user_id)
        if not target_user:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        if target_user == request.user:
            return Response({'error': 'Cannot delete your own account.'}, status=status.HTTP_400_BAD_REQUEST)

        target_user.is_active = False
        target_user.save(update_fields=['is_active'])
        AuditLog.objects.create(
            practice=practice,
            actor=request.user,
            action='USER_DEACTIVATED',
            details={'target_email': target_user.email},
            ip_address=request.META.get('REMOTE_ADDR')
        )
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

        backend_url = getattr(settings, 'APP_PUBLIC_URL', None) or request.build_absolute_uri('/').rstrip('/')
        frontend_url = getattr(settings, 'FRONTEND_URL', None) or os.environ.get('FRONTEND_URL') or backend_url

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
        practice = request.user.practice
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
        domains = request.user.practice.domains.all()
        serializer = DomainSerializer(domains, many=True)
        return Response(serializer.data)

    def post(self, request):
        practice = request.user.practice
        hostname = request.data.get('hostname', '').strip().lower()
        if not hostname:
            return Response({'error': 'Hostname is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Clean protocol if present
        if '://' in hostname:
            from urllib.parse import urlparse
            hostname = urlparse(hostname).hostname or hostname

        domain, created = Domain.objects.get_or_create(
            practice=practice,
            hostname=hostname,
            defaults={'status': 'CONNECTED'}
        )

        AuditLog.objects.create(
            practice=practice,
            actor=request.user,
            action='DOMAIN_ADDED',
            details={'hostname': hostname},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        serializer = DomainSerializer(domain)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DomainDeleteView(APIView):
    """Remove an allowed domain."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def delete(self, request, id):
        practice = request.user.practice
        domain = get_object_or_404(Domain, id=id, practice=practice)
        hostname = domain.hostname
        domain.delete()

        AuditLog.objects.create(
            practice=practice,
            actor=request.user,
            action='DOMAIN_REMOVED',
            details={'hostname': hostname},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return Response({'status': 'deleted', 'hostname': hostname})


class BookingRulesView(APIView):
    """Retrieve or update booking rules and business hours."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        rules, _ = BookingRules.objects.get_or_create(practice=request.user.practice)
        return Response(BookingRulesSerializer(rules).data)

    def put(self, request):
        if request.user.role.upper() not in ('ADMIN', 'OWNER'):
            return Response({'error': 'Admin permissions required'}, status=status.HTTP_403_FORBIDDEN)
        rules, _ = BookingRules.objects.get_or_create(practice=request.user.practice)
        serializer = BookingRulesSerializer(rules, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        AuditLog.objects.create(
            practice=request.user.practice,
            actor=request.user,
            action='BOOKING_RULES_UPDATED',
            details=request.data,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return Response(serializer.data)


class TenantSettingsView(APIView):
    """Retrieve or update practice settings (AI, notification toggles, widget appearance)."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        st, _ = PracticeSettings.objects.get_or_create(practice=request.user.practice)
        return Response(PracticeSettingsSerializer(st).data)

    def put(self, request):
        if request.user.role.upper() not in ('ADMIN', 'OWNER'):
            return Response({'error': 'Admin permissions required'}, status=status.HTTP_403_FORBIDDEN)
        st, _ = PracticeSettings.objects.get_or_create(practice=request.user.practice)
        serializer = PracticeSettingsSerializer(st, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        AuditLog.objects.create(
            practice=request.user.practice,
            actor=request.user,
            action='SETTINGS_UPDATED',
            details=request.data,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return Response(serializer.data)


class EmailConfigView(APIView):
    """Retrieve or configure email provider (Managed vs Custom SMTP)."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        provider = request.user.practice.email_providers.first()
        if not provider:
            provider = EmailProvider.objects.create(
                practice=request.user.practice,
                provider_type='managed',
                is_active=True,
                is_default=True,
                from_name=request.user.practice.name,
                from_email=request.user.practice.email,
            )
        return Response(EmailProviderSerializer(provider).data)

    def put(self, request):
        practice = request.user.practice
        provider = practice.email_providers.first()
        if not provider:
            provider = EmailProvider(practice=practice)

        data = request.data.copy()
        raw_pwd = data.pop('smtp_password', None)
        if isinstance(raw_pwd, list):
            raw_pwd = raw_pwd[0]

        serializer = EmailProviderSerializer(provider, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        if raw_pwd:
            provider.set_smtp_password(raw_pwd)
            provider.save(update_fields=['smtp_password'])

        AuditLog.objects.create(
            practice=practice,
            actor=request.user,
            action='EMAIL_CONFIG_UPDATED',
            details={'provider_type': provider.provider_type, 'from_email': provider.from_email},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return Response(EmailProviderSerializer(provider).data)


class TestEmailConnectionView(APIView):
    """Test SMTP or Managed email delivery."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def post(self, request):
        practice = request.user.practice
        provider = practice.email_providers.first()
        if not provider:
            return Response({'success': False, 'message': 'No email provider configured'})

        test_result = provider.test_connection()
        return Response(test_result)


class EmailTemplateListView(generics.ListCreateAPIView):
    """List or create tenant email templates."""
    serializer_class = EmailTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get_queryset(self):
        return EmailTemplate.objects.filter(practice=self.request.user.practice)

    def perform_create(self, serializer):
        serializer.save(practice=self.request.user.practice)


class EmailTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, or delete a tenant email template."""
    serializer_class = EmailTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]
    lookup_field = 'id'

    def get_queryset(self):
        return EmailTemplate.objects.filter(practice=self.request.user.practice)


class TeamListView(APIView):
    """List or invite team members for the practice."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get(self, request):
        members = User.objects.filter(practice=request.user.practice)
        return Response(TeamMemberSerializer(members, many=True).data)

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        role = request.data.get('role', 'MEMBER').upper()
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')

        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({'error': 'User with this email already exists'}, status=status.HTTP_400_BAD_REQUEST)

        import secrets
        temp_pwd = secrets.token_urlsafe(12)
        new_user = User.objects.create_user(
            email=email,
            username=email,
            password=temp_pwd,
            first_name=first_name,
            last_name=last_name,
            role=role,
            practice=request.user.practice,
            is_active=True
        )

        AuditLog.objects.create(
            practice=request.user.practice,
            actor=request.user,
            action='TEAM_MEMBER_INVITED',
            details={'email': email, 'role': role},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return Response(TeamMemberSerializer(new_user).data, status=status.HTTP_201_CREATED)


class TeamMemberDetailView(APIView):
    """Update role or remove team member."""
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def put(self, request, id):
        member = get_object_or_404(User, id=id, practice=request.user.practice)
        new_role = request.data.get('role')
        if new_role and new_role.upper() in ('OWNER', 'ADMIN', 'MEMBER', 'FRONT_DESK', 'VIEWER'):
            member.role = new_role.upper()
            member.save(update_fields=['role'])
            return Response(TeamMemberSerializer(member).data)
        return Response({'error': 'Invalid role'}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id):
        member = get_object_or_404(User, id=id, practice=request.user.practice)
        if member == request.user:
            return Response({'error': 'Cannot remove yourself'}, status=status.HTTP_400_BAD_REQUEST)
        member.is_active = False
        member.save(update_fields=['is_active'])
        return Response({'status': 'disabled', 'id': str(member.id)})


class AuditLogListView(generics.ListAPIView):
    """Retrieve audit log for current tenant."""
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantAdmin]

    def get_queryset(self):
        return AuditLog.objects.filter(practice=self.request.user.practice).order_by('-created_at')[:100]


class TenantMetricsView(APIView):
    """Real metrics for dashboard overview."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        practice = request.user.practice
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

        return Response({
            'conversations': total_conv,
            'new_leads': total_leads,
            'completed_requests': completed,
            'emergency_requests': emergency,
            'appointment_requests': appointment_reqs,
            'human_handoffs': handoffs,
            'completion_rate': f"{conv_rate}%",
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
        elif request.user.practice:
            practice = request.user.practice
        elif request.user.is_agency_admin or request.user.is_superuser:
            practice = Practice.objects.first()
        else:
            return Response({'error': 'No practice associated with your account.'}, status=status.HTTP_400_BAD_REQUEST)

        if not practice:
            return Response({'error': 'No practice found.'}, status=status.HTTP_404_NOT_FOUND)

        client_key = practice.api_key
        slug = practice.slug
        practice_name = practice.name

        base_url = request.build_absolute_uri('/').rstrip('/')

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
    wp_script_add_data('heyjarvis-concierge-widget', 'data-heyjarvis-client', $client_key);
}});

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
        practice = request.user.practice
        if not practice and (request.user.is_agency_admin or request.user.is_superuser):
            practice_id = request.headers.get('X-Practice-ID') or request.query_params.get('practice_id')
            if practice_id:
                practice = Practice.objects.filter(id=practice_id).first()
            else:
                practice = Practice.objects.first()

        if not practice:
            return Response({'error': 'No practice selected or found for export.'}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(content_type='text/csv')

        if export_type == 'leads':
            response['Content-Disposition'] = f'attachment; filename="leads-{practice.slug}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Patient Name', 'Email', 'Phone', 'Service', 'Intent', 'Preferred Date', 'Preferred Time', 'Status', 'Urgency', 'Created At'])
            for a in Appointment.objects.filter(practice=practice):
                writer.writerow([a.patient_name, a.patient_email, a.patient_phone, a.service_name, a.intent, a.preferred_date, a.preferred_time, a.status, a.urgency, a.created_at.strftime('%Y-%m-%d %H:%M')])
            return response

        elif export_type == 'conversations':
            response['Content-Disposition'] = f'attachment; filename="conversations-{practice.slug}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Conversation ID', 'Patient Name', 'Email', 'Phone', 'Intent', 'State', 'Status', 'Started At', 'Summary'])
            for c in Conversation.objects.filter(practice=practice):
                writer.writerow([str(c.id), c.patient_name, c.patient_email, c.patient_phone, c.intent, c.state, c.status, c.started_at.strftime('%Y-%m-%d %H:%M'), c.summary])
            return response

        return Response({'error': 'Invalid export type. Use "leads" or "conversations"'}, status=status.HTTP_400_BAD_REQUEST)
