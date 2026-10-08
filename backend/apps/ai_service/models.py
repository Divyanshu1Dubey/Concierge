"""
AI Service models.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class AIInteractionLog(models.Model):
    """Log of AI provider interactions for cost tracking."""
    INTERACTION_TYPE_CHOICES = [
        ('chat', 'Chat'),
        ('email_draft', 'Email Draft'),
        ('intent_classification', 'Intent Classification'),
        ('appointment_booking', 'Appointment Booking'),
        ('summary', 'Summary'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=50, db_index=True)
    model = models.CharField(max_length=100, db_index=True)
    interaction_type = models.CharField(max_length=30, choices=INTERACTION_TYPE_CHOICES)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ai_logs'
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['provider', 'created_at']),
            models.Index(fields=['interaction_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.provider}/{self.model} - {self.interaction_type}"
