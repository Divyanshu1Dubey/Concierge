"""
Serializers for the emails app.
"""
from rest_framework import serializers
from .models import EmailThread, Email, EmailCadence


class EmailSerializer(serializers.ModelSerializer):
    """Serializer for Email model."""
    class Meta:
        model = Email
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'sent_at']


class EmailCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating emails."""
    class Meta:
        model = Email
        fields = ['thread', 'direction', 'to_email', 'subject', 'body', 'body_html', 'is_ai_draft']


class EmailThreadSerializer(serializers.ModelSerializer):
    """Serializer for EmailThread with latest email."""
    emails = serializers.SerializerMethodField()
    latest_email = serializers.SerializerMethodField()

    class Meta:
        model = EmailThread
        fields = [
            'id', 'patient_email', 'patient_name', 'subject', 'status',
            'assigned_to', 'metadata', 'last_message_at', 'created_at',
            'emails', 'latest_email',
        ]
        read_only_fields = ['id', 'created_at']

    def get_emails(self, obj):
        return EmailSerializer(obj.emails.all()[:10], many=True).data

    def get_latest_email(self, obj):
        latest = obj.emails.first()
        return EmailSerializer(latest).data if latest else None


class EmailCadenceSerializer(serializers.ModelSerializer):
    """Serializer for EmailCadence model."""
    class Meta:
        model = EmailCadence
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
