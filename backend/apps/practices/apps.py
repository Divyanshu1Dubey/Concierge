"""Practices app configuration."""
from django.apps import AppConfig


class PracticesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.practices'
    verbose_name = 'Practices'

    def ready(self):
        """Import signals when app is ready."""
        import apps.practices.signals  # noqa: F401
