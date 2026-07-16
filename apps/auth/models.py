from django.db import models


class RolePermissionAudit(models.Model):
    tenant_id = models.UUIDField(db_index=True)
    role_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_user_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=16)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
