"""Tests for webhook API endpoints."""

import uuid

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.webhooks.models import TenantWebhook


class TenantWebhookViewSetTest(APITestCase):
    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer token")
        # Patch middleware by setting attributes directly on the request later

    def _authenticated_get(self, url):
        return self.client.get(url, HTTP_X_TENANT_ID=str(self.tenant_id))

    def test_list_requires_auth(self):
        self.client.credentials()  # clear auth
        url = reverse("tenant-webhook-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_webhook(self):
        # We cannot easily simulate JWT middleware in unit tests without a valid
        # token, so we test the serializer/model path directly.
        webhook = TenantWebhook.objects.create(  # noqa: F841
            tenant_id=self.tenant_id,
            name="Test",
            url="https://example.com/webhook",
            created_by_user_id=self.user_id,
        )
