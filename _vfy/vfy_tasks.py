"""Shared Celery task base class for DigiHMS.

All Celery tasks that touch tenant data must:
    - Inherit from :class:`CeliyoBaseTask`
    - Accept ``tenant_id: str`` as their first parameter
    - Use the retry helpers provided here
"""

import structlog
from celery import Task, shared_task

logger = structlog.get_logger(__name__)


class CeliyoBaseTask(Task):
    """Base Celery task with standardized retry policy and structured logging.

    Retry policy:
        - max_retries = 3
        - default_retry_delay = 60 seconds
        - exponential backoff via ``countdown=60 * (2 ** self.request.retries)``
    """

    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3, "default_retry_delay": 60}
    retry_backoff = True
    retry_jitter = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        tenant_id = args[0] if args else kwargs.get("tenant_id")
        logger.error(
            "celery_task_failed",
            task=self.name,
            task_id=task_id,
            tenant_id=str(tenant_id) if tenant_id else None,
            exc_type=type(exc).__name__,
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        tenant_id = args[0] if args else kwargs.get("tenant_id")
        logger.warning(
            "celery_task_retry",
            task=self.name,
            task_id=task_id,
            tenant_id=str(tenant_id) if tenant_id else None,
            attempt=self.request.retries,
            exc_type=type(exc).__name__,
        )
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def apply_retry(self, exc, countdown=None):
        """Call from a task body to retry with exponential backoff.

        Example::

            @shared_task(base=CeliyoBaseTask, bind=True)
            def my_task(self, tenant_id: str, ...):
                try:
                    ...
                except SomeException as exc:
                    raise self.apply_retry(exc)
        """
        if countdown is None:
            countdown = 60 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)


# ===== CDN (Cloudflare) purge tasks =====
# Tenant-agnostic infrastructure tasks — they purge the shared CDN zone, so
# they do not take a tenant_id. Nothing enqueues them automatically yet; call
# them from deploy hooks or admin tooling.


@shared_task(base=CeliyoBaseTask, bind=True, name="common.tasks.purge_cdn_urls")
def purge_cdn_urls(self, urls: list) -> bool:
    """Purge specific URLs from the Cloudflare CDN cache (async)."""
    from common.cloudflare import purge_urls

    return purge_urls(urls)


@shared_task(base=CeliyoBaseTask, bind=True, name="common.tasks.purge_cdn_everything")
def purge_cdn_everything(self) -> bool:
    """Purge the entire Cloudflare CDN zone cache (async). Use sparingly."""
    from common.cloudflare import purge_everything

    return purge_everything()
