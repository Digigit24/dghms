# Add the Service catalog model (mirrors ProcedureMaster's shape) for
# generic billable hospital services (nursing/registration/administrative/
# equipment/miscellaneous/other charges).

import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("opd", "0010_visit_notify_referring_doctor"),
    ]

    operations = [
        migrations.CreateModel(
            name="Service",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("tenant_id", models.UUIDField(db_index=True, help_text="Tenant this record belongs to")),
                ("name", models.CharField(max_length=200)),
                ("code", models.CharField(help_text="Unique service code per tenant", max_length=50)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("nursing", "Nursing"),
                            ("registration", "Registration"),
                            ("administrative", "Administrative"),
                            ("equipment", "Equipment"),
                            ("miscellaneous", "Miscellaneous"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=30,
                    ),
                ),
                (
                    "default_charge",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Service",
                "verbose_name_plural": "Services",
                "db_table": "services",
                "ordering": ["category", "name"],
            },
        ),
        migrations.AddIndex(
            model_name="service",
            index=models.Index(fields=["tenant_id"], name="services_tenant__ea97fb_idx"),
        ),
        migrations.AddIndex(
            model_name="service",
            index=models.Index(fields=["tenant_id", "category"], name="services_tenant__545ae5_idx"),
        ),
        migrations.AddIndex(
            model_name="service",
            index=models.Index(fields=["tenant_id", "is_active"], name="services_tenant__aacd0e_idx"),
        ),
        migrations.AddIndex(
            model_name="service",
            index=models.Index(fields=["code"], name="service_code_idx"),
        ),
        migrations.AddIndex(
            model_name="service",
            index=models.Index(fields=["category"], name="service_category_idx"),
        ),
        migrations.AddIndex(
            model_name="service",
            index=models.Index(fields=["is_active"], name="service_active_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="service",
            unique_together={("tenant_id", "code")},
        ),
    ]
