"""Additive: per-tenant UHID (patient_id) prefix/format config.

Backward-compatible — every column has a default that reproduces the legacy
``PAT{year}NNNN`` scheme, so existing rows and behaviour are unchanged.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hospital", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="hospital",
            name="patient_id_prefix",
            field=models.CharField(
                default="PAT",
                help_text="UHID prefix, e.g. 'UHID' or 'PAT'.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="hospital",
            name="patient_id_include_year",
            field=models.BooleanField(
                default=True,
                help_text="Include the 4-digit year after the prefix (e.g. PAT2026...).",
            ),
        ),
        migrations.AddField(
            model_name="hospital",
            name="patient_id_padding",
            field=models.PositiveSmallIntegerField(
                default=4,
                help_text="Zero-padding width for the running number (e.g. 6 -> UHID000123).",
            ),
        ),
    ]
