"""Shared serializer base classes for DigiHMS.

All tenant-aware serializers should inherit from :class:`TenantAwareSerializer`
or mix in :class:`common.mixins.TenantMixin`.
"""

from rest_framework import serializers

from .mixins import TenantMixin


class TenantAwareSerializer(TenantMixin, serializers.ModelSerializer):
    """Base ModelSerializer that automatically scopes records to the JWT tenant.

    ``tenant_id`` is read-only and injected from ``request.tenant_id`` during
    ``create``. Updates explicitly discard any supplied ``tenant_id``.
    """

    class Meta:
        abstract = True
