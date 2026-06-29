"""Seed hospital-grade system clinical forms (stubbed - full seed via management command)."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("clinical", "0002_seed_system_forms"),
    ]

    operations = [
        # Full hospital system form seeding is done via:
        #   python manage.py seed_system_forms
        # to avoid migration file size limits and allow re-running.
    ]
