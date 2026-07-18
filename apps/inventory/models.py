"""
Inventory Management Models
===========================

Six core models that cover the full inventory lifecycle:

  InventoryCategory   – hierarchical item categories (medicines, surgical, etc.)
  InventorySupplier   – supplier / vendor master
  InventoryItem       – item master with tags (opd/ipd/general/other), thresholds
  InventoryBatch      – per-batch expiry & quantity tracking (FEFO support)
  StockTransaction    – immutable movement ledger (purchase / issue / adjust …)
  StockAlert          – auto-generated alerts for low stock / expiry

All models are tenant-scoped (tenant_id as first indexed field per CLAUDE.md).
"""

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


# ─── 1. Category ─────────────────────────────────────────────────────────────

class InventoryCategory(models.Model):
    """Hierarchical category tree for inventory items."""

    tenant_id  = models.UUIDField(db_index=True)
    name       = models.CharField(max_length=120)
    code       = models.CharField(max_length=30, blank=True,
                    help_text="Short code, e.g. MED, SURG, EQP")
    description = models.TextField(blank=True)
    expiry_alert_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional expiry-alert lead time for items in this category.",
    )
    parent     = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = "inventory_categories"
        ordering     = ["name"]
        unique_together = [["tenant_id", "code"]]
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "is_active"]),
        ]

    def __str__(self):
        return self.name


# ─── 2. Supplier ─────────────────────────────────────────────────────────────

class InventorySupplier(models.Model):
    """Vendor / supplier master."""

    tenant_id    = models.UUIDField(db_index=True)
    name         = models.CharField(max_length=200)
    code         = models.CharField(max_length=30, blank=True)
    contact_name = models.CharField(max_length=120, blank=True)
    phone        = models.CharField(max_length=20, blank=True)
    email        = models.EmailField(blank=True)
    address      = models.TextField(blank=True)
    gstin        = models.CharField(max_length=20, blank=True,
                    help_text="GST Identification Number")
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table   = "inventory_suppliers"
        ordering   = ["name"]
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "is_active"]),
        ]

    def __str__(self):
        return self.name


# ─── 3. Item Master ──────────────────────────────────────────────────────────

class InventoryItem(models.Model):
    """
    Inventory item master.

    ``current_stock`` is a denormalized running total maintained atomically
    via F() expressions on every StockTransaction. Do NOT update it directly.
    """

    UNIT_CHOICES = [
        ("pcs",     "Pieces"),
        ("strip",   "Strip"),
        ("box",     "Box"),
        ("bottle",  "Bottle"),
        ("vial",    "Vial"),
        ("ampoule", "Ampoule"),
        ("ml",      "mL"),
        ("litre",   "Litre"),
        ("gm",      "Gram"),
        ("kg",      "Kilogram"),
        ("tablet",  "Tablet"),
        ("capsule", "Capsule"),
        ("sachet",  "Sachet"),
        ("roll",    "Roll"),
        ("pair",    "Pair"),
        ("set",     "Set"),
        ("other",   "Other"),
    ]

    TAG_CHOICES = ["opd", "ipd", "general", "pharmacy", "surgical", "lab", "other"]

    tenant_id   = models.UUIDField(db_index=True)
    name        = models.CharField(max_length=200)
    code        = models.CharField(max_length=50, blank=True,
                    help_text="Internal SKU / item code")
    barcode     = models.CharField(max_length=100, blank=True)
    category    = models.ForeignKey(
        InventoryCategory, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="items",
    )

    # Tags – stored as JSON list, e.g. ["opd", "general"]
    tags        = models.JSONField(
        default=list, blank=True,
        help_text='List of usage tags: opd, ipd, general, pharmacy, surgical, lab, other',
    )

    # Unit & pricing
    unit_of_measure = models.CharField(max_length=20, choices=UNIT_CHOICES, default="pcs")
    purchase_price  = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    selling_price   = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    tax_rate        = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        help_text="GST % (e.g. 12.00)",
    )
    hsn_code        = models.CharField(max_length=20, blank=True,
                        help_text="HSN code for GST")

    # Stock thresholds
    reorder_level   = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        help_text="Alert fires when current_stock falls to or below this level",
    )
    max_stock_level = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        help_text="Alert fires when current_stock exceeds this level (0 = disabled)",
    )
    expiry_alert_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional item-specific expiry-alert lead time in days.",
    )

    # Denormalized running stock – maintained by StockTransaction.save()
    current_stock   = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
    )

    description     = models.TextField(blank=True)
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table   = "inventory_items"
        ordering   = ["name"]
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "category"]),
            models.Index(fields=["tenant_id", "current_stock"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code or self.id})"

    @property
    def is_low_stock(self):
        return self.current_stock <= self.reorder_level

    @property
    def is_out_of_stock(self):
        return self.current_stock <= 0

    @property
    def is_overstock(self):
        return (
            self.max_stock_level > 0
            and self.current_stock > self.max_stock_level
        )


# ─── 4. Batch ────────────────────────────────────────────────────────────────

