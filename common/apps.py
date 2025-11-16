from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'common'
    verbose_name = 'Common HMS Components'

    def ready(self):
        """
        Override default admin site with custom HMS admin site
        This ensures all @admin.register() decorators use our custom site
        """
        from django.contrib import admin
        from .admin_site import hms_admin_site

        # Replace the default admin site with our custom HMS admin site
        admin.site = hms_admin_site
        admin.sites.site = hms_admin_site
