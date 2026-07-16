from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.contrib.postgres.indexes import GinIndex


class ProductCategory(models.Model):
    """Product category for pharmacy items"""
    CATEGORY_TYPES = [
        ('medicine', 'Medicine'),
        ('healthcare_product', 'Healthcare Product'),
        ('medical_equipment', 'Medical Equipment')
    ]

    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True, null=True)
    type = models.CharField(max_length=50, choices=CATEGORY_TYPES)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pharmacy_product_categories'
        verbose_name_plural = 'Product Categories'
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'name']),
        ]

    def __str__(self):
        return self.name


class PharmacyProduct(models.Model):
    """Pharmacy product model"""
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    product_name = models.CharField(max_length=255)
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )
    company = models.CharField(max_length=255, blank=True, null=True)
    batch_no = models.CharField(max_length=100, blank=True, null=True)

    # Pricing
    mrp = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        blank=True,
        null=True
    )

    # Inventory
    quantity = models.PositiveIntegerField(default=0)
    minimum_stock_level = models.PositiveIntegerField(default=10)

    # Dates
    expiry_date = models.DateField(blank=True, null=True)

    # Status
    is_active = models.BooleanField(default=True)

    # Full-text search vector (populated automatically)
    search_vector = SearchVectorField(null=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pharmacy_products'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'product_name']),
            models.Index(fields=['product_name']),
            models.Index(fields=['company']),
            models.Index(fields=['batch_no']),
            GinIndex(fields=['search_vector'], name='pharmacy_search_vector_idx'),
        ]

    def __str__(self):
        return self.product_name

    @property
    def is_in_stock(self):
        return self.quantity > 0

    @property
    def low_stock_warning(self):
        return self.quantity <= self.minimum_stock_level

    def save(self, *args, **kwargs):
        if not self.selling_price:
            self.selling_price = self.mrp
        super().save(*args, **kwargs)
        PharmacyProduct.objects.filter(pk=self.pk).update(
            search_vector=(
                SearchVector('product_name', weight='A', config='english') +
                SearchVector('company', weight='B', config='english') +
                SearchVector('batch_no', weight='C', config='english')
            )
        )


class Cart(models.Model):
    """Shopping cart for pharmacy products"""
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    user_id = models.UUIDField(unique=True, help_text="User who owns this cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pharmacy_carts'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'user_id']),
        ]

    def __str__(self):
        return f"Cart of user {self.user_id}"

    @property
    def total_items(self):
        return self.cart_items.aggregate(total=models.Sum('quantity'))['total'] or 0

    @property
    def total_amount(self):
        return sum(
            item.price_at_time * item.quantity
            for item in self.cart_items.all()
        )


class CartItem(models.Model):
    """Individual items in the shopping cart"""
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='cart_items')
    product = models.ForeignKey(PharmacyProduct, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price_at_time = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    class Meta:
        db_table = 'pharmacy_cart_items'
        unique_together = ['cart', 'product']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'cart']),
        ]

    def save(self, *args, **kwargs):
        if not self.price_at_time:
            self.price_at_time = self.product.selling_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.product_name} - {self.quantity}"

    @property
    def total_price(self):
        return self.quantity * self.price_at_time


