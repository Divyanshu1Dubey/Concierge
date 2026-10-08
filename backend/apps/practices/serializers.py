"""Serializers for Practice, Tenant Settings, Domains, Email Providers, and Team Members."""
from rest_framework import serializers
from .models import Practice, Domain, BookingRules, PracticeSettings, EmailProvider, EmailTemplate, AuditLog
from apps.users.models import User


class DomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = ['id', 'hostname', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class BookingRulesSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingRules
        fields = [
            'id', 'new_patient_duration', 'doctor_duration', 'hygiene_duration', 'emergency_duration',
            'confirmation_hours', 'no_show_fee', 'financing_options', 'business_hours',
            'emergency_message', 'after_hours_message', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PracticeSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PracticeSettings
        fields = [
            'id', 'ai_enabled', 'ai_greeting_message', 'ai_collects_phone',
            'notification_mode', 'default_from_name', 'default_from_email', 'email_signature',
            'notify_on_new_request', 'notify_on_emergency', 'notify_on_appointment',
            'notify_on_question', 'notify_on_reschedule', 'notify_on_cancel', 'notify_on_handoff',
            'notification_emails', 'follow_up_enabled', 'follow_up_intervals',
            'widget_title', 'widget_subtitle', 'widget_primary_color', 'widget_position',
            'widget_auto_open', 'widget_auto_open_delay_sec',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class EmailProviderSerializer(serializers.ModelSerializer):
    # Never return the password to the browser
    smtp_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = EmailProvider
        fields = [
            'id', 'provider_type', 'is_active', 'is_default',
            'from_name', 'from_email', 'reply_to',
            'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 'has_password',
            'smtp_use_tls', 'smtp_use_ssl',
            'last_tested_at', 'last_test_status', 'last_test_error',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'has_password', 'last_tested_at', 'last_test_status', 'last_test_error', 'created_at', 'updated_at']

    def get_has_password(self, obj):
        return bool(obj.smtp_password)


class EmailTemplateSerializer(serializers.ModelSerializer):
    template_type_display = serializers.CharField(source='get_template_type_display', read_only=True)

    class Meta:
        model = EmailTemplate
        fields = ['id', 'template_type', 'template_type_display', 'subject', 'body', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'template_type_display', 'created_at', 'updated_at']


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.ReadOnlyField(source='actor.email')
    actor_name = serializers.ReadOnlyField(source='actor.full_name')

    class Meta:
        model = AuditLog
        fields = ['id', 'actor_email', 'actor_name', 'action', 'details', 'ip_address', 'created_at']
        read_only_fields = ['id', 'actor_email', 'actor_name', 'action', 'details', 'ip_address', 'created_at']


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'role', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class PracticeSerializer(serializers.ModelSerializer):
    domains = DomainSerializer(many=True, read_only=True)
    booking_rules = BookingRulesSerializer(read_only=True)
    settings = PracticeSettingsSerializer(read_only=True)
    email_providers = EmailProviderSerializer(many=True, read_only=True)

    class Meta:
        model = Practice
        fields = [
            'id', 'name', 'slug', 'email', 'phone', 'address', 'city', 'state', 'zip_code',
            'timezone', 'website', 'logo_url', 'active', 'api_key', 'subscription_status',
            'domains', 'booking_rules', 'settings', 'email_providers',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'api_key', 'created_at', 'updated_at']
