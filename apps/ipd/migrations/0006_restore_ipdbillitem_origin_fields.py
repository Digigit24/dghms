# Restore origin_content_type / origin_object_id / is_price_overridden on
# IPDBillItem, which migration 0004 removed but four call sites in the
# application code (IPDBilling.get_bed_day_info/add_bed_charges,
# IPDBillItemSerializer, IPDBillingViewSet.sync_clinical_charges) still
# reference. No data-loss risk: the dropped columns were empty at the time
# they were removed (0004 immediately preceded any code path that wrote to
# them), so this is a pure schema restoration, safe to run without a
# preserving data migration. Reversible via RemoveField/RemoveIndex.
#
# Semantics differ slightly from before: for source='Bed' items,
# origin_content_type/origin_object_id now point at the Admission itself
# (not any order/clinical model) — this is the dedup key used to compute
# already-billed bed-days across ALL bills for an admission.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("ipd", "0005_admission_registration_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="ipdbillitem",
            name="is_price_overridden",
            field=models.BooleanField(
                default=False,
                help_text="Flag indicating if unit_price was manually changed from system_calculated_price",
            ),
        ),
        migrations.AddField(
            model_name="ipdbillitem",
            name="origin_content_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text="Type of the source record (Admission for bed charges, or a catalog row)",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="ipdbillitem",
            name="origin_object_id",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="ID of the source record referenced by origin_content_type",
            ),
        ),
        migrations.AddIndex(
            model_name="ipdbillitem",
            index=models.Index(
                fields=["origin_content_type", "origin_object_id"],
                name="ipd_bill_it_origin__02f5d1_idx",
            ),
        ),
    ]
