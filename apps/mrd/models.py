import uuid
from django.db import models


class MrdExport(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    patient_id = models.IntegerField(db_index=True)
    requested_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)
    item_ids = models.JSONField(default=list)
    export_format = models.CharField(max_length=8, default='pdf')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    artifact_file = models.FileField(upload_to='mrd_exports/', null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['tenant_id', 'patient_id', 'created_at'])]
