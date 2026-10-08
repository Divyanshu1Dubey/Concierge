"""
Serializers for the dashboard app.
"""
from rest_framework import serializers
from .models import PracticeSettings, WidgetInstall


class PracticeSettingsSerializer(serializers.ModelSerializer):
    """Serializer for PracticeSettings."""
    class Meta:
        model = PracticeSettings
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class WidgetInstallSerializer(serializers.ModelSerializer):
    """Serializer for WidgetInstall."""
    class Meta:
        model = WidgetInstall
        fields = ['id', 'widget_id', 'site_url', 'is_active', 'installed_at', 'last_seen_at']
        read_only_fields = ['id', 'widget_id', 'installed_at']