class PharmacyOrder(models.Model):
    """Pharmacy order model"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ]
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded')
    ]

    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    user_id = models.UUIDField(null=True, blank=True, help_text="User who placed this order")
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    shipping_address = models.TextField()
    billing_address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pharmacy_orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['tenant_id', 'user_id']),
        ]

    def __str__(self):
        return f"Order {self.id} - {self.get_status_display()}"


class PharmacyOrderItem(models.Model):
    """Items in a pharmacy order"""
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    order = models.ForeignKey(PharmacyOrder, on_delete=models.CASCADE, related_name='order_items')
    product = models.ForeignKey(PharmacyProduct, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price_at_time = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    class Meta:
        db_table = 'pharmacy_order_items'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'order']),
        ]

    def __str__(self):
        return f"{self.product.product_name} - {self.quantity}"

    @property
    def total_price(self):
        return self.quantity * self.price_at_time


class Prescription(models.Model):
    """Clinical prescription tied to an OPD/IPD encounter."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partially_dispensed', 'Partially Dispensed'),
        ('dispensed', 'Dispensed'),
        ('cancelled', 'Cancelled'),
    ]

    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    visit = models.ForeignKey(
        'opd.Visit',
        on_delete=models.CASCADE,
        related_name='prescriptions',
        null=True,
        blank=True,
        help_text="OPD visit this prescription belongs to",
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Type of encounter (OPD Visit or IPD Admission)",
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the encounter record",
    )
    encounter = GenericForeignKey("content_type", "object_id")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, help_text="General prescription notes")
    created_by_user_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pharmacy_prescriptions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id'], name='pharmacy_pr_tenant__ca0aef_idx'),
            models.Index(fields=['tenant_id', 'visit'], name='pharmacy_pr_tenant__ee0c13_idx'),
            models.Index(fields=['tenant_id', 'content_type', 'object_id'], name='pharmacy_pr_tenant__enc_idx'),
            models.Index(fields=['tenant_id', 'status'], name='pharmacy_pr_tenant__34ac52_idx'),
        ]

    def __str__(self):
        if self.visit_id:
            return f"Prescription {self.id} for visit {self.visit_id}"
        return f"Prescription {self.id} for encounter {self.content_type_id}:{self.object_id}"

    def recalculate_status(self):
        """Recalculate aggregate prescription status from line item dispense state."""
        items = list(self.items.all())
        if not items:
            self.status = 'pending'
            return self.status
        dispensed_count = sum(1 for item in items if item.is_dispensed)
        if dispensed_count == 0:
            self.status = 'pending'
        elif dispensed_count == len(items):
            self.status = 'dispensed'
        else:
            self.status = 'partially_dispensed'
        return self.status


class PrescriptionItem(models.Model):
    """Individual medicine line item within a prescription."""

    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name='items',
    )
    inventory_item = models.ForeignKey(
        'inventory.InventoryItem',
        on_delete=models.PROTECT,
        related_name='prescription_items',
        null=True,
        blank=True,
        help_text="Inventory item being prescribed (nullable for manual entries)",
    )
    medicine_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Snapshot of inventory item name at prescription time",
    )
    source_row_key = models.CharField(
        max_length=128,
        blank=True,
        help_text="Stable clinical grid row key used to reconcile manual prescription rows",
    )
    dosage = models.CharField(max_length=100, blank=True)
    frequency = models.CharField(max_length=100, blank=True)
    duration = models.CharField(max_length=100, blank=True)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Quantity prescribed",
    )
    dispensed_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    is_dispensed = models.BooleanField(default=False)
    dispensed_at = models.DateTimeField(null=True, blank=True)
    dispensed_by_user_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pharmacy_prescription_items'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['tenant_id'], name='pharmacy_pr_tenant__eafb3e_idx'),
            models.Index(fields=['tenant_id', 'prescription'], name='pharmacy_pr_tenant__8a3b6e_idx'),
            models.Index(fields=['tenant_id', 'inventory_item'], name='pharmacy_pr_tenant__58cd22_idx'),
            models.Index(fields=['tenant_id', 'prescription', 'source_row_key'], name='pharmacy_pr_tenant__row_idx'),
        ]

    def __str__(self):
        return f"{self.medicine_name or self.inventory_item_id} - {self.quantity}"

    def mark_dispensed(self, quantity=None, user_id=None):
        """Mark item as dispensed and record metadata."""
        from django.utils import timezone
        self.is_dispensed = True
        if quantity is not None:
            self.dispensed_quantity = quantity
        self.dispensed_at = timezone.now()
        if user_id is not None:
            self.dispensed_by_user_id = user_id
        self.save()
