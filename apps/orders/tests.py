# apps/orders/tests.py

import hashlib
import hmac
import json
import uuid

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.orders.models import Order, RazorpayConfig
from apps.patients.models import PatientProfile


class RazorpayWebhookTenantTest(APITestCase):
    """P0 regression: Razorpay webhook must derive tenant from the stored order."""

    def setUp(self):
        self.tenant_a = uuid.uuid4()
        self.tenant_b = uuid.uuid4()

        self.patient_a = PatientProfile.objects.create(
            tenant_id=self.tenant_a,
            first_name='Test',
            last_name='Patient',
            phone='1111111111',
        )

        self.order = Order.objects.create(
            tenant_id=self.tenant_a,
            patient=self.patient_a,
            services_type='consultation',
            total_amount=100,
            razorpay_order_id='order_test_123',
        )

        RazorpayConfig.objects.create(
            tenant_id=self.tenant_a,
            razorpay_key_id='key_a',
            razorpay_key_secret='secret_a',
            razorpay_webhook_secret='webhook_secret_a',
        )
        RazorpayConfig.objects.create(
            tenant_id=self.tenant_b,
            razorpay_key_id='key_b',
            razorpay_key_secret='secret_b',
            razorpay_webhook_secret='webhook_secret_b',
        )

    def _build_payload(self, order_id):
        return json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': 'pay_test_123',
                        'order_id': order_id,
                    }
                }
            }
        }).encode('utf-8')

    def _sign(self, payload, secret):
        return hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()

    def test_webhook_with_order_tenant_succeeds(self):
        """A correctly signed webhook for the order's tenant is accepted."""
        payload = self._build_payload(self.order.razorpay_order_id)
        signature = self._sign(payload, 'webhook_secret_a')

        response = self.client.post(
            '/api/orders/webhooks/razorpay/',
            data=payload,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)

    def test_webhook_signed_with_wrong_tenant_secret_fails(self):
        """A payload signed with tenant B's secret for an order owned by tenant A fails verification."""
        payload = self._build_payload(self.order.razorpay_order_id)
        signature = self._sign(payload, 'webhook_secret_b')

        response = self.client.post(
            '/api/orders/webhooks/razorpay/',
            data=payload,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_webhook_order_without_tenant_returns_400(self):
        """An order missing tenant_id must be rejected before processing."""
        order_no_tenant = Order.objects.create(
            tenant_id=None,
            patient=self.patient_a,
            services_type='consultation',
            total_amount=100,
            razorpay_order_id='order_no_tenant_123',
        )
        payload = self._build_payload(order_no_tenant.razorpay_order_id)
        # Signature does not matter because tenant guard runs first.
        signature = self._sign(payload, 'webhook_secret_a')

        response = self.client.post(
            '/api/orders/webhooks/razorpay/',
            data=payload,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
