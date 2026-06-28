"""Tests for webhook dispatch tasks."""

import hashlib
import hmac
import json
import uuid

from django.test import TestCase

from apps.webhooks.models import TenantWebhook, WebhookDelivery
from apps.webhooks.tasks import _sign_payload, dispatch_webhook_event


class WebhookSigningTest(TestCase):
    def test_sign_payload(self):
        payload = {"event": "test", "tenant_id": str(uuid.uuid4())}
        secret = "secret"
        expected = hmac.new(
            secret.encode(),
            json.dumps(payload, separators=(",", ":"), default=str).encode(),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(_sign_payload(payload, secret), expected)


class DispatchWebhookEventTest(TestCase):
    def test_creates_pending_delivery(self):
        tenant_id = uuid.uuid4()
        webhook = TenantWebhook.objects.create(
            tenant_id=tenant_id,
            name="Test",
            url="https://example.com/webhook",
            events=["clinical.record.created"],
        )
        dispatch_webhook_event(str(tenant_id), "clinical.record.created", {"id": 1})
        delivery = WebhookDelivery.objects.get(webhook=webhook)
        self.assertEqual(delivery.status, WebhookDelivery.Status.PENDING)

    def test_skips_unsubscribed_event(self):
        tenant_id = uuid.uuid4()
        TenantWebhook.objects.create(
            tenant_id=tenant_id,
            name="Test",
            url="https://example.com/webhook",
            events=["clinical.record.updated"],
        )
        dispatch_webhook_event(str(tenant_id), "clinical.record.created", {"id": 1})
        self.assertEqual(WebhookDelivery.objects.count(), 0)
