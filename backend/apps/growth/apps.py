from django.apps import AppConfig


class GrowthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.growth'
    label = 'growth'
    verbose_name = 'Growth & Conversion'

    def ready(self):
        from . import signals  # noqa: F401
