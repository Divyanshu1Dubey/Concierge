"""
Admin registrations for emails app.
"""
from django.contrib import admin
from apps.emails.models import EmailThread, Email, EmailCadence


@admin.register(EmailThread)
class EmailThreadAdmin(admin.ModelAdmin):
    list_display = ['patient_email', 'subject', 'status', 'last_message_at']
    list_filter = ['status']
    search_fields = ['patient_email', 'subject']


@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ['subject', 'direction', 'status', 'is_ai_draft', 'sent_at']
    list_filter = ['direction', 'status', 'is_ai_draft']
    search_fields = ['subject', 'to_email', 'from_email']


@admin.register(EmailCadence)
class EmailCadenceAdmin(admin.ModelAdmin):
    list_display = ['patient_email', 'status', 'current_step', 'next_scheduled_at']
    list_filter = ['status']
    search_fields = ['patient_email']
