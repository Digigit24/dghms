"""Allow inventory_item on PrescriptionItem to be null.

This enables manual prescription entries where no inventory item
is linked (e.g., external medicines, seed data).
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_remove_inventorycategory_unique_inventory_category_code_per_tenant_and_more'),
        ('pharmacy', '0003_prescription_prescriptionitem_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='prescriptionitem',
            name='inventory_item',
            field=models.ForeignKey(
                blank=True,
                help_text='Inventory item being prescribed (nullable for manual entries)',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='prescription_items',
                to='inventory.inventoryitem',
            ),
        ),
        migrations.AlterField(
            model_name='prescriptionitem',
            name='quantity',
            field=models.DecimalField(
                decimal_places=2,
                default='1.00',
                help_text='Quantity prescribed',
                max_digits=10,
            ),
        ),
    ]
