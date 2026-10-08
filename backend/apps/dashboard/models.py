"""
Dashboard models.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone as django_timezone


class PracticeSettings(models.Model):
    """Practice-wide settings."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    practice_name = models.CharField(max_length=200)
    practice_email = models.EmailField()
    practice_phone = models.CharField(max_length=20, blank=True)
    practice_address = models.TextField(blank=True)
    practice_website = models.URLField(blank=True)
    practice_timezone = models.CharField(max_length=50, default='America/New_York', verbose_name='Timezone')

    # Widget settings
    widget_enabled = models.BooleanField(default=True)
    widget_color = models.CharField(max_length=7, default='#2563EB')
    widget_title = models.CharField(max_length=100, default='HeyJarvis')
    widget_greeting = models.CharField(max_length=200, default='Hello! How can I help you today?')

    # AI settings
    ai_provider = models.CharField(max_length=50, default='openai')
    ai_temperature = models.FloatField(default=0.7)
    ai_max_tokens = models.IntegerField(default=500)

    # Notification settings
    notification_email = models.EmailField(blank=True)
    notification_webhook = models.URLField(blank=True)
    notify_on_new_conversation = models.BooleanField(default=True)
    notify_on_appointment = models.BooleanField(default=True)
    notify_on_escalation = models.BooleanField(default=True)

    # Email settings
    auto_reply_enabled = models.BooleanField(default=True)
    auto_reply_delay_minutes = models.IntegerField(default=15)

    created_at = models.DateTimeField(default=django_timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Practice Settings'
        verbose_name_plural = 'Practice Settings'

    def __str__(self):
        return self.practice_name


class WidgetInstall(models.Model):
    """Widget installation record for a practice."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    widget_id = models.CharField(max_length=100, unique=True, db_index=True)
    site_url = models.URLField()
    is_active = models.BooleanField(default=True)
    practice = models.ForeignKey(
        PracticeSettings, on_delete=models.CASCADE, related_name='widgets'
    )
    metadata = models.JSONField(default=dict, blank=True)
    installed_at = models.DateTimeField(default=django_timezone.now)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-installed_at']

    def __str__(self):
        return f"{self.widget_id} - {self.site_url}"
