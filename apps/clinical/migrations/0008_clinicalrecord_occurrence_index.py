# Generated for repeatable clinical records (round notes, monitoring charts).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0007_clinicaldocumentinstance_clinicaldocumenttemplate_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicalrecord",
            name="occurrence_index",
            field=models.PositiveIntegerField(
                default=1,
                db_index=True,
                help_text=(
                    "1-based instance number for repeatable forms (e.g. round notes, "
                    "monitoring charts). Non-repeatable forms always use 1."
                ),
            ),
        ),
        migrations.AlterUniqueTogether(
            name="clinicalrecord",
            unique_together={
                ("tenant_id", "form", "encounter_type", "encounter_id", "occurrence_index")
            },
        ),
    ]
