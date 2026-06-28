"""Celery task for writing user activity log entries."""

import structlog
import uuid
from celery import shared_task

from common.tasks import CeliyoBaseTask
from .models import UserActivityLog

logger = structlog.get_logger(__name__)


def _scrub_path(path: str) -> str:
    """Return the path without query string to avoid logging sensitive data."""
    if not path:
        return path
    return path.split("?", 1)[0]


@shared_task(base=CeliyoBaseTask, bind=True, max_retries=3, default_retry_delay=60)
def write_activity_log_entry(
    self,
    tenant_id: str,
    user_id: str,
    method: str,
    path: str,
    status_code: int,
    ip_address: str,
    user_agent: str,
):
    """Persist an activity log row asynchronously."""
    scrubbed_path = _scrub_path(path)
    try:
        tenant_uuid = uuid.UUID(tenant_id) if tenant_id else None
        user_uuid = uuid.UUID(user_id) if user_id else None
        UserActivityLog.objects.create(
            tenant_id=tenant_uuid,
            user_id=user_uuid,
            method=method,
            path=scrubbed_path,
            status_code=status_code,
            ip_address=ip_address or None,
            user_agent=user_agent or "",
            created_by_user_id=user_uuid,
        )
        logger.info(
            "activity_log_written",
            tenant_id=tenant_id,
            user_id=user_id,
            method=method,
            path=scrubbed_path,
            status_code=status_code,
        )
    except Exception as exc:
        logger.error(
            "activity_log_write_failed",
            tenant_id=tenant_id,
            path=scrubbed_path,
            error=str(exc),
        )
        raise self.apply_retry(exc)
