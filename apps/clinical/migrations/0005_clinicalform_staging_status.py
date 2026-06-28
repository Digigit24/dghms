"""Add 'staging' as a valid status for ClinicalForm.

AI-generated forms land in 'staging' after apply, requiring an explicit
publish step before they are available for patient encounters.  The
underlying column is a VARCHAR(20) with no DB-level CHECK constraint, so
no column alteration is required — only Django's internal state is updated.

Reversible: reverting removes the choice definition; any rows already set
to 'staging' remain in the DB but the choice is no longer recognised by
Django until the migration is re-applied.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0004_clinicalformgenerationrequest"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clinicalform",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("staging", "Staging"),
                    ("published", "Published"),
                    ("archived", "Archived"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
    ]
