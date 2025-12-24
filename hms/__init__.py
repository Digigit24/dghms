"""
DigiHMS Application Initialization
"""

# Load Celery app when Django starts (only if celery is installed)
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Celery not installed yet - skip
    celery_app = None
    __all__ = ()
