from django.db import migrations, models
import django.db.models.deletion


def backfill_prescription_encounter(apps, schema_editor):
    Prescription = apps.get_model("pharmacy", "Prescription")
    ContentType = apps.get_model("contenttypes", "ContentType")
    visit_ct = ContentType.objects.get(app_label="opd", model="visit")
    Prescription.objects.filter(
        visit_id__isnull=False,
        content_type__isnull=True,
    ).update(content_type=visit_ct, object_id=models.F("visit_id"))


def clear_backfilled_prescription_encounter(apps, schema_editor):
    Prescription = apps.get_model("pharmacy", "Prescription")
    ContentType = apps.get_model("contenttypes", "ContentType")
    visit_ct = ContentType.objects.get(app_label="opd", model="visit")
    Prescription.objects.filter(content_type=visit_ct).update(
        content_type=None,
        object_id=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("pharmacy", "0005_remove_prescriptionitem_instructions_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="prescription",
            name="visit",
            field=models.ForeignKey(
                blank=True,
                help_text="OPD visit this prescription belongs to",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="prescriptions",
                to="opd.visit",
            ),
        ),
        migrations.AddField(
            model_name="prescription",
            name="content_type",
            field=models.ForeignKey(
                blank=True,
                help_text="Type of encounter (OPD Visit or IPD Admission)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="prescription",
            name="object_id",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="ID of the encounter record",
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="prescription",
            index=models.Index(
                fields=["tenant_id", "content_type", "object_id"],
                name="pharmacy_pr_tenant__enc_idx",
            ),
        ),
        migrations.AddField(
            model_name="prescriptionitem",
            name="source_row_key",
            field=models.CharField(
                blank=True,
                help_text="Stable clinical grid row key used to reconcile manual prescription rows",
                max_length=128,
            ),
        ),
        migrations.AddIndex(
            model_name="prescriptionitem",
            index=models.Index(
                fields=["tenant_id", "prescription", "source_row_key"],
                name="pharmacy_pr_tenant__row_idx",
            ),
        ),
        migrations.RunPython(
            backfill_prescription_encounter,
            clear_backfilled_prescription_encounter,
        ),
    ]
