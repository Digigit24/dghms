"""Celery tasks for webhook dispatch."""

import hashlib
import hmac
import json
from datetime import datetime, timezone

import requests
import structlog
from celery import shared_task

from common.tasks import CeliyoBaseTask
from .models import TenantWebhook, WebhookDelivery

logger = structlog.get_logger(__name__)


def _sign_payload(payload: dict, secret: str) -> str:
    """Return HMAC-SHA256 hex signature for the JSON payload."""
    body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@shared_task(base=CeliyoBaseTask, bind=True, max_retries=3, default_retry_delay=60)
def dispatch_webhook_event(self, tenant_id: str, event_name: str, payload: dict):
    """Deliver ``event_name`` to all active webhooks for ``tenant_id``.

    Delivery rows are created in ``pending`` state, updated after each HTTP
    attempt. Retries use exponential backoff: 60s, 300s, 1800s (D-17).
    """
    import uuid

    tenant_uuid = uuid.UUID(tenant_id) if tenant_id else None
    if tenant_uuid is None:
        logger.error("webhook_dispatch_missing_tenant", event_name=event_name)
        return

    webhooks = TenantWebhook.objects.filter(
        tenant_id=tenant_uuid, is_active=True
    )

    for webhook in webhooks:
        if not webhook.is_subscribed_to(event_name):
            continue

        delivery = WebhookDelivery.objects.create(
            tenant_id=tenant_uuid,
            webhook=webhook,
            event_name=event_name,
            payload=payload,
            status=WebhookDelivery.Status.PENDING,
            attempt_count=0,
        )

        _attempt_delivery.delay(
            tenant_id=tenant_id,
            delivery_id=delivery.id,
        )


@shared_task(base=CeliyoBaseTask, bind=True, max_retries=3, default_retry_delay=60)
def _attempt_delivery(self, tenant_id: str, delivery_id: int):
    """Attempt a single webhook delivery and schedule retry on failure."""
    import uuid

    tenant_uuid = uuid.UUID(tenant_id) if tenant_id else None
    try:
        delivery = WebhookDelivery.objects.get(tenant_id=tenant_uuid, id=delivery_id)
    except WebhookDelivery.DoesNotExist:
        logger.error("webhook_delivery_not_found", delivery_id=delivery_id)
        return

    webhook = delivery.webhook
    delivery.attempt_count += 1

    signed_payload = {
        "event": delivery.event_name,
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": delivery.payload,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Celiyo-Event": delivery.event_name,
        "X-Celiyo-Tenant": tenant_id,
        "X-Celiyo-Delivery": str(delivery.id),
        "X-Celiyo-Attempt": str(delivery.attempt_count),
    }
    if webhook.secret:
        headers["X-Celiyo-Signature"] = _sign_payload(signed_payload, webhook.secret)

    try:
        response = requests.post(
            webhook.url,
            json=signed_payload,
            headers=headers,
            timeout=30,
        )
        delivery.response_status_code = response.status_code
        delivery.response_body = response.text[:2000]
    except requests.RequestException as exc:
        delivery.response_status_code = None
        delivery.response_body = ""
        delivery.error_message = str(exc)[:1000]
        response = None

    if response is not None and 200 <= response.status_code < 300:
        delivery.status = WebhookDelivery.Status.SUCCESS
        delivery.delivered_at = datetime.now(timezone.utc)
        delivery.save(update_fields=[
            "status",
            "response_status_code",
            "response_body",
            "attempt_count",
            "delivered_at",
            "updated_at",
        ])
        logger.info(
            "webhook_delivery_success",
            delivery_id=delivery.id,
            webhook_id=webhook.id,
            status_code=delivery.response_status_code,
        )
        return

    delivery.status = WebhookDelivery.Status.FAILED if delivery.attempt_count >= 3 else WebhookDelivery.Status.PENDING
    delivery.error_message = delivery.error_message or f"HTTP {delivery.response_status_code}"
    delivery.save(update_fields=[
        "status",
        "response_status_code",
        "response_body",
        "attempt_count",
        "error_message",
        "updated_at",
    ])

    if delivery.attempt_count < 3:
        countdown = 60 * (5 ** (delivery.attempt_count - 1))  # 60, 300, 1800
        logger.warning(
            "webhook_delivery_retry",
            delivery_id=delivery.id,
            attempt=delivery.attempt_count,
            countdown=countdown,
        )
        raise self.retry(countdown=countdown)

    logger.error(
        "webhook_delivery_failed",
        delivery_id=delivery.id,
        webhook_id=webhook.id,
        attempts=delivery.attempt_count,
    )
