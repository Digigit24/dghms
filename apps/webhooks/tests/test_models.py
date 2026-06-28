"""Tests for webhook models."""

import uuid

from django.test import TestCase

from apps.webhooks.models import TenantWebhook, WebhookDelivery


class TenantWebhookModelTest(TestCase):
    def test_create_webhook(self):
        tenant_id = uuid.uuid4()
        webhook = TenantWebhook.objects.create(
            tenant_id=tenant_id,
            name="Test Hook",
            url="https://example.com/webhook",
            secret="shh",
            events=["clinical.record.created"],
            created_by_user_id=uuid.uuid4(),
        )
        self.assertEqual(webhook.tenant_id, tenant_id)
        self.assertTrue(webhook.is_subscribed_to("clinical.record.created"))
        self.assertFalse(webhook.is_subscribed_to("clinical.record.updated"))

    def test_empty_events_subscribe_to_all(self):
        webhook = TenantWebhook.objects.create(
            tenant_id=uuid.uuid4(),
            name="Catch-all",
            url="https://example.com/webhook",
            events=[],
        )
        self.assertTrue(webhook.is_subscribed_to("any.event"))


class WebhookDeliveryModelTest(TestCase):
    def test_delivery_defaults(self):
        tenant_id = uuid.uuid4()
        webhook = TenantWebhook.objects.create(
            tenant_id=tenant_id,
            name="Test Hook",
            url="https://example.com/webhook",
        )
        delivery = WebhookDelivery.objects.create(
            tenant_id=tenant_id,
            webhook=webhook,
            event_name="clinical.record.created",
            payload={"id": 1},
        )
        self.assertEqual(delivery.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(delivery.attempt_count, 0)
