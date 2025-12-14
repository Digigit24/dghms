from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.patients'

    def ready(self):
        """Import signals when app is ready"""
        import apps.patients.signals  # noqa
