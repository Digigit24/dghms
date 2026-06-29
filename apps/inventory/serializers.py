"""
Inventory Serializers
=====================

Follows the same patterns as other DigiHMS apps:
  - tenant_id is always excluded from write payloads (comes from JWT)
  - read-only computed fields are last in field lists
  - separate List vs Detail serializers where needed for performance
"""

from rest_framework import serializers

from .models import (
    InventoryCategory,
    InventorySupplier,
    InventoryItem,
    InventoryBatch,
    StockTransaction,
    StockAlert,
)


# ─── Category ────────────────────────────────────────────────────────────────

class InventoryCategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.SerializerMethodField()
    children_count = serializers.SerializerMethodField()

    class Meta:
        model  = InventoryCategory
        fields = [
            "id", "name", "code", "description",
            "parent", "parent_name",
            "is_active", "children_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_parent_name(self, obj):
        return obj.parent.name if obj.parent else None

    def get_children_count(self, obj):
        return obj.children.count()

    def validate_code(self, value):
        return value.upper().strip() if value else value


# ─── Supplier ────────────────────────────────────────────────────────────────

class InventorySupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model  = InventorySupplier
        fields = [
            "id", "name", "code", "contact_name",
            "phone", "email", "address", "gstin",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ─── Item ────────────────────────────────────────────────────────────────────

class InventoryItemListSerializer(serializers.ModelSerializer):
    """Compact serializer for list views."""

    category_name    = serializers.CharField(source="category.name", read_only=True, default=None)
    is_low_stock     = serializers.BooleanField(read_only=True)
    is_out_of_stock  = serializers.BooleanField(read_only=True)
    is_overstock     = serializers.BooleanField(read_only=True)

    class Meta:
        model  = InventoryItem
        fields = [
            "id", "name", "code", "barcode",
            "category", "category_name",
            "tags", "unit_of_measure",
            "purchase_price", "selling_price",
            "reorder_level", "max_stock_level",
            "current_stock",
            "is_active",
            "is_low_stock", "is_out_of_stock", "is_overstock",
            "created_at",
        ]
        read_only_fields = [
            "id", "current_stock",
            "is_low_stock", "is_out_of_stock", "is_overstock",
            "created_at",
        ]


class InventoryItemSerializer(serializers.ModelSerializer):
    """Full serializer for create / retrieve / update."""

    category_name   = serializers.CharField(source="category.name", read_only=True, default=None)
    is_low_stock    = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)
    is_overstock    = serializers.BooleanField(read_only=True)

    class Meta:
        model  = InventoryItem
        fields = [
            "id", "name", "code", "barcode",
            "category", "category_name",
            "tags", "unit_of_measure",
            "purchase_price", "selling_price",
            "tax_rate", "hsn_code",
            "reorder_level", "max_stock_level",
            "current_stock",
            "description", "is_active",
            "is_low_stock", "is_out_of_stock", "is_overstock",
            "created_by_user_id",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "current_stock",
            "is_low_stock", "is_out_of_stock", "is_overstock",
            "created_at", "updated_at",
        ]

    def validate_tags(self, value):
        valid = {"opd", "ipd", "general", "pharmacy", "surgical", "lab", "other"}
        for tag in value:
            if tag not in valid:
                raise serializers.ValidationError(
                    f"'{tag}' is not a valid tag. Choose from: {', '.join(sorted(valid))}"
                )
        return list(set(value))  # deduplicate


# ─── Batch ────────────────────────────────────────────────────────────────────

class InventoryBatchSerializer(serializers.ModelSerializer):
    item_name        = serializers.CharField(source="item.name", read_only=True)
    supplier_name    = serializers.CharField(source="supplier.name", read_only=True, default=None)
    is_expired       = serializers.BooleanField(read_only=True)
    days_to_expiry   = serializers.IntegerField(read_only=True)

    class Meta:
        model  = InventoryBatch
        fields = [
            "id", "item", "item_name",
            "batch_number", "expiry_date", "manufacturing_date",
            "purchase_date", "supplier", "supplier_name",
            "purchase_price",
            "quantity_received", "remaining_quantity",
            "is_active", "notes",
            "is_expired", "days_to_expiry",
            "created_by_user_id",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "is_expired", "days_to_expiry",
            "created_at", "updated_at",
        ]

    def validate(self, attrs):
        qty_recv = attrs.get("quantity_received", Decimal("0"))
        qty_rem  = attrs.get("remaining_quantity")

        if qty_rem is None:
            attrs["remaining_quantity"] = qty_recv

        if attrs.get("expiry_date") and attrs.get("manufacturing_date"):
            if attrs["expiry_date"] <= attrs["manufacturing_date"]:
                raise serializers.ValidationError(
                    {"expiry_date": "Expiry date must be after manufacturing date."}
                )
        return attrs


from decimal import Decimal   # noqa – needed in validate above


# ─── Stock Transaction ───────────────────────────────────────────────────────

class StockTransactionSerializer(serializers.ModelSerializer):
    item_name        = serializers.CharField(source="item.name", read_only=True)
    item_unit        = serializers.CharField(source="item.unit_of_measure", read_only=True)
    batch_number     = serializers.CharField(source="batch.batch_number", read_only=True, default=None)
    transaction_type_label = serializers.SerializerMethodField()
    is_addition      = serializers.BooleanField(read_only=True)

    class Meta:
        model  = StockTransaction
        fields = [
            "id", "item", "item_name", "item_unit",
            "batch", "batch_number",
            "transaction_type", "transaction_type_label",
            "quantity", "quantity_before", "quantity_after",
            "unit_cost",
            "reference_type", "reference_id",
            "notes", "is_addition",
            "performed_by_user_id",
            "created_at",
        ]
        read_only_fields = [
            "id", "quantity_before", "quantity_after",
            "is_addition", "transaction_type_label",
            "created_at",
        ]

    def get_transaction_type_label(self, obj):
        return dict(StockTransaction.TYPE_CHOICES).get(obj.transaction_type, obj.transaction_type)

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate(self, attrs):
        """Validate batch belongs to the item."""
        batch = attrs.get("batch")
        item  = attrs.get("item")
        if batch and item and batch.item_id != item.id:
            raise serializers.ValidationError(
                {"batch": "This batch does not belong to the selected item."}
            )
        return attrs


# ─── Dedicated action payloads ───────────────────────────────────────────────

class ReceiveStockSerializer(serializers.Serializer):
    """
    POST /inventory/stock-transactions/receive/
    Receive stock from a supplier — creates a new batch.
    """
    item            = serializers.IntegerField()
    batch_number    = serializers.CharField(max_length=80)
    quantity        = serializers.DecimalField(max_digits=10, decimal_places=2,
                        validators=[lambda v: v > 0 or (_ for _ in ()).throw(serializers.ValidationError("Must be > 0"))])
    expiry_date     = serializers.DateField(required=False, allow_null=True)
    manufacturing_date = serializers.DateField(required=False, allow_null=True)
    supplier        = serializers.IntegerField(required=False, allow_null=True)
    unit_cost       = serializers.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    reference_id    = serializers.CharField(max_length=100, default="", allow_blank=True)
    notes           = serializers.CharField(default="", allow_blank=True)


class IssueStockSerializer(serializers.Serializer):
    """
    POST /inventory/stock-transactions/issue/
    Issue stock (to OPD visit, IPD admission, or general).
    """
    item            = serializers.IntegerField()
    batch           = serializers.IntegerField(required=False, allow_null=True)
    quantity        = serializers.DecimalField(max_digits=10, decimal_places=2)
    issue_type      = serializers.ChoiceField(
        choices=["issue_opd", "issue_ipd", "issue_general"],
        default="issue_general",
    )
    reference_type  = serializers.ChoiceField(
        choices=["opd_visit", "ipd_admission", "manual", "other"],
        default="manual",
    )
    reference_id    = serializers.CharField(max_length=100, default="", allow_blank=True)
    notes           = serializers.CharField(default="", allow_blank=True)


class AdjustStockSerializer(serializers.Serializer):
    """
    POST /inventory/stock-transactions/adjust/
    Manual stock adjustment (add or remove).
    """
    item            = serializers.IntegerField()
    batch           = serializers.IntegerField(required=False, allow_null=True)
    adjustment_type = serializers.ChoiceField(
        choices=["adjustment_add", "adjustment_remove", "disposal", "expired"],
    )
    quantity        = serializers.DecimalField(max_digits=10, decimal_places=2)
    notes           = serializers.CharField(default="", allow_blank=True)


# ─── Stock Alert ─────────────────────────────────────────────────────────────

class StockAlertSerializer(serializers.ModelSerializer):
    item_name        = serializers.CharField(source="item.name", read_only=True)
    item_code        = serializers.CharField(source="item.code", read_only=True)
    item_unit        = serializers.CharField(source="item.unit_of_measure", read_only=True)
    batch_number     = serializers.CharField(source="batch.batch_number", read_only=True, default=None)
    expiry_date      = serializers.DateField(source="batch.expiry_date", read_only=True, default=None)
    alert_type_label = serializers.SerializerMethodField()

    class Meta:
        model  = StockAlert
        fields = [
            "id", "item", "item_name", "item_code", "item_unit",
            "batch", "batch_number", "expiry_date",
            "alert_type", "alert_type_label", "message",
            "current_value", "threshold",
            "is_active", "is_acknowledged",
            "acknowledged_by_user_id", "acknowledged_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_alert_type_label(self, obj):
        return dict(StockAlert.ALERT_TYPE_CHOICES).get(obj.alert_type, obj.alert_type)


# ─── Dashboard ───────────────────────────────────────────────────────────────

class InventoryDashboardSerializer(serializers.Serializer):
    total_items         = serializers.IntegerField()
    active_items        = serializers.IntegerField()
    low_stock_count     = serializers.IntegerField()
    out_of_stock_count  = serializers.IntegerField()
    overstock_count     = serializers.IntegerField()
    expiring_soon_count = serializers.IntegerField()
    expired_count       = serializers.IntegerField()
    total_categories    = serializers.IntegerField()
    active_alerts       = serializers.IntegerField()
    unacknowledged_alerts = serializers.IntegerField()
    total_stock_value   = serializers.DecimalField(max_digits=16, decimal_places=2)
    recent_transactions = StockTransactionSerializer(many=True)
