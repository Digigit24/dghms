from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
import uuid
import datetime
from decimal import Decimal


class FeeType(models.Model):
    """
    Define various fee types that can be applied to orders
    """
    CATEGORY_CHOICES = [
        ('service', 'Service Fee'),
        ('delivery', 'Delivery Fee'),
        ('tax', 'Tax'),
        ('consultation', 'Consultation Fee'),
        ('misc', 'Miscellaneous Fee')
    ]

    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True, null=True)
    is_percentage = models.BooleanField(default=False)
    value = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    class Meta:
        db_table = 'fee_types'
        verbose_name = 'Fee Type'
        verbose_name_plural = 'Fee Types'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'category']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class Order(models.Model):
    """
    Main Order Model for Hospital Services
    Represents a comprehensive order across different service types
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded')
    ]

    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('net_banking', 'Net Banking'),
        ('online', 'Online Payment'),
        ('insurance', 'Insurance'),
        ('other', 'Other')
    ]

    SERVICE_TYPE_CHOICES = [
        ('diagnostic', 'Diagnostic Services'),
        ('nursing_care', 'Nursing Care'),
        ('home_healthcare', 'Home Healthcare'),
        ('consultation', 'Doctor Consultation'),
        ('laboratory', 'Laboratory Tests'),
        ('pharmacy', 'Pharmacy')
    ]

    # Unique Identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    order_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )

    # User & Ownership
    user_id = models.UUIDField(null=True, blank=True, help_text="User who created this order")
    patient = models.ForeignKey(
        'patients.PatientProfile', 
        on_delete=models.CASCADE,
        related_name='orders'
    )
    
    # Order Details
    services_type = models.CharField(
        max_length=20, 
        choices=SERVICE_TYPE_CHOICES
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    
    # Payment Details
    payment_method = models.CharField(
        max_length=20, 
        choices=PAYMENT_METHOD_CHOICES, 
        null=True, 
        blank=True
    )
    is_paid = models.BooleanField(default=False)
    
    # Financial Breakdown
    subtotal = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    total_fees = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    total_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Additional Metadata
    notes = models.TextField(
        blank=True, 
        null=True, 
        help_text="Additional order notes or instructions"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Relationships
    fees = models.ManyToManyField(
        FeeType, 
        through='OrderFee',
        related_name='orders'
    )
    
    class Meta:
        db_table = 'orders'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['tenant_id', 'created_at']),
            models.Index(fields=['patient', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Order {self.order_number} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        """Generate unique order number if not exists"""
        if not self.order_number:
            # Generate order number: ORD2025XXXX
            year = datetime.datetime.now().year
            last_order = Order.objects.filter(
                order_number__startswith=f'ORD{year}'
            ).order_by('-created_at').first()
            
            if last_order:
                try:
                    last_num = int(last_order.order_number[-4:])
                    num = last_num + 1
                except ValueError:
                    num = 1
            else:
                num = 1
            
            self.order_number = f'ORD{year}{num:04d}'
        
        super().save(*args, **kwargs)
    
    def calculate_totals(self):
        """
        Calculate subtotal, fees, and total amount
        """
        # Calculate subtotal from order items
        subtotal = sum(item.get_total_price() for item in self.order_items.all())
        self.subtotal = subtotal
        
        # Calculate total fees
        total_fees = sum(
            fee.calculate_fee_amount(subtotal) 
            for fee in self.fees.all()
        )
        self.total_fees = total_fees
        
        # Calculate total amount
        self.total_amount = subtotal + total_fees
        
        self.save()
        return self.total_amount


class OrderItem(models.Model):
    """
    Polymorphic Order Item Model
    Can reference different types of services
    """
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='order_items'
    )
    
    # Generic Foreign Key to support multiple service types
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE
    )
    object_id = models.PositiveIntegerField()
    service = GenericForeignKey('content_type', 'object_id')
    
    quantity = models.PositiveIntegerField(default=1)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'order_items'
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'order']),
        ]
    
    def get_total_price(self):
        """
        Dynamically get price based on service type
        """
        if self.content_type.model == 'appointment':
            # Get consultation fee from appointment
            return self.service.consultation_fee * self.quantity
        
        # Add more service type price retrievals as needed
        # e.g., for pharmacy items, diagnostic services, etc.
        return Decimal('0.00')
    
    def __str__(self):
        return f"Item for {self.service} - Qty: {self.quantity}"


class OrderFee(models.Model):
    """
    Intermediate model to track fees applied to an order
    """
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='order_fee_details'
    )
    fee_type = models.ForeignKey(
        FeeType, 
        on_delete=models.PROTECT,
        related_name='order_fee_details'
    )
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    class Meta:
        db_table = 'order_fees'
        verbose_name = 'Order Fee'
        verbose_name_plural = 'Order Fees'
        unique_together = ['order', 'fee_type']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'order']),
        ]
    
    def __str__(self):
        return f"{self.fee_type.name} for {self.order}"