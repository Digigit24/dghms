from django.db import migrations, models


PRINT_TEMPLATE_BY_FORM_CODE = {
    "monitoring_chart": "monitoring_chart",
    "system_ipd_monitoring_entry": "monitoring_chart",
    "nursing_initial_assessment": "nursing_paper",
    "nurses_continuation_sheet": "nursing_paper",
    "system_ipd_nursing_notes": "nursing_paper",
    "round_notes": "progress_sheet",
    "short_round_notes": "progress_sheet",
    "progress_sheet": "progress_sheet",
}


def backfill_print_template_codes(apps, schema_editor):
    ClinicalForm = apps.get_model("clinical", "ClinicalForm")
    for form_code, print_template_code in PRINT_TEMPLATE_BY_FORM_CODE.items():
        ClinicalForm.objects.filter(code=form_code).update(print_template_code=print_template_code)


def reset_print_template_codes(apps, schema_editor):
    ClinicalForm = apps.get_model("clinical", "ClinicalForm")
    ClinicalForm.objects.update(print_template_code="clinical_form")


class Migration(migrations.Migration):
    dependencies = [
        ("clinical", "0012_alter_clinicalformfield_field_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicalform",
            name="print_template_code",
            field=models.CharField(
                choices=[
                    ("clinical_form", "Generic Clinical Form"),
                    ("nursing_paper", "Nursing Paper"),
                    ("monitoring_chart", "Monitoring Chart"),
                    ("progress_sheet", "Progress Sheet"),
                ],
                default="clinical_form",
                help_text="Registered /api/print form code used when printing ClinicalRecord rows for this form.",
                max_length=64,
            ),
        ),
        migrations.RunPython(backfill_print_template_codes, reset_print_template_codes),
    ]
