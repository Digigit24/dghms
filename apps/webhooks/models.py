"""Webhook subscription and delivery tracking for DigiHMS tenants."""

from django.db import models


class TenantWebhook(models.Model):
    """A tenant-owned webhook subscription."""

    class EventChoice(models.TextChoices):
        # Keep a small set of known events; additional events can be stored in events_json.
        RECORD_CREATED = "clinical.record.created", "Clinical Record Created"
        RECORD_UPDATED = "clinical.record.updated", "Clinical Record Updated"
        RECORD_LOCKED = "clinical.record.locked", "Clinical Record Locked"
        RECORD_UNLOCKED = "clinical.record.unlocked", "Clinical Record Unlocked"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    name = models.CharField(max_length=200)
    url = models.URLField(max_length=1000)
    secret = models.CharField(max_length=255, blank=True, default="", help_text="Shared secret for HMAC-SHA256 signature")
    events = models.JSONField(default=list, help_text="List of event names to subscribe to; empty means all")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "tenant_webhooks"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} -> {self.url}"

    def is_subscribed_to(self, event_name):
        if not self.events:
            return True
        return event_name in self.events


class WebhookDelivery(models.Model):
    """A single webhook delivery attempt record."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    webhook = models.ForeignKey(
        TenantWebhook,
        on_delete=models.CASCADE,
        related_name="deliveries",
        db_index=True,
    )
    event_name = models.CharField(max_length=128, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    response_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True, default="")
    attempt_count = models.PositiveSmallIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "webhook_deliveries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "webhook", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.event_name} -> {self.status} ({self.attempt_count})"
