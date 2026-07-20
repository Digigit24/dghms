# ipd/apps.py
from django.apps import AppConfig


class IpdConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ipd'
    verbose_name = 'IPD Management'

    def ready(self):
        # Register bill/item synchronization receivers. Without this import,
        # IPDBillItem writes do not reliably recalculate their parent IPDBilling.
        import apps.ipd.signals  # noqa: F401
