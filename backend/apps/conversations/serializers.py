"""Serializers for the conversations app with tenant awareness and state machine data."""
from rest_framework import serializers
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for Message model."""
    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'content', 'intent', 'confidence', 'created_at']
        read_only_fields = ['id', 'created_at']


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer for Conversation model with full messages and state machine fields."""
    messages = MessageSerializer(many=True, read_only=True)
    message_count = serializers.SerializerMethodField()
    practice_name = serializers.ReadOnlyField(source='practice.name')

    class Meta:
        model = Conversation
        fields = [
            'id', 'practice', 'practice_name', 'session_id', 'state',
            'patient_email', 'patient_name', 'patient_phone',
            'intent', 'intent_confidence', 'service_requested',
            'preferred_date', 'preferred_time', 'urgency', 'lead_status',
            'summary', 'source_url', 'metadata', 'internal_notes',
            'response_draft', 'response_sent_at',
            'assigned_to', 'status', 'started_at', 'ended_at',
            'last_activity_at', 'messages', 'message_count',
        ]
        read_only_fields = ['id', 'started_at', 'last_activity_at']

    def get_message_count(self, obj):
        return obj.messages.count()


class ConversationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new conversation."""
    class Meta:
        model = Conversation
        fields = ['patient_email', 'patient_name', 'patient_phone', 'intent', 'practice']

    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        if user and user.is_authenticated and user.practice and 'practice' not in validated_data:
            validated_data['practice'] = user.practice
        return Conversation.objects.create(**validated_data)


class ChatRequestSerializer(serializers.Serializer):
    """Serializer for incoming chat messages from widget or hosted concierge."""
    message = serializers.CharField(required=False, default="")
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    client_key = serializers.CharField(required=False, allow_blank=True)
    practice_slug = serializers.CharField(required=False, allow_blank=True)
    session_id = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    url = serializers.CharField(required=False, allow_blank=True)


class ChatResponseSerializer(serializers.Serializer):
    """Serializer for chat responses."""
    conversation_id = serializers.UUIDField()
    message = serializers.CharField()
    state = serializers.CharField(required=False)
    intent = serializers.CharField(required=False)
    confidence = serializers.FloatField(required=False)
    conversation_complete = serializers.BooleanField(default=False)
    quick_replies = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    requires_human = serializers.BooleanField(default=False)