class InventoryBatch(models.Model):
    """
    One purchase lot for an item.  Tracks expiry + remaining quantity.

    ``remaining_quantity`` is decremented atomically when stock is issued
    against this batch.
    """

    tenant_id          = models.UUIDField(db_index=True)
    item               = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name="batches",
    )
    batch_number       = models.CharField(max_length=80)
    expiry_date        = models.DateField(null=True, blank=True)
    manufacturing_date = models.DateField(null=True, blank=True)
    purchase_date      = models.DateField(default=timezone.now)
    supplier           = models.ForeignKey(
        InventorySupplier, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="batches",
    )
    purchase_price     = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
    )
    quantity_received  = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
    )
    remaining_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
    )
    is_active          = models.BooleanField(default=True)
    notes              = models.TextField(blank=True)
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "inventory_batches"
        ordering = ["expiry_date", "created_at"]
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "item"]),
            models.Index(fields=["tenant_id", "expiry_date"]),
            models.Index(fields=["item", "expiry_date"]),
        ]

    def __str__(self):
        return f"{self.item.name} | Batch {self.batch_number}"

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.now().date())

    @property
    def days_to_expiry(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.now().date()).days


# ─── 5. Stock Transaction ────────────────────────────────────────────────────

class StockTransaction(models.Model):
    """
    Immutable movement ledger entry.

    Every change to stock – purchase, issue, return, adjustment, disposal –
    is recorded here.  quantity_delta is always positive; transaction_type
    determines whether it is an addition or reduction.

    On save(), ``InventoryItem.current_stock`` and, if batch is set,
    ``InventoryBatch.remaining_quantity`` are updated atomically.
    """

    TYPE_CHOICES = [
        # Additions
        ("opening_stock",   "Opening Stock"),
        ("purchase",        "Purchase / Received"),
        ("return_from_use", "Return From Use"),
        ("adjustment_add",  "Adjustment — Add"),
        # Reductions
        ("issue_opd",       "Issued to OPD"),
        ("issue_ipd",       "Issued to IPD"),
        ("issue_general",   "Issued — General"),
        ("adjustment_remove","Adjustment — Remove"),
        ("disposal",        "Disposal / Write-off"),
        ("transfer_out",    "Transfer Out"),
        ("expired",         "Expired Stock"),
    ]

    # Increase transaction types (positive delta on item stock)
    ADDITION_TYPES = {
        "opening_stock", "purchase", "return_from_use", "adjustment_add",
    }

    REFERENCE_TYPES = [
        ("opd_visit",      "OPD Visit"),
        ("ipd_admission",  "IPD Admission"),
        ("purchase_order", "Purchase Order"),
        ("manual",         "Manual Entry"),
        ("transfer",       "Transfer"),
        ("other",          "Other"),
    ]

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id        = models.UUIDField(db_index=True)
    item             = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name="transactions",
    )
    batch            = models.ForeignKey(
        InventoryBatch, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="transactions",
    )

    transaction_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    quantity         = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Always positive; direction inferred from transaction_type",
    )
    quantity_before  = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    quantity_after   = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    unit_cost        = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        help_text="Cost per unit at time of transaction",
    )

    # What triggered this transaction
    reference_type   = models.CharField(
        max_length=30, choices=REFERENCE_TYPES, default="manual",
    )
    reference_id     = models.CharField(max_length=100, blank=True,
                        help_text="e.g. visit ID, admission ID, PO number")

    notes            = models.TextField(blank=True)
    performed_by_user_id = models.UUIDField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "item"]),
            models.Index(fields=["tenant_id", "transaction_type"]),
            models.Index(fields=["tenant_id", "created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self):
        return f"{self.transaction_type} | {self.item.name} | qty {self.quantity}"

    @property
    def is_addition(self):
        return self.transaction_type in self.ADDITION_TYPES


# ─── 6. Stock Alert ──────────────────────────────────────────────────────────

class StockAlert(models.Model):
    """
    Auto-generated alert for low stock, out-of-stock, expiry, or overstock.

    Alerts are created/refreshed by ``_check_and_update_alerts()`` which is
    called after every StockTransaction and batch save.
    """

    ALERT_TYPE_CHOICES = [
        ("low_stock",          "Low Stock"),
        ("out_of_stock",       "Out of Stock"),
        ("expiry_approaching", "Expiry Approaching"),
        ("expired",            "Expired"),
        ("overstock",          "Overstock"),
    ]

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id     = models.UUIDField(db_index=True)
    item          = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name="alerts",
    )
    batch         = models.ForeignKey(
        InventoryBatch, null=True, blank=True,
        on_delete=models.CASCADE, related_name="alerts",
    )
    alert_type    = models.CharField(max_length=30, choices=ALERT_TYPE_CHOICES)
    message       = models.CharField(max_length=300)

    # Thresholds snapshot at time of generation
    current_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    threshold     = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    is_active         = models.BooleanField(default=True,
                          help_text="False once the condition resolves")
    is_acknowledged   = models.BooleanField(default=False)
    acknowledged_by_user_id = models.UUIDField(null=True, blank=True)
    acknowledged_at   = models.DateTimeField(null=True, blank=True)

    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_alerts"
        ordering = ["-created_at"]
        # One active alert per (item, alert_type) — or per (item, batch, alert_type)
        unique_together = [["tenant_id", "item", "alert_type", "batch"]]
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "alert_type"]),
            models.Index(fields=["tenant_id", "is_acknowledged"]),
        ]

    def __str__(self):
        return f"{self.alert_type} | {self.item.name}"
