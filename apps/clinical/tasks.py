"""Celery tasks for the clinical app."""

import structlog
from celery import shared_task

from common.tasks import CeliyoBaseTask

logger = structlog.get_logger(__name__)


@shared_task(base=CeliyoBaseTask, bind=True)
def create_clinical_audit_log_task(
    self,
    tenant_id: str,
    record_id: int,
    action: str,
    user_id: str,
    metadata: dict | None = None,
):
    """Create an append-only audit log entry for a clinical record.

    Args:
        tenant_id: UUID string of the tenant.
        record_id: Primary key of the ClinicalRecord.
        action: One of ClinicalRecordAuditLog.Action values.
        user_id: UUID string of the acting SuperAdmin user.
        metadata: Optional dict with IDs/codes (no PHI/field values).
    """
    from .models import ClinicalRecord, ClinicalRecordAuditLog

    metadata = metadata or {}

    try:
        record = ClinicalRecord.objects.get(pk=record_id, tenant_id=tenant_id)
    except ClinicalRecord.DoesNotExist as exc:
        logger.warning(
            "clinical_audit_log_record_missing",
            tenant_id=tenant_id,
            record_id=record_id,
            action=action,
        )
        raise self.apply_retry(exc) from exc

    try:
        ClinicalRecordAuditLog.objects.create(
            tenant_id=record.tenant_id,
            record=record,
            action=action,
            user_id=user_id,
            metadata=metadata,
            created_by_user_id=user_id,
        )
        logger.info(
            "clinical_audit_log_created",
            tenant_id=tenant_id,
            record_id=record_id,
            action=action,
            user_id=user_id,
        )
    except Exception as exc:
        logger.error(
            "clinical_audit_log_failed",
            tenant_id=tenant_id,
            record_id=record_id,
            action=action,
            user_id=user_id,
            error=str(exc),
        )
        raise self.apply_retry(exc) from exc
