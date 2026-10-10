"""
Views for the dashboard app.
"""
from rest_framework import generics, permissions
from apps.core.permissions import IsAgencyAdmin
from .models import PracticeSettings, WidgetInstall
from .serializers import PracticeSettingsSerializer, WidgetInstallSerializer


class PracticeSettingsView(generics.RetrieveUpdateAPIView):
    """Get or update practice settings."""
    serializer_class = PracticeSettingsSerializer
    # Legacy platform-wide singleton; tenant settings live at /api/practices/settings/.
    permission_classes = [permissions.IsAuthenticated, IsAgencyAdmin]

    def get_object(self):
        settings_obj, _ = PracticeSettings.objects.get_or_create(
            pk=1,
            defaults={'practice_name': 'My Practice', 'practice_email': ''},
        )
        return settings_obj


class WidgetInstallView(generics.CreateAPIView):
    """Register a new widget installation."""
    serializer_class = WidgetInstallSerializer
    permission_classes = [permissions.IsAuthenticated, IsAgencyAdmin]

    def perform_create(self, serializer):
        import secrets
        settings_obj, _ = PracticeSettings.objects.get_or_create(
            pk=1, defaults={'practice_name': 'My Practice', 'practice_email': ''},
        )
        serializer.save(practice=settings_obj, widget_id=secrets.token_hex(12))
