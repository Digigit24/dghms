"""App configuration for the printing app."""

from django.apps import AppConfig


class PrintingConfig(AppConfig):
    """Server-side print rendering (WeasyPrint) for clinical/IPD forms."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.printing"
    label = "printing"
    verbose_name = "Print Rendering"
