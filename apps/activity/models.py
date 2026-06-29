"""Async activity log storage for DigiHMS audit trail."""

from django.db import models


class UserActivityLog(models.Model):
    """A single user activity event captured by ActivityLogMiddleware."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    user_id = models.UUIDField(null=True, blank=True, db_index=True)
    method = models.CharField(max_length=16)
    path = models.CharField(max_length=2048)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "user_activity_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "-created_at"]),
            models.Index(fields=["tenant_id", "user_id", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.method} {self.path} {self.status_code}"
