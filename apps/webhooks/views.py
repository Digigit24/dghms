"""ViewSets for webhook subscriptions and delivery history."""

import structlog
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from common.mixins import TenantViewSetMixin
from common.celery_utils import enqueue_task
from common.pagination import StandardPagination
from common.permissions import check_permission, HMSPermissions
from common.responses import success_response
from .models import TenantWebhook, WebhookDelivery
from .serializers import (
    TenantWebhookCreateUpdateSerializer,
    TenantWebhookDetailSerializer,
    TenantWebhookListSerializer,
    WebhookDeliverySerializer,
    WebhookTestSerializer,
)
from .tasks import _attempt_delivery

logger = structlog.get_logger(__name__)


@extend_schema_view(
    list=extend_schema(
        summary="List webhook subscriptions",
        description="List tenant webhook subscriptions.",
        tags=["Webhooks"],
        responses={200: TenantWebhookListSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve a webhook subscription",
        description="Retrieve a single webhook subscription including its secret (write-only).",
        tags=["Webhooks"],
        responses={200: TenantWebhookDetailSerializer},
    ),
    create=extend_schema(
        summary="Create a webhook subscription",
        description="Subscribe to webhook events for the current tenant.",
        tags=["Webhooks"],
        responses={201: TenantWebhookCreateUpdateSerializer},
    ),
    update=extend_schema(
        summary="Update a webhook subscription",
        description="Replace a webhook subscription.",
        tags=["Webhooks"],
        responses={200: TenantWebhookCreateUpdateSerializer},
    ),
    partial_update=extend_schema(
        summary="Patch a webhook subscription",
        description="Partially update a webhook subscription.",
        tags=["Webhooks"],
        responses={200: TenantWebhookCreateUpdateSerializer},
    ),
    destroy=extend_schema(
        summary="Delete a webhook subscription",
        description="Delete a webhook subscription and its delivery history.",
        tags=["Webhooks"],
        responses={204: None},
    ),
)
class TenantWebhookViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """Manage tenant webhook subscriptions and inspect deliveries."""

    queryset = TenantWebhook.objects.all()
    pagination_class = StandardPagination

    def get_serializer_class(self):
        if self.action == "list":
            return TenantWebhookListSerializer
        if self.action in ["create", "update", "partial_update"]:
            return TenantWebhookCreateUpdateSerializer
        if self.action in ["deliveries", "test"]:
            return WebhookTestSerializer
        return TenantWebhookDetailSerializer

    def get_queryset(self):
        if not check_permission(self.request, HMSPermissions.WEBHOOKS_VIEW):
            raise PermissionDenied("No permission to view webhooks.")
        return super().get_queryset()

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.WEBHOOKS_CREATE):
            raise PermissionDenied("No permission to create webhooks.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.WEBHOOKS_EDIT):
            raise PermissionDenied("No permission to edit webhooks.")
        serializer.save(updated_by_user_id=self.request.user_id)

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.WEBHOOKS_DELETE):
            raise PermissionDenied("No permission to delete webhooks.")
        instance.delete()

    @extend_schema(
        summary="List webhook deliveries",
        description="Returns paginated delivery history for a webhook subscription.",
        tags=["Webhooks"],
        responses={200: WebhookDeliverySerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="deliveries")
    def deliveries(self, request, pk=None):
        webhook = self.get_object()
        queryset = WebhookDelivery.objects.filter(
            tenant_id=request.tenant_id, webhook=webhook
        ).order_by("-created_at")
        page = self.paginate_queryset(queryset)
        serializer = WebhookDeliverySerializer(
            page or queryset, many=True, context={"request": request}
        )
        return self.get_paginated_response(serializer.data) if page else success_response(serializer.data)

    @extend_schema(
        summary="Test webhook",
        description="Send a test event payload to the webhook URL immediately.",
        tags=["Webhooks"],
        request=WebhookTestSerializer,
        responses={200: WebhookDeliverySerializer},
    )
    @action(detail=True, methods=["post"], url_path="test")
    def test(self, request, pk=None):
        webhook = self.get_object()
        serializer = WebhookTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        delivery = WebhookDelivery.objects.create(
            tenant_id=request.tenant_id,
            webhook=webhook,
            event_name=serializer.validated_data["event_name"],
            payload=serializer.validated_data.get("payload", {}),
            status=WebhookDelivery.Status.PENDING,
            attempt_count=0,
        )
        enqueue_task(
            _attempt_delivery,
            log_event="webhook_test_publish_failed",
            tenant_id=str(request.tenant_id),
            delivery_id=delivery.id,
        )
        return success_response(
            data=WebhookDeliverySerializer(delivery).data,
        )
