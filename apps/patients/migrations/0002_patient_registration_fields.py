# Additive registration fields for the IPD Registration form (non-breaking).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="patientprofile",
            name="title",
            field=models.CharField(blank=True, default="", max_length=20, help_text="Mr, Mrs, Ms, Dr, Master, Baby, etc."),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="aadhaar_number",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="photo_data",
            field=models.TextField(blank=True, default="", help_text="Base64 data URL of the patient photo."),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="guardian_first_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="guardian_middle_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="guardian_last_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="guardian_mobile",
            field=models.CharField(blank=True, default="", max_length=15),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="guardian_gender",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="guardian_relation",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="guardian_address",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="patientprofile",
            name="guardian_photo_data",
            field=models.TextField(blank=True, default="", help_text="Base64 data URL of the guardian photo."),
        ),
    ]
