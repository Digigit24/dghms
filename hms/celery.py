"""Celery configuration for DigiHMS."""

import os

import structlog
from celery import Celery

logger = structlog.get_logger(__name__)

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hms.settings')

# Create Celery app
app = Celery('hms')

# Load configuration from Django settings with CELERY_ prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

# Celery beat schedule (for periodic tasks, if needed in future)
app.conf.beat_schedule = {
    # Example: Clean up expired products every day
    # 'cleanup-expired-products': {
    #     'task': 'apps.pharmacy.tasks.cleanup_expired_products',
    #     'schedule': crontab(hour=2, minute=0),  # Run at 2 AM daily
    # },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to verify Celery is running."""
    logger.info("celery_debug_task", request_id=self.request.id)
