"""Additive: tenant-wide UI navigation style preference on the Hospital singleton.

Backward-compatible — the new column defaults to "horizontal" so existing
rows keep their current (implicit) frontend behaviour. Small per-tenant
table (Hospital is a singleton per tenant/DB); no zero-downtime concerns.
Reversible via RemoveField.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hospital", "0002_patient_id_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="hospital",
            name="nav_style",
            field=models.CharField(
                choices=[("horizontal", "Horizontal"), ("vertical", "Vertical")],
                default="horizontal",
                help_text="Tenant-wide preference: horizontal top nav vs vertical sidebar",
                max_length=10,
            ),
        ),
    ]
