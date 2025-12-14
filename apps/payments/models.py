from datetime import datetime
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal
import uuid


class PaymentCategory(models.Model):
    """
    Categories for financial transactions
    """
    CATEGORY_CHOICES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
        ('refund', 'Refund'),
        ('adjustment', 'Accounting Adjustment')
    ]

    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    name = models.CharField(max_length=100, unique=True)
    category_type = models.CharField(
        max_length=20, 
        choices=CATEGORY_CHOICES
    )
    description = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'payment_categories'
        verbose_name = 'Payment Category'
        verbose_name_plural = 'Payment Categories'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'category_type']),
        ]
    
    def __str__(self):
        return self.name


class Transaction(models.Model):
    """
    Comprehensive financial transaction tracking
    """
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('net_banking', 'Net Banking'),
        ('online', 'Online Payment'),
        ('cheque', 'Cheque'),
        ('insurance', 'Insurance'),
        ('other', 'Other')
    ]

    TRANSACTION_TYPE_CHOICES = [
        ('payment', 'Payment Received'),
        ('refund', 'Refund Issued'),
        ('expense', 'Expense'),
        ('adjustment', 'Accounting Adjustment')
    ]

    # Unique Identifiers
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    transaction_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )
    
    # Financial Details
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Categorization
    category = models.ForeignKey(
        PaymentCategory, 
        on_delete=models.PROTECT,
        related_name='transactions'
    )
    transaction_type = models.CharField(
        max_length=20, 
        choices=TRANSACTION_TYPE_CHOICES
    )
    
    # Payment Method
    payment_method = models.CharField(
        max_length=20, 
        choices=PAYMENT_METHOD_CHOICES, 
        null=True, 
        blank=True
    )
    
    # Related Models (Generic Foreign Key to support multiple sources)
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey('content_type', 'object_id')
    
    # User Information
    user_id = models.UUIDField(null=True, blank=True, help_text="User associated with this transaction")

    # Tracking and Metadata
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Transaction description or notes"
    )

    # Reconciliation Fields
    is_reconciled = models.BooleanField(default=False)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_by_id = models.UUIDField(null=True, blank=True, help_text="User who reconciled this transaction")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'transactions'
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'transaction_type']),
            models.Index(fields=['tenant_id', 'created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['category']),
        ]
    
    def save(self, *args, **kwargs):
        """Generate unique transaction number"""
        if not self.transaction_number:
            # Generate transaction number: TRX2025XXXX
            year = datetime.now().year
            last_transaction = Transaction.objects.filter(
                transaction_number__startswith=f'TRX{year}'
            ).order_by('-created_at').first()
            
            if last_transaction:
                try:
                    last_num = int(last_transaction.transaction_number[-4:])
                    num = last_num + 1
                except ValueError:
                    num = 1
            else:
                num = 1
            
            self.transaction_number = f'TRX{year}{num:04d}'
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.transaction_number} - {self.amount} ({self.get_transaction_type_display()})"

class AccountingPeriod(models.Model):
    """
    Financial accounting periods for reporting and reconciliation
    """
    PERIOD_TYPE_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annual', 'Annual')
    ]

    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    period_type = models.CharField(
        max_length=20, 
        choices=PERIOD_TYPE_CHOICES
    )
    
    # Financial Summaries
    total_income = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    total_expenses = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    net_profit = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    
    # Reconciliation Status
    is_closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by_id = models.UUIDField(null=True, blank=True, help_text="User who closed this period")
    
    class Meta:
        db_table = 'accounting_periods'
        verbose_name = 'Accounting Period'
        verbose_name_plural = 'Accounting Periods'
        ordering = ['-start_date']
        unique_together = ['name', 'start_date', 'end_date']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'start_date', 'end_date']),
            models.Index(fields=['tenant_id', 'is_closed']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"
    
    def calculate_financial_summary(self):
        """
        Calculate total income, expenses, and net profit
        for the accounting period
        """
        # Get transactions within this period
        transactions = Transaction.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date
        )
        
        # Calculate totals by transaction type
        self.total_income = transactions.filter(
            transaction_type='payment'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        
        self.total_expenses = transactions.filter(
            transaction_type='expense'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        
        # Calculate net profit
        self.net_profit = self.total_income - self.total_expenses
        
        self.save()
        return {
            'total_income': self.total_income,
            'total_expenses': self.total_expenses,
            'net_profit': self.net_profit
        }