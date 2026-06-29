"""Shared model, serializer, and ViewSet mixins for DigiHMS."""

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import structlog

from .pagination import StandardPagination

logger = structlog.get_logger(__name__)


# ===== MODEL MIXINS =====


class TenantModelMixin(models.Model):
    """Abstract model mixin for multi-tenancy support."""

    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant identifier for multi-tenancy",
    )

    class Meta:
        abstract = True


class EncounterMixin(models.Model):
    """GenericForeignKey mixin for linking to OPD/IPD encounters.

    Note: the new clinical system uses ``encounter_type`` + ``encounter_id``
    (see D-08). This mixin is kept for legacy code that needs GFK support.
    """

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of encounter (OPD Visit or IPD Admission)",
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the encounter record",
    )
    encounter = GenericForeignKey("content_type", "object_id")

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]


class AuditMixin(models.Model):
    """Standard audit fields for tenant-scoped models.

    Use this in addition to ``TenantModelMixin`` for models that need
    created_by / updated_by tracking.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SuperAdmin User ID who created this record",
    )
    updated_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SuperAdmin User ID who last updated this record",
    )

    class Meta:
        abstract = True


# ===== SERIALIZER MIXINS =====


class TenantMixin(serializers.ModelSerializer):
    """Mixin to automatically handle tenant_id from request context."""

    def create(self, validated_data):
        request = self.context.get("request")
        if request and hasattr(request, "tenant_id"):
            validated_data["tenant_id"] = request.tenant_id
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("tenant_id", None)
        return super().update(instance, validated_data)

    class Meta:
        abstract = True


# ===== VIEWSET MIXINS =====


class TenantViewSetMixin:
    """Mixin for ViewSets to automatically filter by tenant_id.

    Requires ``request.tenant_id`` to be set by the JWT middleware. Raises
    ``PermissionDenied`` if it is missing.
    """

    pagination_class = StandardPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            raise PermissionDenied("Tenant context is required.")
        return queryset.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            raise PermissionDenied("Tenant context is required.")
        serializer.save(tenant_id=tenant_id)


class PatientAccessMixin:
    """Restrict patient users to their own records."""

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self.request, "is_patient", False):
            if hasattr(queryset.model, "user_id"):
                queryset = queryset.filter(user_id=self.request.user_id)
            elif hasattr(queryset.model, "patient"):
                queryset = queryset.filter(patient__user_id=self.request.user_id)
        return queryset


class WebhookDispatchMixin:
    """Mixin that queues webhook dispatch after a successful create/update."""

    webhook_event_name = None

    def _get_webhook_payload(self, instance, action):
        """Override in view to shape the webhook payload."""
        return {
            "event": f"{self.webhook_event_name}.{action}",
            "tenant_id": str(instance.tenant_id),
            "model": instance._meta.label_lower,
            "instance_id": str(instance.pk),
        }

    def _dispatch_webhook(self, instance, action):
        if not self.webhook_event_name:
            return
        try:
            from apps.webhooks.tasks import dispatch_webhook_event

            dispatch_webhook_event.delay(
                tenant_id=str(instance.tenant_id),
                event_name=f"{self.webhook_event_name}.{action}",
                payload=self._get_webhook_payload(instance, action),
            )
        except Exception as exc:
            logger.warning(
                "webhook_dispatch_failed",
                event=f"{self.webhook_event_name}.{action}",
                instance_id=instance.pk,
                error=str(exc),
            )

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._dispatch_webhook(serializer.instance, "created")

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._dispatch_webhook(serializer.instance, "updated")


class CachedFormStructureMixin:
    """Mixin for clinical form ViewSets that busts the form structure cache.

    Any write to a form, section, or field invalidates cache keys matching
    ``clinical:form:<form_id>:*``.
    """

    def _bust_form_cache(self, form_id):
        try:
            from common.cache import CeliyoCache

            cache = CeliyoCache()
            cache.delete_pattern(f"clinical:form:{form_id}:*")
        except Exception as exc:
            logger.warning(
                "form_cache_bust_failed",
                form_id=form_id,
                error=str(exc),
            )

    def perform_create(self, serializer):
        super().perform_create(serializer)
        form_id = getattr(serializer.instance, "form_id", None)
        if form_id:
            self._bust_form_cache(form_id)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        form_id = getattr(serializer.instance, "form_id", None)
        if form_id:
            self._bust_form_cache
