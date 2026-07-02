"""Additive: tenant-configurable print letterhead layout on the Hospital singleton.

Backward-compatible — the new column defaults to an empty dict ``{}``, which
the API/serializer layer interprets as "not configured yet" and falls back to
a computed default built from existing Hospital fields (name, address, email,
phone, registration_number, logo). Small per-tenant table (Hospital is a
singleton per tenant/DB); no zero-downtime concerns. Reversible via
RemoveField.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hospital", "0003_hospital_nav_style"),
    ]

    operations = [
        migrations.AddField(
            model_name="hospital",
            name="letterhead_config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Tenant-configurable print letterhead layout (logo, badge, text lines, alignment)",
            ),
        ),
    ]
