# diagnostics/apps.py
from django.apps import AppConfig


class DiagnosticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.diagnostics'
    verbose_name = 'Diagnostics Management'

    def ready(self):
        # Import signal handlers
        import apps.diagnostics.signals
