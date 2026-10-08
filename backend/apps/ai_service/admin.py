"""
Admin registrations for ai_service app.
"""
from django.contrib import admin
from apps.ai_service.models import AIInteractionLog


@admin.register(AIInteractionLog)
class AIInteractionLogAdmin(admin.ModelAdmin):
    list_display = ['provider', 'model', 'interaction_type', 'total_tokens', 'latency_ms', 'created_at']
    list_filter = ['provider', 'interaction_type']
    search_fields = ['model']
    readonly_fields = ['id', 'created_at']
