"""Conversation and Message models for AI chat sessions and multi-tenant front-desk tracking."""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class Conversation(models.Model):
    """A chat conversation session with a patient."""
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_ABANDONED = 'abandoned'
    STATUS_HANDOFF = 'handoff'
    STATUS_CLOSED = 'closed'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_ABANDONED, 'Abandoned'),
        (STATUS_HANDOFF, 'Handoff to Staff'),
        (STATUS_CLOSED, 'Closed'),
    ]

    STATE_STARTED = 'STARTED'
    STATE_IDENTIFYING_INTENT = 'IDENTIFYING_INTENT'
    STATE_COLLECTING_INFORMATION = 'COLLECTING_INFORMATION'
    STATE_QUALIFYING = 'QUALIFYING'
    STATE_CONFIRMING = 'CONFIRMING'
    STATE_SUBMITTING = 'SUBMITTING'
    STATE_SUBMITTED = 'SUBMITTED'
    STATE_HANDOFF = 'HANDOFF'
    STATE_CLOSED = 'CLOSED'

    STATE_CHOICES = [
        (STATE_STARTED, 'Started'),
        (STATE_IDENTIFYING_INTENT, 'Identifying Intent'),
        (STATE_COLLECTING_INFORMATION, 'Collecting Information'),
        (STATE_QUALIFYING, 'Qualifying'),
        (STATE_CONFIRMING, 'Confirming'),
        (STATE_SUBMITTING, 'Submitting'),
        (STATE_SUBMITTED, 'Submitted'),
        (STATE_HANDOFF, 'Human Handoff'),
        (STATE_CLOSED, 'Closed'),
    ]

    LEAD_STATUS_CHOICES = [
        ('NEW', 'New'),
        ('CONTACTED', 'Contacted'),
        ('QUALIFIED', 'Qualified'),
        ('BOOKED', 'Booked'),
        ('CLOSED', 'Closed'),
        ('SPAM', 'Spam'),
    ]

    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('NORMAL', 'Normal'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    practice = models.ForeignKey(
        'practices.Practice', on_delete=models.CASCADE, null=True, blank=True, related_name='conversations'
    )
    session_id = models.CharField(max_length=100, db_index=True, blank=True)
    state = models.CharField(max_length=35, choices=STATE_CHOICES, default=STATE_STARTED)

    patient_email = models.EmailField(db_index=True, blank=True)
    patient_name = models.CharField(max_length=200, blank=True)
    patient_phone = models.CharField(max_length=20, blank=True)

    intent = models.CharField(max_length=50, blank=True, db_index=True)
    intent_confidence = models.FloatField(default=0.0)
    service_requested = models.CharField(max_length=100, blank=True)
    preferred_date = models.CharField(max_length=100, blank=True)
    preferred_time = models.CharField(max_length=100, blank=True)
    urgency = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='NORMAL')
    lead_status = models.CharField(max_length=20, choices=LEAD_STATUS_CHOICES, default='NEW')

    summary = models.TextField(blank=True)
    source_url = models.URLField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    internal_notes = models.JSONField(default=list, blank=True)

    response_draft = models.TextField(blank=True)
    response_sent_at = models.DateTimeField(null=True, blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='assigned_conversations'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-last_activity_at']
        indexes = [
            models.Index(fields=['practice', 'status']),
            models.Index(fields=['practice', 'lead_status']),
            models.Index(fields=['patient_email', 'status']),
            models.Index(fields=['status', 'last_activity_at']),
        ]

    def __str__(self):
        return f"Conversation {self.id} - {self.patient_name or self.patient_email or 'Guest'}"


class Message(models.Model):
    """A message in a conversation."""
    SENDER_USER = 'user'
    SENDER_AI = 'ai'
    SENDER_STAFF = 'staff'

    SENDER_CHOICES = [
        (SENDER_USER, 'User'),
        (SENDER_AI, 'AI'),
        (SENDER_STAFF, 'Staff'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages'
    )
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES)
    content = models.TextField()
    intent = models.CharField(max_length=50, blank=True)
    confidence = models.FloatField(default=0.0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    def __str__(self):
        return f"{self.sender}: {self.content[:50]}"
