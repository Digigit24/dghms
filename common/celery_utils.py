"""Request-safe Celery publishing helpers."""

import structlog
from celery import states
from celery.result import AsyncResult


logger = structlog.get_logger(__name__)


def enqueue_task(task, *, log_event="celery_task_publish_failed", **kwargs):
    """Publish once, returning ``None`` when the broker is unavailable."""
    try:
        return task.apply_async(kwargs=kwargs, retry=False)
    except Exception as exc:
        logger.warning(log_event, task=getattr(task, "name", str(task)), error=str(exc))
        return None


def get_task_snapshot(task_id):
    """Read task state without allowing a result-backend outage to escape."""
    try:
        result = AsyncResult(task_id)
        state = result.state
        return {
            "state": state,
            "ready": state in states.READY_STATES,
            "successful": state == states.SUCCESS,
            "result": result.result if state == states.SUCCESS else None,
            "info": result.info if state == states.FAILURE else None,
        }
    except Exception as exc:
        logger.warning("celery_result_backend_unavailable", task_id=task_id, error=str(exc))
        return None
