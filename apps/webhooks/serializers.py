"""Serializers for webhook subscriptions and deliveries."""

from rest_framework import serializers

from common.serializers import TenantAwareSerializer
from .models import TenantWebhook, WebhookDelivery


class TenantWebhookListSerializer(TenantAwareSerializer):
    class Meta:
        model = TenantWebhook
        fields = ["id", "tenant_id", "name", "url", "events", "is_active", "created_at"]
        read_only_fields = ["tenant_id"]


class TenantWebhookDetailSerializer(TenantAwareSerializer):
    class Meta:
        model = TenantWebhook
        fields = [
            "id",
            "tenant_id",
            "name",
            "url",
            "secret",
            "events",
            "is_active",
            "created_at",
            "updated_at",
            "created_by_user_id",
        ]
        read_only_fields = ["tenant_id", "created_by_user_id"]
        extra_kwargs = {"secret": {"write_only": True}}


class TenantWebhookCreateUpdateSerializer(TenantAwareSerializer):
    class Meta:
        model = TenantWebhook
        exclude = ["tenant_id", "created_by_user_id"]
        extra_kwargs = {"secret": {"write_only": True}}


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = [
            "id",
            "tenant_id",
            "webhook",
            "event_name",
            "status",
            "response_status_code",
            "attempt_count",
            "delivered_at",
            "error_message",
            "created_at",
        ]
        read_only_fields = ["tenant_id", "webhook", "event_name", "status", "response_status_code", "attempt_count", "delivered_at", "error_message"]


class WebhookTestSerializer(serializers.Serializer):
    event_name = serializers.CharField(max_length=128)
    payload = serializers.JSONField(default=dict, required=False)
