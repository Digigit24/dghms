from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clinical", "0013_clinicalform_print_template_code"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clinicalform",
            name="print_template_code",
            field=models.CharField(
                choices=[
                    ("clinical_form", "Generic Clinical Form"),
                    ("nursing_paper", "Nursing Paper"),
                    ("monitoring_chart", "Monitoring Chart"),
                    ("progress_sheet", "Progress Sheet"),
                    ("jeevisha_pain_opd", "Jeevisha Pain OPD"),
                ],
                default="clinical_form",
                help_text="Registered /api/print form code used when printing ClinicalRecord rows for this form.",
                max_length=64,
            ),
        ),
    ]
