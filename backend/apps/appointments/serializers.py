"""Serializers for appointments, requests, and front-desk workflows."""
from rest_framework import serializers
from .models import Appointment, AppointmentSlot, Service


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ['id', 'name', 'description', 'duration_minutes', 'price', 'is_active']


class AppointmentSlotSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)

    class Meta:
        model = AppointmentSlot
        fields = [
            'id', 'service', 'service_name', 'start_time', 'end_time',
            'max_bookings', 'current_bookings', 'is_available',
        ]


class AppointmentSerializer(serializers.ModelSerializer):
    service_title = serializers.SerializerMethodField()
    conversation_summary = serializers.CharField(source='conversation.summary', read_only=True)
    transcript = serializers.SerializerMethodField()
    practice_name = serializers.ReadOnlyField(source='practice.name')
    practice_phone = serializers.ReadOnlyField(source='practice.phone')
    assigned_name = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            'id', 'practice', 'practice_name', 'practice_phone',
            'conversation', 'conversation_summary', 'transcript',
            'patient_email', 'patient_name', 'patient_phone',
            'service', 'service_name', 'service_title',
            'intent', 'preferred_date', 'preferred_time',
            'urgency', 'priority', 'status', 'message', 'ai_summary',
            'source_website', 'notes', 'internal_notes',
            'response_draft', 'response_sent_at',
            'confirmation_code', 'confirmed_at', 'cancelled_at',
            'assigned_to', 'assigned_name',
            'created_at', 'updated_at',
        ]
        # Tenant ownership and lifecycle timestamps are server-controlled.
        read_only_fields = [
            'id', 'practice', 'conversation', 'confirmation_code', 'confirmed_at', 'cancelled_at',
            'response_sent_at', 'created_at', 'updated_at',
        ]

    def _practice_id(self):
        if self.instance is not None:
            return self.instance.practice_id
        practice = self.context.get('practice')
        return practice.id if practice else None

    def validate_service(self, service):
        if service and service.practice_id != self._practice_id():
            raise serializers.ValidationError('Service does not belong to this practice.')
        return service

    def validate_assigned_to(self, user):
        if user and user.practice_id != self._practice_id():
            raise serializers.ValidationError('Assignee must belong to the same practice.')
        return user

    def get_service_title(self, obj):
        if obj.service_name:
            return obj.service_name
        if obj.service:
            return obj.service.name
        return (obj.intent or 'General Appointment').replace('_', ' ').title()

    def get_assigned_name(self, obj):
        if obj.assigned_to:
            return obj.assigned_to.full_name or obj.assigned_to.email
        return None

    def get_transcript(self, obj):
        if obj.conversation:
            return list(obj.conversation.messages.order_by('created_at').values('sender', 'content', 'created_at'))
        return []


class AIDraftRequestSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=['draft', 'professional', 'shorter', 'warmer', 'translate', 'summarize', 'explain', 'next_action'],
        default='draft'
    )
    current_text = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    target_language = serializers.CharField(required=False, default='Spanish', max_length=50)


class SendReplySerializer(serializers.Serializer):
    to_email = serializers.EmailField()
    subject = serializers.CharField(max_length=500)
    body = serializers.CharField(max_length=20000)
    reply_to = serializers.EmailField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
