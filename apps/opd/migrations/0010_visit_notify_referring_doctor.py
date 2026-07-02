# Additive migration — adds a single optional boolean field to Visit.
# Mirrors IPD Admission.notify_reference_doctor. Existing rows default to
# False; no backfill needed, no downtime risk (ADD COLUMN ... DEFAULT is
# safe on Postgres for a boolean column).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('opd', '0009_alter_visit_visit_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='notify_referring_doctor',
            field=models.BooleanField(default=False, blank=True, help_text='Whether to send an SMS to the referring doctor'),
        ),
    ]
