"""
Email thread and message models.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class EmailThread(models.Model):
    """An email conversation thread with a patient."""
    STATUS_ACTIVE = 'active'
    STATUS_CLOSED = 'closed'
    STATUS_PENDING = 'pending'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_CLOSED, 'Closed'),
        (STATUS_PENDING, 'Pending'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    practice = models.ForeignKey(
        'practices.Practice', on_delete=models.CASCADE, null=True, blank=True, related_name='email_threads'
    )
    patient_email = models.EmailField(db_index=True)
    patient_name = models.CharField(max_length=200, blank=True)
    subject = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='assigned_email_threads'
    )
    metadata = models.JSONField(default=dict, blank=True)
    last_message_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_message_at']
        indexes = [
            models.Index(fields=['patient_email', 'status']),
        ]

    def __str__(self):
        return f"{self.subject} - {self.patient_email}"


class Email(models.Model):
    """An individual email in a thread."""
    DIRECTION_INCOMING = 'incoming'
    DIRECTION_OUTGOING = 'outgoing'
    DIRECTION_INTERNAL = 'internal'

    DIRECTION_CHOICES = [
        (DIRECTION_INCOMING, 'Incoming'),
        (DIRECTION_OUTGOING, 'Outgoing'),
        (DIRECTION_INTERNAL, 'Internal'),
    ]

    STATUS_SENDING = 'sending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_DRAFT = 'draft'
    STATUS_RECEIVED = 'received'

    STATUS_CHOICES = [
        (STATUS_SENDING, 'Sending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_DRAFT, 'Draft'),
        (STATUS_RECEIVED, 'Received'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(
        EmailThread, on_delete=models.CASCADE, related_name='emails'
    )
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    from_email = models.EmailField()
    to_email = models.EmailField()
    cc = models.EmailField(blank=True)
    subject = models.CharField(max_length=500)
    body = models.TextField()
    body_html = models.TextField(blank=True)
    is_ai_draft = models.BooleanField(default=False)
    is_staff_reply = models.BooleanField(default=False)
    provider_message_id = models.CharField(max_length=200, blank=True)
    provider = models.CharField(max_length=50, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.direction}: {self.subject}"


class EmailCadence(models.Model):
    """Email cadence campaign for a patient."""
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    practice = models.ForeignKey(
        'practices.Practice', on_delete=models.CASCADE, null=True, blank=True, related_name='email_cadences'
    )
    patient_email = models.EmailField(db_index=True)
    patient_name = models.CharField(max_length=200, blank=True)
    template = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    current_step = models.IntegerField(default=0)
    total_steps = models.IntegerField(default=5)
    next_scheduled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'next_scheduled_at']),
        ]

    def __str__(self):
        return f"Cadence for {self.patient_email} ({self.template})"
