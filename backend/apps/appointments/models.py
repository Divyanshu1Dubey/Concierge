"""Appointment models for bookings, requests, and front-desk coordination."""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class Service(models.Model):
    """Dental services offered."""
    practice = models.ForeignKey(
        'practices.Practice', on_delete=models.CASCADE, null=True, blank=True, related_name='services'
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    duration_minutes = models.IntegerField(default=30)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AppointmentSlot(models.Model):
    """Available appointment time slots."""
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='slots')
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()
    max_bookings = models.IntegerField(default=1)
    current_bookings = models.IntegerField(default=0)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['start_time', 'is_available']),
        ]

    def __str__(self):
        return f"{self.service.name} - {self.start_time}"

    @property
    def available_spots(self):
        return self.max_bookings - self.current_bookings


class Appointment(models.Model):
    """Patient appointment request & booking record."""
    STATUS_PENDING = 'pending'
    STATUS_CONTACTED = 'contacted'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_COMPLETED = 'completed'
    STATUS_NO_SHOW = 'no_show'
    STATUS_SPAM = 'spam'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_CONTACTED, 'Contacted'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_NO_SHOW, 'No Show'),
        (STATUS_SPAM, 'Spam'),
    ]

    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('NORMAL', 'Normal'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    practice = models.ForeignKey(
        'practices.Practice', on_delete=models.CASCADE, null=True, blank=True, related_name='appointments'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='appointments'
    )
    patient_email = models.EmailField(db_index=True, blank=True)
    patient_name = models.CharField(max_length=200, blank=True)
    patient_phone = models.CharField(max_length=20, blank=True)
    
    service = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True, related_name='appointments'
    )
    service_name = models.CharField(max_length=200, blank=True)
    slot = models.ForeignKey(
        AppointmentSlot, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='appointments'
    )
    
    intent = models.CharField(max_length=50, default='appointment', blank=True)
    preferred_date = models.CharField(max_length=100, blank=True)
    preferred_time = models.CharField(max_length=100, blank=True)
    urgency = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='NORMAL')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='NORMAL')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    message = models.TextField(blank=True)
    ai_summary = models.TextField(blank=True)
    source_website = models.CharField(max_length=255, blank=True)
    
    notes = models.TextField(blank=True)
    internal_notes = models.JSONField(default=list, blank=True)
    
    response_draft = models.TextField(blank=True)
    response_sent_at = models.DateTimeField(null=True, blank=True)
    
    confirmation_code = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='assigned_appointments'
    )
    reminder_sent = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['practice', 'status']),
            models.Index(fields=['patient_email', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.patient_name or self.patient_email or 'Guest'} - {self.service_name or 'Appointment'}"

    def save(self, *args, **kwargs):
        if not self.confirmation_code:
            import secrets
            self.confirmation_code = f"APT-{secrets.token_hex(4).upper()}"
        super().save(*args, **kwargs)


class AppointmentOffer(models.Model):
    """
    A specific visit time the front desk asked the patient to confirm (sent as a branded email).
    The patient answers through a single-use link; only a hash of its token is stored.
    """
    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_RESCHEDULE = 'reschedule_requested'
    STATUS_SUPERSEDED = 'superseded'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Awaiting patient'),
        (STATUS_CONFIRMED, 'Confirmed by patient'),
        (STATUS_RESCHEDULE, 'Patient asked for another time'),
        (STATUS_SUPERSEDED, 'Replaced by a newer time'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='offers')
    practice = models.ForeignKey('practices.Practice', on_delete=models.CASCADE, related_name='appointment_offers')
    offered_date = models.DateField()
    offered_time = models.CharField(max_length=50)
    token_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING)
    patient_note = models.TextField(blank=True, max_length=1000)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='appointment_offers'
    )
    created_at = models.DateTimeField(default=timezone.now)
    responded_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Offer {self.offered_date} {self.offered_time} ({self.status})"