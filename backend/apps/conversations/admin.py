"""
Admin registrations for conversations app.
"""
from django.contrib import admin
from apps.conversations.models import Conversation, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'patient_email', 'status', 'intent', 'last_activity_at']
    list_filter = ['status', 'intent']
    search_fields = ['patient_email', 'patient_name']
    readonly_fields = ['id', 'started_at', 'last_activity_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'sender', 'intent', 'created_at']
    list_filter = ['sender', 'intent']
    search_fields = ['content']
