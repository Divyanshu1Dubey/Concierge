"""
Views for the dashboard app.
"""
from rest_framework import generics, permissions
from .models import PracticeSettings, WidgetInstall
from .serializers import PracticeSettingsSerializer, WidgetInstallSerializer


class PracticeSettingsView(generics.RetrieveUpdateAPIView):
    """Get or update practice settings."""
    serializer_class = PracticeSettingsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        settings_obj, _ = PracticeSettings.objects.get_or_create(
            pk=1,
            defaults={'practice_name': 'My Practice', 'practice_email': ''},
        )
        return settings_obj


class WidgetInstallView(generics.CreateAPIView):
    """Register a new widget installation."""
    serializer_class = WidgetInstallSerializer
    permission_classes = [permissions.AllowAny]
