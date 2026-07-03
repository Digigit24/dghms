"""Additive: tenant-wide UI theme configuration on the Hospital singleton.

Backward-compatible — defaults to an empty dict ``{}``.  The frontend reads
``theme_config.primary_color`` (a hex string) on startup and applies it as the
default primary colour.  Empty dict → frontend falls back to the user's own
stored colour or the system default (#3b82f6 / hsl 221 83% 53%).

Reversible via RemoveField.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hospital", "0004_hospital_letterhead_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="hospital",
            name="theme_config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Tenant-wide UI theme. JSON: { "primary_color": "#hexcolour" }',
            ),
        ),
    ]
