# Additive registration fields on Admission (non-breaking).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ipd", "0004_alter_ipdbillitem_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="admission",
            name="admission_type",
            field=models.CharField(
                max_length=20,
                default="regular",
                choices=[
                    ("regular", "Regular"),
                    ("emergency", "Emergency"),
                    ("transfer", "Transfer"),
                    ("readmission", "Readmission"),
                ],
                help_text="Type of admission",
            ),
        ),
        migrations.AddField(
            model_name="admission",
            name="reference_doctor_id",
            field=models.UUIDField(null=True, blank=True, help_text="SuperAdmin User ID of the reference/referring doctor"),
        ),
        migrations.AddField(
            model_name="admission",
            name="notify_reference_doctor",
            field=models.BooleanField(default=False, help_text="Whether to send an SMS to the reference doctor"),
        ),
        migrations.AddField(
            model_name="admission",
            name="consulting_doctor_ids",
            field=models.JSONField(default=list, blank=True, help_text="List of SuperAdmin User IDs of consulting doctors (multiple allowed)"),
        ),
    ]
