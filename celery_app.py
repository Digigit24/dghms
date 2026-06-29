"""Top-level Celery application for DigiHMS.

Usage::

    celery -A celery_app worker -l info
    celery -A celery_app beat -l info

This module re-exports the Celery app defined in ``hms.celery`` so that
worker commands can target the project root directly.
"""

import os

# Ensure Django settings are available before the Celery app is imported.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hms.settings")


