# Add 'Service' to IPDBillItem.SOURCE_CHOICES so bill items created from the
# new Service catalog (apps.opd.models.Service) can be tagged correctly.
# Choices-only change — no schema/data impact, safe on any table size.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ipd", "0007_ipdbilltemplate_ipdbilltemplateitem"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ipdbillitem",
            name="source",
            field=models.CharField(
                choices=[
                    ("Bed", "Bed Charges"),
                    ("Pharmacy", "Pharmacy"),
                    ("Lab", "Laboratory"),
                    ("Radiology", "Radiology"),
                    ("Consultation", "Consultation"),
                    ("Procedure", "Procedure"),
                    ("Surgery", "Surgery"),
                    ("Therapy", "Therapy"),
                    ("Package", "Package"),
                    ("Service", "Service"),
                    ("Other", "Other"),
                ],
                default="Other",
                help_text="Source/category of the charge",
                max_length=20,
            ),
        ),
    ]
