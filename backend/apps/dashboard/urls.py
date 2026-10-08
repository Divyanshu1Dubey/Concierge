"""
URL routing for the dashboard app.
"""
from django.urls import path
from .views import PracticeSettingsView, WidgetInstallView

urlpatterns = [
    path('settings/', PracticeSettingsView.as_view(), name='practice-settings'),
    path('widgets/', WidgetInstallView.as_view(), name='widget-install'),
]
