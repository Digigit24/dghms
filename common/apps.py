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

        self._patch_drf_ip_address_field()

    @staticmethod
    def _patch_drf_ip_address_field():
        """
        DRF 3.14 calls  validators, msg = ip_address_validators(...)  but
        Django 5.x changed ip_address_validators to return a plain list.
        Patch DRF's own module-level reference so schema generation and
        ModelSerializer auto-fields work correctly.
        """
        try:
            import rest_framework.fields as drf_fields
            from django.core.validators import (
                validate_ipv4_address,
                validate_ipv46_address,
                validate_ipv6_address,
            )
            from django.utils.translation import gettext_lazy as _

            _compat_map = {
                'both': ([validate_ipv46_address], _('Enter a valid IPv4 or IPv6 address.')),
                'ipv4': ([validate_ipv4_address],  _('Enter a valid IPv4 address.')),
                'ipv6': ([validate_ipv6_address],  _('Enter a valid IPv6 address.')),
            }

            def _ip_address_validators_compat(protocol, unpack_ipv4):
                if protocol != 'both' and unpack_ipv4:
                    raise ValueError(
                        "You can only use `unpack_ipv4` if `protocol` is set to 'both'"
                    )
                try:
                    return _compat_map[protocol.lower()]
                except KeyError:
                    raise ValueError(
                        "The protocol '%s' is unknown. Supported: %s"
                        % (protocol, list(_compat_map))
                    )

            drf_fields.ip_address_validators = _ip_address_validators_compat
        except Exception:
            pass  # If anything goes wrong, don't break startup
