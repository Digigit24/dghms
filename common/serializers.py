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

    def create(self, validated_data):
        """Inject tenant_id from request context on create."""
        request = self.context.get("request")
        if request and hasattr(request, "tenant_id"):
            validated_data["tenant_id"] = request.tenant_id
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Discard any supplied tenant_id on update."""
        validated_data.pop("tenant_id", None)
        return super().update(instance, validated_data)
