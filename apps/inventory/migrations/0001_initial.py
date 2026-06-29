"""
Initial migration for the Inventory Management app.

Creates 6 tables:
  inventory_categories
  inventory_suppliers
  inventory_items
  inventory_batches
  inventory_transactions
  inventory_alerts
"""

import uuid
from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        # ── 1. Categories ────────────────────────────────────────────────────
        migrations.CreateModel(
            name="InventoryCategory",
            fields=[
                ("id",          models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_id",   models.UUIDField(db_index=True)),
                ("name",        models.CharField(max_length=120)),
                ("code",        models.CharField(blank=True, help_text="Short code, e.g. MED, SURG, EQP", max_length=30)),
                ("description", models.TextField(blank=True)),
                ("parent",      models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="children", to="inventory.inventorycategory")),
                ("is_active",   models.BooleanField(default=True)),
                ("created_at",  models.DateTimeField(auto_now_add=True)),
                ("updated_at",  models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "inventory_categories",
                "ordering": ["name"],
            },
        ),
        migrations.AddConstraint(
            model_name="inventorycategory",
            constraint=models.UniqueConstraint(fields=["tenant_id", "code"], name="unique_inventory_category_code_per_tenant", condition=models.Q(code__gt="")),
        ),
        migrations.AddIndex(
            model_name="inventorycategory",
            index=models.Index(fields=["tenant_id"], name="inv_cat_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="inventorycategory",
            index=models.Index(fields=["tenant_id", "is_active"], name="inv_cat_tenant_active_idx"),
        ),

        # ── 2. Suppliers ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name="InventorySupplier",
            fields=[
                ("id",           models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_id",    models.UUIDField(db_index=True)),
                ("name",         models.CharField(max_length=200)),
                ("code",         models.CharField(blank=True, max_length=30)),
                ("contact_name", models.CharField(blank=True, max_length=120)),
                ("phone",        models.CharField(blank=True, max_length=20)),
                ("email",        models.EmailField(blank=True)),
                ("address",      models.TextField(blank=True)),
                ("gstin",        models.CharField(blank=True, help_text="GST Identification Number", max_length=20)),
                ("is_active",    models.BooleanField(default=True)),
                ("created_at",   models.DateTimeField(auto_now_add=True)),
                ("updated_at",   models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "inventory_suppliers",
                "ordering": ["name"],
            },
        ),
        migrations.AddIndex(
            model_name="inventorysupplier",
            index=models.Index(fields=["tenant_id"], name="inv_sup_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="inventorysupplier",
            index=models.Index(fields=["tenant_id", "is_active"], name="inv_sup_tenant_active_idx"),
        ),

        # ── 3. Items ─────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="InventoryItem",
            fields=[
                ("id",              models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_id",       models.UUIDField(db_index=True)),
                ("name",            models.CharField(max_length=200)),
                ("code",            models.CharField(blank=True, help_text="Internal SKU / item code", max_length=50)),
                ("barcode",         models.CharField(blank=True, max_length=100)),
                ("category",        models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="items", to="inventory.inventorycategory")),
                ("tags",            models.JSONField(blank=True, default=list, help_text="List of usage tags: opd, ipd, general, pharmacy, surgical, lab, other")),
                ("unit_of_measure", models.CharField(choices=[("pcs","Pieces"),("strip","Strip"),("box","Box"),("bottle","Bottle"),("vial","Vial"),("ampoule","Ampoule"),("ml","mL"),("litre","Litre"),("gm","Gram"),("kg","Kilogram"),("tablet","Tablet"),("capsule","Capsule"),("sachet","Sachet"),("roll","Roll"),("pair","Pair"),("set","Set"),("other","Other")], default="pcs", max_length=20)),
                ("purchase_price",  models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("selling_price",   models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("tax_rate",        models.DecimalField(decimal_places=2, default=Decimal("0.00"), help_text="GST % (e.g. 12.00)", max_digits=5)),
                ("hsn_code",        models.CharField(blank=True, help_text="HSN code for GST", max_length=20)),
                ("reorder_level",   models.DecimalField(decimal_places=2, default=Decimal("0.00"), help_text="Alert fires when current_stock falls to or below this level", max_digits=10)),
                ("max_stock_level", models.DecimalField(decimal_places=2, default=Decimal("0.00"), help_text="Alert fires when current_stock exceeds this level (0 = disabled)", max_digits=10)),
                ("current_stock",   models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("description",     models.TextField(blank=True)),
                ("is_active",       models.BooleanField(default=True)),
                ("created_by_user_id", models.UUIDField(blank=True, null=True)),
                ("created_at",      models.DateTimeField(auto_now_add=True)),
                ("updated_at",      models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "inventory_items",
                "ordering": ["name"],
            },
        ),
        migrations.AddIndex(
            model_name="inventoryitem",
            index=models.Index(fields=["tenant_id"], name="inv_item_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="inventoryitem",
            index=models.Index(fields=["tenant_id", "is_active"], name="inv_item_tenant_active_idx"),
        ),
        migrations.AddIndex(
            model_name="inventoryitem",
            index=models.Index(fields=["tenant_id", "category"], name="inv_item_tenant_cat_idx"),
        ),
        migrations.AddIndex(
            model_name="inventoryitem",
            index=models.Index(fields=["tenant_id", "current_stock"], name="inv_item_tenant_stock_idx"),
        ),

        # ── 4. Batches ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name="InventoryBatch",
            fields=[
                ("id",                 models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_id",          models.UUIDField(db_index=True)),
                ("item",               models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="batches", to="inventory.inventoryitem")),
                ("batch_number",       models.CharField(max_length=80)),
                ("expiry_date",        models.DateField(blank=True, null=True)),
                ("manufacturing_date", models.DateField(blank=True, null=True)),
                ("purchase_date",      models.DateField(default=django.utils.timezone.now)),
                ("supplier",           models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="batches", to="inventory.inventorysupplier")),
                ("purchase_price",     models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("quantity_received",  models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("remaining_quantity", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("is_active",          models.BooleanField(default=True)),
                ("notes",              models.TextField(blank=True)),
                ("created_by_user_id", models.UUIDField(blank=True, null=True)),
                ("created_at",         models.DateTimeField(auto_now_add=True)),
                ("updated_at",         models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "inventory_batches",
                "ordering": ["expiry_date", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="inventorybatch",
            index=models.Index(fields=["tenant_id"], name="inv_batch_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="inventorybatch",
            index=models.Index(fields=["tenant_id", "item"], name="inv_batch_tenant_item_idx"),
        ),
        migrations.AddIndex(
            model_name="inventorybatch",
            index=models.Index(fields=["tenant_id", "expiry_date"], name="inv_batch_tenant_expiry_idx"),
        ),
        migrations.AddIndex(
            model_name="inventorybatch",
            index=models.Index(fields=["item", "expiry_date"], name="inv_batch_item_expiry_idx"),
        ),

        # ── 5. Stock Transactions ─────────────────────────────────────────────
        migrations.CreateModel(
            name="StockTransaction",
            fields=[
                ("id",               models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_id",        models.UUIDField(db_index=True)),
                ("item",             models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="inventory.inventoryitem")),
                ("batch",            models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transactions", to="inventory.inventorybatch")),
                ("transaction_type", models.CharField(choices=[("opening_stock","Opening Stock"),("purchase","Purchase / Received"),("return_from_use","Return From Use"),("adjustment_add","Adjustment — Add"),("issue_opd","Issued to OPD"),("issue_ipd","Issued to IPD"),("issue_general","Issued — General"),("adjustment_remove","Adjustment — Remove"),("disposal","Disposal / Write-off"),("transfer_out","Transfer Out"),("expired","Expired Stock")], max_length=30)),
                ("quantity",         models.DecimalField(decimal_places=2, help_text="Always positive; direction inferred from transaction_type", max_digits=10)),
                ("quantity_before",  models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("quantity_after",   models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("unit_cost",        models.DecimalField(decimal_places=2, default=Decimal("0.00"), help_text="Cost per unit at time of transaction", max_digits=10)),
                ("reference_type",   models.CharField(choices=[("opd_visit","OPD Visit"),("ipd_admission","IPD Admission"),("purchase_order","Purchase Order"),("manual","Manual Entry"),("transfer","Transfer"),("other","Other")], default="manual", max_length=30)),
                ("reference_id",     models.CharField(blank=True, help_text="e.g. visit ID, admission ID, PO number", max_length=100)),
                ("notes",            models.TextField(blank=True)),
                ("performed_by_user_id", models.UUIDField(blank=True, null=True)),
                ("created_at",       models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "inventory_transactions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="stocktransaction",
            index=models.Index(fields=["tenant_id"], name="inv_txn_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="stocktransaction",
            index=models.Index(fields=["tenant_id", "item"], name="inv_txn_tenant_item_idx"),
        ),
        migrations.AddIndex(
            model_name="stocktransaction",
            index=models.Index(fields=["tenant_id", "transaction_type"], name="inv_txn_tenant_type_idx"),
        ),
        migrations.AddIndex(
            model_name="stocktransaction",
            index=models.Index(fields=["tenant_id", "created_at"], name="inv_txn_tenant_date_idx"),
        ),
        migrations.AddIndex(
            model_name="stocktransaction",
            index=models.Index(fields=["reference_type", "reference_id"], name="inv_txn_ref_idx"),
        ),

        # ── 6. Stock Alerts ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="StockAlert",
            fields=[
                ("id",            models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_id",     models.UUIDField(db_index=True)),
                ("item",          models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alerts", to="inventory.inventoryitem")),
                ("batch",         models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="alerts", to="inventory.inventorybatch")),
                ("alert_type",    models.CharField(choices=[("low_stock","Low Stock"),("out_of_stock","Out of Stock"),("expiry_approaching","Expiry Approaching"),("expired","Expired"),("overstock","Overstock")], max_length=30)),
                ("message",       models.CharField(max_length=300)),
                ("current_value", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("threshold",     models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("is_active",          models.BooleanField(default=True, help_text="False once the condition resolves")),
                ("is_acknowledged",    models.BooleanField(default=False)),
                ("acknowledged_by_user_id", models.UUIDField(blank=True, null=True)),
                ("acknowledged_at",    models.DateTimeField(blank=True, null=True)),
                ("created_at",         models.DateTimeField(auto_now_add=True)),
                ("updated_at",         models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "inventory_alerts",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="stockalert",
            unique_together={("tenant_id", "item", "alert_type", "batch")},
        ),
        migrations.AddIndex(
            model_name="stockalert",
            index=models.Index(fields=["tenant_id"], name="inv_alert_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="stockalert",
            index=models.Index(fields=["tenant_id", "is_active"], name="inv_alert_tenant_active_idx"),
        ),
        migrations.AddIndex(
            model_name="stockalert",
            index=models.Index(fields=["tenant_id", "alert_type"], name="inv_alert_tenant_type_idx"),
        ),
        migrations.AddIndex(
            model_name="stockalert",
            index=models.Index(fields=["tenant_id", "is_acknowledged"], name="inv_alert_tenant_ack_idx"),
        ),
    ]
