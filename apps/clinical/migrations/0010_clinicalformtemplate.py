from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("clinical", "0009_alter_clinicalformfield_field_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClinicalFormTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_id", models.UUIDField(db_index=True)),
                ("name", models.CharField(max_length=200)),
                ("description", models.CharField(blank=True, default="", max_length=500)),
                ("values", models.JSONField(blank=True, default=dict, help_text="Map of field_key -> value.")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by_user_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("form", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name="value_templates", to="clinical.clinicalform")),
            ],
            options={
                "db_table": "clinical_form_templates",
                "ordering": ["name", "id"],
                "unique_together": {("tenant_id", "form", "name")},
            },
        ),
        migrations.AddIndex(
            model_name="clinicalformtemplate",
            index=models.Index(fields=["tenant_id", "form"], name="clinical_fo_tenant__tmpl_idx"),
        ),
    ]
