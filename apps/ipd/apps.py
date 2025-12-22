# ipd/apps.py
from django.apps import AppConfig


class IpdConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ipd'
    verbose_name = 'IPD Management'

    def ready(self):
        import apps.ipd.signals
