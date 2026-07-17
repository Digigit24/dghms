from django.apps import AppConfig


class OpdConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.opd'

    def ready(self):
        # Register bill/item synchronization receivers.  Without this import,
        # OPDBillItem writes do not recalculate their parent OPDBill.
        import apps.opd.signals  # noqa: F401
