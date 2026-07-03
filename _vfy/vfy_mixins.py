"""Shared model, serializer, and ViewSet mixins for DigiHMS."""
# (touch: cache-bust fix in CachedFormStructureMixin below)

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import structlog

from .pagination import StandardPagination

logger = structlog.get_logger(__name__)


class TenantModelMixin(models.Model):
    tenant_id = models.UUIDField(db_index=True)

    class Meta:
        abstract = True


class CachedFormStructureMixin:
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
            self._bust_form_cache(form_id)

    def perform_destroy(self, instance):
        form_id = getattr(instance, "form_id", None)
        super().perform_destroy(instance)
        if form_id:
            self._bust_form_cache(form_id)
