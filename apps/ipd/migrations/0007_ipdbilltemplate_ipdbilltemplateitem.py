# Add IPDBillTemplate + IPDBillTemplateItem — reusable sets of bill line
# items ('Bed' is intentionally never a valid template item source; bed
# charges are always computed per-bill from the admission's actual length
# of stay).

import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ipd", "0006_restore_ipdbillitem_origin_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="IPDBillTemplate",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("tenant_id", models.UUIDField(db_index=True, help_text="Tenant this record belongs to")),
                ("name", models.CharField(help_text="Template name", max_length=200)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "created_by_user_id",
                    models.UUIDField(blank=True, db_index=True, help_text="User who created this template", null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "IPD Bill Template",
                "verbose_name_plural": "IPD Bill Templates",
                "db_table": "ipd_bill_templates",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="IPDBillTemplateItem",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("tenant_id", models.UUIDField(db_index=True, help_text="Tenant this record belongs to")),
                ("item_name", models.CharField(help_text="Description of the item/service", max_length=200)),
                (
                    "source",
                    models.CharField(
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
                        help_text="Source/category of the charge (never 'Bed')",
                        max_length=20,
                    ),
                ),
                ("default_quantity", models.PositiveIntegerField(default=1)),
                (
                    "default_unit_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                        help_text="Default unit price applied when this template is used",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="ipd.ipdbilltemplate",
                        help_text="Bill template this item belongs to",
                    ),
                ),
            ],
            options={
                "verbose_name": "IPD Bill Template Item",
                "verbose_name_plural": "IPD Bill Template Items",
                "db_table": "ipd_bill_template_items",
                "ordering": ["id"],
            },
        ),
        migrations.AddIndex(
            model_name="ipdbilltemplate",
            index=models.Index(fields=["tenant_id"], name="ipd_bill_te_tenant__97bcf9_idx"),
        ),
        migrations.AddIndex(
            model_name="ipdbilltemplate",
            index=models.Index(fields=["tenant_id", "is_active"], name="ipd_bill_te_tenant__0454d1_idx"),
        ),
        migrations.AddIndex(
            model_name="ipdbilltemplateitem",
            index=models.Index(fields=["tenant_id"], name="ipd_bill_te_tenant__3f1f85_idx"),
        ),
        migrations.AddIndex(
            model_name="ipdbilltemplateitem",
            index=models.Index(fields=["tenant_id", "template"], name="ipd_bill_te_tenant__570575_idx"),
        ),
    ]
