from datetime import datetime, date
from django.db import models, transaction
from django.core.exceptions import ValidationError
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
    name = models.CharField(max_length=100)
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
        constraints = [
            models.UniqueConstraint(
                fields=['tenant_id', 'name'],
                name='unique_payment_category_per_tenant'
            ),
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
        ('razorpay', 'Razorpay'),
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


class BillPaymentSequence(models.Model):
    """Per-tenant-per-day counter used to mint sequential receipt numbers.

    Mirrors ``apps.opd.models.OPDBillSequence``: a single locked counter row
    per (tenant, date, prefix) avoids the phantom-read collision that scanning
    existing rows for "max + 1" is prone to under concurrent payment posting.
    """

    tenant_id = models.UUIDField(db_index=True)
    receipt_date = models.DateField(db_index=True)
    prefix = models.CharField(max_length=30)
    last_sequence = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'bill_payment_sequences'
        unique_together = [['tenant_id', 'receipt_date', 'prefix']]

    def __str__(self):
        return f"{self.prefix}/{self.receipt_date}: {self.last_sequence}"

    @classmethod
    def next_receipt_number(cls, tenant_id, receipt_date, prefix):
        """Atomically claim the next sequence number and format it.

        Must be called inside a transaction.atomic() block — BillPayment.save()
        already provides one.
        """
        cls.objects.get_or_create(tenant_id=tenant_id, receipt_date=receipt_date, prefix=prefix)

        counter = (
            cls.objects
            .select_for_update()
            .get(tenant_id=tenant_id, receipt_date=receipt_date, prefix=prefix)
        )
        counter.last_sequence += 1
        counter.save(update_fields=['last_sequence'])

        date_str = receipt_date.strftime('%Y%m%d')
        return f"{prefix}/{date_str}/{counter.last_sequence:03d}"


class BillPayment(models.Model):
    """Unified payment ledger entry for OPD and IPD (including Daycare) bills.

    Each row is one payment-mode leg of a payment event. A single payment
    event — e.g. one "cash + online" split — produces two rows sharing the
    same ``payment_group_id`` so they print together as one receipt; a plain
    single-mode payment produces one row whose ``payment_group_id`` still
    identifies it (a group of one) so receipt printing/lookup is uniform.
    """

    BILL_TYPE_CHOICES = [
        ('opd', 'OPD'),
        ('ipd', 'IPD'),
        ('daycare', 'Daycare'),
        ('advance', 'Advance'),
    ]
    PAYMENT_MODE_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('bank', 'Bank Transfer'),
        ('online', 'Online'),
        ('insurance', 'Insurance'),
        ('cheque', 'Cheque'),
        ('razorpay', 'Razorpay'),
        ('multiple', 'Multiple'),
        ('other', 'Other'),
    ]

    _RECEIPT_PREFIX_BY_BILL_TYPE = {
        'opd': 'OPD-RCPT',
        'ipd': 'IPD-RCPT',
        'daycare': 'DC-RCPT',
        'advance': 'ADV-RCPT',
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    bill_type = models.CharField(max_length=10, choices=BILL_TYPE_CHOICES)
    opd_bill = models.ForeignKey(
        'opd.OPDBill', null=True, blank=True, on_delete=models.SET_NULL, related_name='bill_payments'
    )
    ipd_bill = models.ForeignKey(
        'ipd.IPDBilling', null=True, blank=True, on_delete=models.SET_NULL, related_name='bill_payments'
    )
    admission = models.ForeignKey(
        'ipd.Admission', null=True, blank=True, on_delete=models.SET_NULL, related_name='advance_payments',
        help_text="Set only for bill_type='advance' rows: an unapplied (or partially applied) advance deposit for this admission.",
    )
    applied_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="bill_type='advance' only: portion of this deposit already applied to a bill via apply_advance.",
    )
    bill_number = models.CharField(max_length=60, blank=True)
    patient_name = models.CharField(max_length=255, blank=True)
    encounter_number = models.CharField(max_length=100, blank=True, help_text="Visit number (OPD) or Admission ID (IPD)")
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODE_CHOICES, default='cash')
    payment_group_id = models.UUIDField(
        null=True, blank=True, db_index=True,
        help_text="Groups the rows recorded together as one payment event (e.g. a cash+online split) so they print as a single receipt."
    )
    receipt_number = models.CharField(
        max_length=40, blank=True, db_index=True,
        help_text="Printable receipt number, auto-generated per tenant on first save."
    )
    payment_date = models.DateField(default=date.today)
    notes = models.TextField(blank=True)
    recorded_by_user_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bill_payments"
        verbose_name = "Bill Payment"
        verbose_name_plural = "Bill Payments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id"], name="billpay_tenant_idx"),
            models.Index(fields=["tenant_id", "bill_type"], name="billpay_tenant_type_idx"),
            models.Index(fields=["tenant_id", "payment_date"], name="billpay_tenant_date_idx"),
            models.Index(fields=["tenant_id", "payment_mode"], name="billpay_tenant_mode_idx"),
            models.Index(fields=["opd_bill"], name="billpay_opd_bill_idx"),
            models.Index(fields=["ipd_bill"], name="billpay_ipd_bill_idx"),
            models.Index(fields=["admission"], name="billpay_admission_idx"),
            models.Index(fields=["payment_group_id"], name="billpay_group_idx"),
        ]

    def __str__(self):
        return f"BillPayment {self.id} [{self.bill_type}] {self.amount}"

    def clean(self):
        """Enforce bill_type/reference-field pairing.

        'advance' rows are unapplied (or partially applied) deposits against
        an admission, not a specific bill — they must carry admission and
        must NOT carry ipd_bill (apply_advance moves money onto a bill's
        received_amount directly; it never repoints this row). opd/ipd/
        daycare rows keep their existing (unenforced-here) shape.
        """
        super().clean()
        if self.bill_type == 'advance':
            if not self.admission_id:
                raise ValidationError({'admission': "Advance payments require an admission."})
            if self.ipd_bill_id:
                raise ValidationError({'ipd_bill': "Advance payments cannot be linked to a bill directly."})

    def save(self, *args, **kwargs):
        """Auto-generate receipt_number on first save (never on later edits).

        Existing rows created before this field was introduced keep a blank
        receipt_number rather than being backfilled, so no uniqueness
        constraint is declared on this column — the per-tenant-per-day
        sequence counter already guarantees every newly generated number is
        collision-free without one.
        """
        self.clean()
        if not self.receipt_number:
            with transaction.atomic():
                prefix = self._RECEIPT_PREFIX_BY_BILL_TYPE.get(self.bill_type, 'RCPT')
                self.receipt_number = BillPaymentSequence.next_receipt_number(
                    self.tenant_id, self.payment_date, prefix
                )
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)
