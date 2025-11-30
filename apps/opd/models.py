# opd/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import os

User = get_user_model()


class Visit(models.Model):
    """
    Visit Model - Core OPD visit tracking.
    
    Tracks every patient visit to the OPD, managing queue positions,
    consultation timing, and payment status.
    """
    
    VISIT_TYPE_CHOICES = [
        ('new', 'New Visit'),
        ('follow_up', 'Follow-up'),
        ('emergency', 'Emergency'),
    ]
    
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('called', 'Called'),
        ('in_consultation', 'In Consultation'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
    ]
    
    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    visit_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique visit identifier (e.g., OPD/20231223/001)"
    )
    
    # Related Models
    patient = models.ForeignKey(
        'patients.PatientProfile',
        on_delete=models.PROTECT,
        related_name='opd_visits'
    )
    doctor = models.ForeignKey(
        'doctors.DoctorProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='opd_visits',
        help_text="Assigned when patient is called"
    )
    appointment = models.ForeignKey(
        'appointments.Appointment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='opd_visit',
        help_text="For scheduled visits"
    )
    referred_by = models.ForeignKey(
        'doctors.DoctorProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referred_visits',
        help_text="Referring doctor if applicable"
    )
    created_by_id = models.UUIDField(null=True, blank=True, help_text="User who created the visit")
    
    # Visit Information
    visit_date = models.DateField(auto_now_add=True)
    visit_type = models.CharField(
        max_length=20,
        choices=VISIT_TYPE_CHOICES,
        default='new'
    )
    entry_time = models.DateTimeField(auto_now_add=True)
    is_follow_up = models.BooleanField(default=False)
    
    # Queue Management
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='waiting'
    )
    queue_position = models.IntegerField(
        null=True,
        blank=True,
        help_text="Position in waiting queue"
    )
    
    # Consultation Timing
    consultation_start_time = models.DateTimeField(
        null=True,
        blank=True
    )
    consultation_end_time = models.DateTimeField(
        null=True,
        blank=True
    )
    
    # Payment Information
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid'
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    paid_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    balance_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'opd_visits'
        ordering = ['-visit_date', '-entry_time']
        verbose_name = 'OPD Visit'
        verbose_name_plural = 'OPD Visits'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'visit_date']),
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['visit_number'], name='visit_number_idx'),
            models.Index(fields=['patient', 'visit_date'], name='visit_patient_date_idx'),
            models.Index(fields=['doctor', 'visit_date'], name='visit_doctor_date_idx'),
            models.Index(fields=['status', 'visit_date'], name='visit_status_date_idx'),
            models.Index(fields=['payment_status'], name='visit_payment_idx'),
        ]
    
    def __str__(self):
        return self.visit_number
    
    def save(self, *args, **kwargs):
        """Auto-generate visit number if not set."""
        if not self.visit_number:
            self.visit_number = self.generate_visit_number()
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_visit_number():
        """Generate unique visit number: OPD/YYYYMMDD/###"""
        from datetime import date
        today = date.today()
        date_str = today.strftime('%Y%m%d')
        
        # Get count of visits for today
        today_count = Visit.objects.filter(
            visit_date=today
        ).count() + 1
        
        return f"OPD/{date_str}/{today_count:03d}"
    
    def calculate_waiting_time(self):
        """Calculate time spent in waiting queue."""
        if self.consultation_start_time:
            delta = self.consultation_start_time - self.entry_time
            return int(delta.total_seconds() / 60)  # Return minutes
        return None
    
    def get_queue_position(self):
        """Calculate current position in queue."""
        if self.status not in ['waiting', 'called']:
            return None
        
        return Visit.objects.filter(
            visit_date=self.visit_date,
            status__in=['waiting', 'called'],
            entry_time__lt=self.entry_time
        ).count() + 1
    
    def update_payment_status(self):
        """Update payment status based on amounts."""
        if self.paid_amount >= self.total_amount:
            self.payment_status = 'paid'
            self.balance_amount = Decimal('0.00')
        elif self.paid_amount > Decimal('0.00'):
            self.payment_status = 'partial'
            self.balance_amount = self.total_amount - self.paid_amount
        else:
            self.payment_status = 'unpaid'
            self.balance_amount = self.total_amount
        self.save()


class OPDBill(models.Model):
    """
    OPD Bill Model - Consultation billing.
    
    Stores billing details for OPD consultations including
    fees, discounts, and payment information.
    """
    
    OPD_TYPE_CHOICES = [
        ('consultation', 'Consultation'),
        ('follow_up', 'Follow-up'),
        ('emergency', 'Emergency'),
    ]
    
    CHARGE_TYPE_CHOICES = [
        ('first_visit', 'First Visit'),
        ('revisit', 'Revisit'),
        ('emergency', 'Emergency'),
    ]
    
    PAYMENT_MODE_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('bank', 'Bank Transfer'),
        ('multiple', 'Multiple Modes'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
    ]
    
    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    visit = models.OneToOneField(
        Visit,
        on_delete=models.CASCADE,
        related_name='opd_bill'
    )
    bill_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique bill identifier (e.g., OPD-BILL/20231223/001)"
    )
    bill_date = models.DateTimeField(auto_now_add=True)
    
    # Doctor Information
    doctor = models.ForeignKey(
        'doctors.DoctorProfile',
        on_delete=models.PROTECT,
        related_name='opd_bills'
    )
    
    # Bill Classification
    opd_type = models.CharField(
        max_length=20,
        choices=OPD_TYPE_CHOICES,
        default='consultation'
    )
    opd_subtype = models.CharField(
        max_length=50,
        blank=True,
        default='NA',
        help_text="Additional classification if needed"
    )
    charge_type = models.CharField(
        max_length=20,
        choices=CHARGE_TYPE_CHOICES,
        default='first_visit'
    )
    
    # Medical Information
    diagnosis = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    
    # Financial Details
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('100.00'))
        ]
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    payable_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Payment Details
    payment_mode = models.CharField(
        max_length=20,
        choices=PAYMENT_MODE_CHOICES,
        default='cash'
    )
    payment_details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Store multiple payment details"
    )
    received_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    balance_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid'
    )
    
    # Audit Fields
    billed_by_id = models.UUIDField(null=True, blank=True, help_text="User who created this bill")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'opd_bills'
        ordering = ['-bill_date']
        verbose_name = 'OPD Bill'
        verbose_name_plural = 'OPD Bills'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'bill_date']),
            models.Index(fields=['tenant_id', 'payment_status']),
            models.Index(fields=['bill_number'], name='opd_bill_number_idx'),
            models.Index(fields=['visit'], name='opd_bill_visit_idx'),
            models.Index(fields=['doctor', 'bill_date'], name='opd_bill_doctor_date_idx'),
            models.Index(fields=['payment_status'], name='opd_bill_payment_idx'),
        ]
    
    def __str__(self):
        return self.bill_number
    
    def save(self, *args, **kwargs):
        """Auto-generate bill number and calculate amounts."""
        if not self.bill_number:
            self.bill_number = self.generate_bill_number()
        self.calculate_totals()
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_bill_number():
        """Generate unique bill number: OPD-BILL/YYYYMMDD/###"""
        from datetime import date
        today = date.today()
        date_str = today.strftime('%Y%m%d')
        
        # Get count of bills for today
        today_count = OPDBill.objects.filter(
            bill_date__date=today
        ).count() + 1
        
        return f"OPD-BILL/{date_str}/{today_count:03d}"
    
    def calculate_totals(self):
        """Calculate payable amount after discount."""
        # Calculate discount amount
        if self.discount_percent > 0:
            self.discount_amount = (
                self.total_amount * self.discount_percent / Decimal('100.00')
            )
        
        # Calculate payable amount
        self.payable_amount = self.total_amount - self.discount_amount
        
        # Calculate balance
        self.balance_amount = self.payable_amount - self.received_amount
        
        # Update payment status
        if self.received_amount >= self.payable_amount:
            self.payment_status = 'paid'
            self.balance_amount = Decimal('0.00')
        elif self.received_amount > Decimal('0.00'):
            self.payment_status = 'partial'
        else:
            self.payment_status = 'unpaid'

    def record_payment(self, amount, mode='cash', details=None, user_id=None):
        """
        Record a payment for this bill and create a financial transaction.

        Args:
            amount: Payment amount
            mode: Payment method (cash, card, upi, etc.)
            details: Additional payment details (dict)
            user_id: User ID who processed the payment
        """
        from apps.payments.models import Transaction, PaymentCategory
        from django.contrib.contenttypes.models import ContentType

        payment_amount = Decimal(str(amount))
        self.received_amount += payment_amount
        self.payment_mode = mode

        if details:
            self.payment_details = details

        self.calculate_totals()
        self.save()

        # Update visit payment status
        self.visit.paid_amount += payment_amount
        self.visit.update_payment_status()

        # Create financial transaction record
        try:
            # Get or create "OPD Consultation" category
            category, _ = PaymentCategory.objects.get_or_create(
                name='OPD Consultation',
                tenant_id=self.tenant_id,
                defaults={
                    'category_type': 'income',
                    'description': 'Revenue from OPD consultation fees'
                }
            )

            # Map payment mode to transaction payment method
            payment_method_mapping = {
                'cash': 'cash',
                'card': 'card',
                'upi': 'upi',
                'bank': 'net_banking',
                'multiple': 'other',
            }
            transaction_payment_method = payment_method_mapping.get(mode, 'cash')

            # Create transaction
            Transaction.objects.create(
                tenant_id=self.tenant_id,
                amount=payment_amount,
                category=category,
                transaction_type='payment',
                payment_method=transaction_payment_method,
                content_type=ContentType.objects.get_for_model(OPDBill),
                object_id=self.id,
                user_id=user_id,
                description=f'OPD Bill payment - {self.bill_number} (Visit: {self.visit.visit_number})'
            )
        except Exception as e:
            # Log error but don't fail the payment recording
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Failed to create transaction for OPD bill {self.bill_number}: {str(e)}')


class ProcedureMaster(models.Model):
    """
    Procedure Master Model - Master data for procedures and tests.
    
    Stores available procedures, tests, and investigations
    with their default charges.
    """
    
    CATEGORY_CHOICES = [
        ('laboratory', 'Laboratory'),
        ('radiology', 'Radiology'),
        ('cardiology', 'Cardiology'),
        ('pathology', 'Pathology'),
        ('ultrasound', 'Ultrasound'),
        ('ct_scan', 'CT Scan'),
        ('mri', 'MRI'),
        ('ecg', 'ECG'),
        ('xray', 'X-Ray'),
        ('other', 'Other'),
    ]
    
    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    name = models.CharField(max_length=200)
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique procedure code"
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES
    )
    description = models.TextField(blank=True)
    
    # Pricing
    default_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'procedure_masters'
        ordering = ['category', 'name']
        verbose_name = 'Procedure Master'
        verbose_name_plural = 'Procedure Masters'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'category']),
            models.Index(fields=['tenant_id', 'is_active']),
            models.Index(fields=['code'], name='proc_master_code_idx'),
            models.Index(fields=['category'], name='proc_master_category_idx'),
            models.Index(fields=['is_active'], name='proc_master_active_idx'),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class ProcedurePackage(models.Model):
    """
    Procedure Package Model - Bundled procedures.
    
    Groups multiple procedures into packages with
    discounted pricing.
    """
    
    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    name = models.CharField(max_length=200)
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique package code"
    )
    
    # Procedures
    procedures = models.ManyToManyField(
        ProcedureMaster,
        related_name='packages'
    )
    
    # Pricing
    total_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Sum of individual procedure charges"
    )
    discounted_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Package discounted price"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'procedure_packages'
        ordering = ['name']
        verbose_name = 'Procedure Package'
        verbose_name_plural = 'Procedure Packages'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'is_active']),
            models.Index(fields=['code'], name='proc_package_code_idx'),
            models.Index(fields=['is_active'], name='proc_package_active_idx'),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    @property
    def discount_percent(self):
        """Calculate discount percentage."""
        if self.total_charge > 0:
            discount = self.total_charge - self.discounted_charge
            return (discount / self.total_charge) * 100
        return 0
    
    @property
    def savings_amount(self):
        """Calculate savings amount."""
        return self.total_charge - self.discounted_charge


class ProcedureBill(models.Model):
    """
    Procedure Bill Model - Investigation billing.
    
    Stores billing for procedures and investigations
    ordered during OPD visits.
    """
    
    BILL_TYPE_CHOICES = [
        ('hospital', 'Hospital'),
        ('diagnostic', 'Diagnostic Center'),
        ('external', 'External Lab'),
    ]
    
    PAYMENT_MODE_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('bank', 'Bank Transfer'),
        ('multiple', 'Multiple Modes'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
    ]
    
    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    visit = models.ForeignKey(
        Visit,
        on_delete=models.CASCADE,
        related_name='procedure_bills'
    )
    bill_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique bill identifier (e.g., PROC-BILL/20231223/001)"
    )
    bill_date = models.DateTimeField(auto_now_add=True)
    
    # Doctor Information
    doctor = models.ForeignKey(
        'doctors.DoctorProfile',
        on_delete=models.PROTECT,
        related_name='ordered_procedures',
        help_text="Doctor who ordered the procedures"
    )
    
    # Bill Classification
    bill_type = models.CharField(
        max_length=20,
        choices=BILL_TYPE_CHOICES,
        default='hospital'
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        help_text="Additional categorization"
    )
    
    # Financial Details
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('100.00'))
        ]
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    payable_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Payment Details
    payment_mode = models.CharField(
        max_length=20,
        choices=PAYMENT_MODE_CHOICES,
        default='cash'
    )
    payment_details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Store multiple payment details"
    )
    received_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    balance_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid'
    )
    
    # Audit Fields
    billed_by_id = models.UUIDField(null=True, blank=True, help_text="User who created this bill")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'procedure_bills'
        ordering = ['-bill_date']
        verbose_name = 'Procedure Bill'
        verbose_name_plural = 'Procedure Bills'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'bill_date']),
            models.Index(fields=['tenant_id', 'payment_status']),
            models.Index(fields=['bill_number'], name='proc_bill_number_idx'),
            models.Index(fields=['visit'], name='proc_bill_visit_idx'),
            models.Index(fields=['doctor', 'bill_date'], name='proc_bill_doctor_date_idx'),
            models.Index(fields=['payment_status'], name='proc_bill_payment_idx'),
        ]
    
    def __str__(self):
        return self.bill_number
    
    def save(self, *args, **kwargs):
        """Auto-generate bill number and calculate amounts."""
        if not self.bill_number:
            self.bill_number = self.generate_bill_number()
        self.calculate_totals()
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_bill_number():
        """Generate unique bill number: PROC-BILL/YYYYMMDD/###"""
        from datetime import date
        today = date.today()
        date_str = today.strftime('%Y%m%d')
        
        # Get count of bills for today
        today_count = ProcedureBill.objects.filter(
            bill_date__date=today
        ).count() + 1
        
        return f"PROC-BILL/{date_str}/{today_count:03d}"
    
    def calculate_totals(self):
        """Calculate total amount from items and apply discount."""
        # Calculate total from items
        self.total_amount = sum(
            item.amount for item in self.items.all()
        )
        
        # Calculate discount amount
        if self.discount_percent > 0:
            self.discount_amount = (
                self.total_amount * self.discount_percent / Decimal('100.00')
            )
        
        # Calculate payable amount
        self.payable_amount = self.total_amount - self.discount_amount
        
        # Calculate balance
        self.balance_amount = self.payable_amount - self.received_amount
        
        # Update payment status
        if self.received_amount >= self.payable_amount:
            self.payment_status = 'paid'
            self.balance_amount = Decimal('0.00')
        elif self.received_amount > Decimal('0.00'):
            self.payment_status = 'partial'
        else:
            self.payment_status = 'unpaid'

    def record_payment(self, amount, mode='cash', details=None, user_id=None):
        """
        Record a payment for this procedure bill and create a financial transaction.

        Args:
            amount: Payment amount
            mode: Payment method (cash, card, upi, etc.)
            details: Additional payment details (dict)
            user_id: User ID who processed the payment
        """
        from apps.payments.models import Transaction, PaymentCategory
        from django.contrib.contenttypes.models import ContentType

        payment_amount = Decimal(str(amount))
        self.received_amount += payment_amount
        self.payment_mode = mode

        if details:
            self.payment_details = details

        self.calculate_totals()
        self.save()

        # Update visit payment status
        self.visit.paid_amount += payment_amount
        self.visit.update_payment_status()

        # Create financial transaction record
        try:
            # Get or create "Procedure/Test Fees" category
            category, _ = PaymentCategory.objects.get_or_create(
                name='Procedure & Test Fees',
                tenant_id=self.tenant_id,
                defaults={
                    'category_type': 'income',
                    'description': 'Revenue from procedures, tests and investigations'
                }
            )

            # Map payment mode to transaction payment method
            payment_method_mapping = {
                'cash': 'cash',
                'card': 'card',
                'upi': 'upi',
                'bank': 'net_banking',
                'multiple': 'other',
            }
            transaction_payment_method = payment_method_mapping.get(mode, 'cash')

            # Create transaction
            Transaction.objects.create(
                tenant_id=self.tenant_id,
                amount=payment_amount,
                category=category,
                transaction_type='payment',
                payment_method=transaction_payment_method,
                content_type=ContentType.objects.get_for_model(ProcedureBill),
                object_id=self.id,
                user_id=user_id,
                description=f'Procedure Bill payment - {self.bill_number} (Visit: {self.visit.visit_number})'
            )
        except Exception as e:
            # Log error but don't fail the payment recording
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Failed to create transaction for Procedure bill {self.bill_number}: {str(e)}')


class ProcedureBillItem(models.Model):
    """
    Procedure Bill Item Model - Line items in procedure bills.
    
    Individual procedures/tests listed in a procedure bill.
    """
    
    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    procedure_bill = models.ForeignKey(
        ProcedureBill,
        on_delete=models.CASCADE,
        related_name='items'
    )
    procedure = models.ForeignKey(
        ProcedureMaster,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bill_items'
    )
    
    # Item Details
    particular_name = models.CharField(
        max_length=200,
        help_text="Store name even if procedure is deleted"
    )
    note = models.TextField(blank=True)
    quantity = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)]
    )
    unit_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Quantity × Unit Charge"
    )
    item_order = models.IntegerField(
        default=0,
        help_text="Display order in bill"
    )
    
    class Meta:
        db_table = 'procedure_bill_items'
        ordering = ['item_order', 'id']
        verbose_name = 'Procedure Bill Item'
        verbose_name_plural = 'Procedure Bill Items'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'procedure_bill']),
        ]
    
    def __str__(self):
        return f"{self.particular_name} - {self.quantity} × {self.unit_charge}"
    
    def save(self, *args, **kwargs):
        """Calculate amount before saving."""
        self.amount = Decimal(str(self.quantity)) * self.unit_charge
        
        # Store procedure name
        if self.procedure and not self.particular_name:
            self.particular_name = self.procedure.name
        
        super().save(*args, **kwargs)
        
        # Recalculate bill totals
        self.procedure_bill.calculate_totals()
        self.procedure_bill.save()


class ClinicalNote(models.Model):
    """
    Clinical Note Model - Medical documentation.
    
    Stores clinical documentation including complaints,
    diagnosis, treatment plans, and prescriptions.
    """
    
    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    visit = models.OneToOneField(
        Visit,
        on_delete=models.CASCADE,
        related_name='clinical_note'
    )
    ehr_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="Electronic Health Record ID"
    )
    note_date = models.DateTimeField(auto_now_add=True)
    
    # Clinical Information
    present_complaints = models.TextField(
        blank=True,
        help_text="Patient's presenting complaints"
    )
    observation = models.TextField(
        blank=True,
        help_text="Doctor's observations"
    )
    diagnosis = models.TextField(
        blank=True,
        help_text="Clinical diagnosis"
    )
    investigation = models.TextField(
        blank=True,
        help_text="Investigations ordered"
    )
    treatment_plan = models.TextField(
        blank=True,
        help_text="Recommended treatment"
    )
    medicines_prescribed = models.JSONField(
        default=list,
        blank=True,
        help_text="List of prescribed medicines"
    )
    doctor_advice = models.TextField(
        blank=True,
        help_text="Doctor's advice to patient"
    )
    
    # Surgery/Referral
    suggested_surgery_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Name of suggested surgery if any"
    )
    suggested_surgery_reason = models.TextField(
        blank=True,
        help_text="Reason for suggesting surgery"
    )
    referred_doctor = models.ForeignKey(
        'doctors.DoctorProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_referrals',
        help_text="Doctor to whom patient is referred"
    )
    
    # Follow-up
    next_followup_date = models.DateField(
        null=True,
        blank=True,
        help_text="Next follow-up appointment date"
    )
    
    # Audit Fields
    created_by_id = models.UUIDField(null=True, blank=True, help_text="User who created the note")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'clinical_notes'
        ordering = ['-note_date']
        verbose_name = 'Clinical Note'
        verbose_name_plural = 'Clinical Notes'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'visit']),
            models.Index(fields=['visit'], name='clinical_note_visit_idx'),
            models.Index(fields=['ehr_number'], name='clinical_note_ehr_idx'),
        ]
    
    def __str__(self):
        return f"Clinical Note - {self.visit.visit_number}"


class VisitFinding(models.Model):
    """
    Visit Finding Model - Physical examination findings.
    
    Records vital signs and systemic examination findings
    during patient visits.
    """
    
    FINDING_TYPE_CHOICES = [
        ('examination', 'General Examination'),
        ('systemic', 'Systemic Examination'),
    ]
    
    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    visit = models.ForeignKey(
        Visit,
        on_delete=models.CASCADE,
        related_name='findings'
    )
    finding_date = models.DateTimeField(auto_now_add=True)
    finding_type = models.CharField(
        max_length=20,
        choices=FINDING_TYPE_CHOICES,
        default='examination'
    )
    
    # Vital Signs
    temperature = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal('90.0')),
            MaxValueValidator(Decimal('110.0'))
        ],
        help_text="Temperature in °F"
    )
    pulse = models.IntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(30),
            MaxValueValidator(300)
        ],
        help_text="Pulse rate per minute"
    )
    bp_systolic = models.IntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(50),
            MaxValueValidator(300)
        ],
        help_text="Systolic blood pressure"
    )
    bp_diastolic = models.IntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(30),
            MaxValueValidator(200)
        ],
        help_text="Diastolic blood pressure"
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal('0.5')),
            MaxValueValidator(Decimal('500.0'))
        ],
        help_text="Weight in kg"
    )
    height = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal('30.0')),
            MaxValueValidator(Decimal('300.0'))
        ],
        help_text="Height in cm"
    )
    bmi = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        editable=False,
        help_text="Body Mass Index (auto-calculated)"
    )
    spo2 = models.IntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100)
        ],
        help_text="Oxygen saturation percentage"
    )
    respiratory_rate = models.IntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(5),
            MaxValueValidator(60)
        ],
        help_text="Breaths per minute"
    )
    
    # Systemic Examination
    tongue = models.CharField(
        max_length=200,
        blank=True,
        help_text="Tongue examination findings"
    )
    throat = models.CharField(
        max_length=200,
        blank=True,
        help_text="Throat examination findings"
    )
    cns = models.CharField(
        max_length=200,
        blank=True,
        help_text="Central Nervous System findings"
    )
    rs = models.CharField(
        max_length=200,
        blank=True,
        help_text="Respiratory System findings"
    )
    cvs = models.CharField(
        max_length=200,
        blank=True,
        help_text="Cardiovascular System findings"
    )
    pa = models.CharField(
        max_length=200,
        blank=True,
        help_text="Per Abdomen findings"
    )
    
    # Audit Fields
    recorded_by_id = models.UUIDField(null=True, blank=True, help_text="User who recorded these findings")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'visit_findings'
        ordering = ['-finding_date']
        verbose_name = 'Visit Finding'
        verbose_name_plural = 'Visit Findings'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'visit']),
            models.Index(fields=['visit', '-finding_date'], name='finding_visit_date_idx'),
        ]
    
    def __str__(self):
        return f"Findings - {self.visit.visit_number}"
    
    def save(self, *args, **kwargs):
        """Calculate BMI before saving."""
        self.calculate_bmi()
        super().save(*args, **kwargs)
    
    def calculate_bmi(self):
        """Calculate BMI from height and weight."""
        if self.weight and self.height:
            # Convert height from cm to meters
            height_m = self.height / Decimal('100.0')
            # BMI = weight(kg) / height(m)²
            self.bmi = self.weight / (height_m ** 2)
            # Round to 2 decimal places
            self.bmi = round(self.bmi, 2)
    
    @property
    def blood_pressure(self):
        """Return formatted blood pressure."""
        if self.bp_systolic and self.bp_diastolic:
            return f"{self.bp_systolic}/{self.bp_diastolic}"
        return None
    
    @property
    def bmi_category(self):
        """Return BMI category."""
        if not self.bmi:
            return None
        
        if self.bmi < 18.5:
            return "Underweight"
        elif 18.5 <= self.bmi < 25:
            return "Normal"
        elif 25 <= self.bmi < 30:
            return "Overweight"
        else:
            return "Obese"


class VisitAttachment(models.Model):
    """
    Visit Attachment Model - Medical document uploads.
    
    Stores uploaded medical documents, reports, and images
    associated with visits.
    """
    
    FILE_TYPE_CHOICES = [
        ('xray', 'X-Ray'),
        ('report', 'Lab Report'),
        ('prescription', 'Prescription'),
        ('scan', 'Scan'),
        ('document', 'Document'),
        ('other', 'Other'),
    ]
    
    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    visit = models.ForeignKey(
        Visit,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(
        upload_to='opd/attachments/%Y/%m/',
        help_text="Upload medical documents"
    )
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(
        max_length=20,
        choices=FILE_TYPE_CHOICES,
        default='other'
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the attachment"
    )
    
    # Audit Fields
    uploaded_by_id = models.UUIDField(null=True, blank=True, help_text="User who uploaded this attachment")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'visit_attachments'
        ordering = ['-uploaded_at']
        verbose_name = 'Visit Attachment'
        verbose_name_plural = 'Visit Attachments'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'visit']),
            models.Index(fields=['visit'], name='attachment_visit_idx'),
            models.Index(fields=['file_type'], name='attachment_type_idx'),
        ]
    
    def __str__(self):
        return f"{self.file_name} - {self.visit.visit_number}"
    
    def save(self, *args, **kwargs):
        """Store original filename."""
        if self.file and not self.file_name:
            self.file_name = os.path.basename(self.file.name)
        super().save(*args, **kwargs)
    
    def get_file_size(self):
        """Return file size in a human-readable format."""
        if self.file:
            size = self.file.size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.2f} {unit}"
                size /= 1024.0
        return None
    
    def get_file_extension(self):
        """Return file extension."""
        if self.file:
            return os.path.splitext(self.file.name)[1].lower()
        return None


class ClinicalNoteTemplateGroup(models.Model):
    """
    Template Group Model - Organize templates into categories.

    Groups like: General Examination, Cardiology Assessment, etc.
    """

    id = models.AutoField(primary_key=True)

    # Tenant Information
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant identifier for multi-tenancy"
    )

    name = models.CharField(
        max_length=200,
        help_text="Group name (e.g., General Examination)"
    )
    description = models.TextField(blank=True)
    display_order = models.IntegerField(
        default=0,
        help_text="Order in which to display this group"
    )
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'clinical_note_template_groups'
        ordering = ['display_order', 'name']
        verbose_name = 'Clinical Note Template Group'
        verbose_name_plural = 'Clinical Note Template Groups'
        unique_together = [['tenant_id', 'name']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'is_active']),
        ]

    def __str__(self):
        return self.name


class ClinicalNoteTemplate(models.Model):
    """
    Clinical Note Template Model - Define reusable form templates.

    Each template can have multiple fields of different types.
    """

    id = models.AutoField(primary_key=True)

    # Tenant Information
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant identifier for multi-tenancy"
    )

    name = models.CharField(
        max_length=200,
        help_text="Template name (e.g., Initial Consultation Form)"
    )
    code = models.CharField(
        max_length=50,
        help_text="Unique template code"
    )
    group = models.ForeignKey(
        ClinicalNoteTemplateGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='templates'
    )
    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'clinical_note_templates'
        ordering = ['display_order', 'name']
        verbose_name = 'Clinical Note Template'
        verbose_name_plural = 'Clinical Note Templates'
        unique_together = [['tenant_id', 'code']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'is_active']),
            models.Index(fields=['code'], name='clinical_template_code_idx'),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class ClinicalNoteTemplateField(models.Model):
    """
    Template Field Model - Individual fields in a template.

    Defines the structure of each field (name, type, options, validation).
    """

    FIELD_TYPE_CHOICES = [
        ('text', 'Text (Short)'),
        ('textarea', 'Text Area (Long)'),
        ('number', 'Number'),
        ('decimal', 'Decimal'),
        ('boolean', 'Boolean (Yes/No)'),
        ('date', 'Date'),
        ('datetime', 'Date & Time'),
        ('time', 'Time'),
        ('select', 'Single Select'),
        ('multiselect', 'Multiple Select'),
        ('radio', 'Radio Buttons'),
        ('checkbox', 'Checkboxes'),
        ('image', 'Image Upload'),
        ('file', 'File Upload'),
        ('json', 'JSON Data'),
    ]

    id = models.AutoField(primary_key=True)

    # Tenant Information
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant identifier for multi-tenancy"
    )

    template = models.ForeignKey(
        ClinicalNoteTemplate,
        on_delete=models.CASCADE,
        related_name='fields'
    )

    # Field Definition
    field_name = models.CharField(
        max_length=100,
        help_text="Internal field name (use lowercase, no spaces)"
    )
    field_label = models.CharField(
        max_length=200,
        help_text="Display label for the field"
    )
    field_type = models.CharField(
        max_length=20,
        choices=FIELD_TYPE_CHOICES
    )

    # Field Configuration
    help_text = models.CharField(
        max_length=500,
        blank=True,
        help_text="Help text to display below the field"
    )
    placeholder = models.CharField(
        max_length=200,
        blank=True,
        help_text="Placeholder text for input fields"
    )
    default_value = models.TextField(
        blank=True,
        help_text="Default value for the field"
    )

    # Validation Rules
    is_required = models.BooleanField(
        default=False,
        help_text="Is this field mandatory?"
    )
    min_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum value (for number fields)"
    )
    max_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum value (for number fields)"
    )
    min_length = models.IntegerField(
        null=True,
        blank=True,
        help_text="Minimum length (for text fields)"
    )
    max_length = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum length (for text fields)"
    )

    # Display Configuration
    display_order = models.IntegerField(
        default=0,
        help_text="Order in which to display this field"
    )
    column_width = models.IntegerField(
        default=12,
        choices=[(i, f"{i}/12") for i in range(1, 13)],
        help_text="Bootstrap column width (1-12)"
    )

    # Conditional Display
    show_condition = models.JSONField(
        default=dict,
        blank=True,
        help_text="Conditions to show this field based on other fields"
    )

    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'clinical_note_template_fields'
        ordering = ['template', 'display_order', 'id']
        verbose_name = 'Clinical Note Template Field'
        verbose_name_plural = 'Clinical Note Template Fields'
        unique_together = [['template', 'field_name']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['template', 'display_order']),
        ]

    def __str__(self):
        return f"{self.template.code} - {self.field_label}"


class ClinicalNoteTemplateFieldOption(models.Model):
    """
    Field Option Model - Options for select/multiselect fields.

    Stores dropdown options, radio button options, etc.
    """

    id = models.AutoField(primary_key=True)

    # Tenant Information
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant identifier for multi-tenancy"
    )

    field = models.ForeignKey(
        ClinicalNoteTemplateField,
        on_delete=models.CASCADE,
        related_name='options'
    )

    option_value = models.CharField(
        max_length=100,
        help_text="Internal value"
    )
    option_label = models.CharField(
        max_length=200,
        help_text="Display label"
    )
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Additional metadata for options
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional data for the option"
    )

    class Meta:
        db_table = 'clinical_note_template_field_options'
        ordering = ['field', 'display_order', 'option_label']
        verbose_name = 'Template Field Option'
        verbose_name_plural = 'Template Field Options'
        unique_together = [['field', 'option_value']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['field', 'display_order']),
        ]

    def __str__(self):
        return f"{self.field.field_label} - {self.option_label}"


class ClinicalNoteTemplateResponse(models.Model):
    """
    Template Response Model - Actual filled form data.

    Links a completed template to a visit with all field responses.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('completed', 'Completed'),
        ('reviewed', 'Reviewed'),
        ('archived', 'Archived'),
    ]

    id = models.AutoField(primary_key=True)

    # Tenant Information
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant identifier for multi-tenancy"
    )

    visit = models.ForeignKey(
        Visit,
        on_delete=models.CASCADE,
        related_name='template_responses'
    )
    template = models.ForeignKey(
        ClinicalNoteTemplate,
        on_delete=models.PROTECT,
        related_name='responses'
    )

    # Response Metadata
    response_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )

    # Summary (computed from field responses)
    response_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Cached summary of all responses"
    )

    # Audit (UUID fields instead of ForeignKey to User)
    filled_by_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="User ID who filled the template"
    )
    reviewed_by_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="User ID who reviewed the template"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'clinical_note_template_responses'
        ordering = ['-response_date']
        verbose_name = 'Clinical Note Template Response'
        verbose_name_plural = 'Clinical Note Template Responses'
        unique_together = [['visit', 'template']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['visit']),
            models.Index(fields=['template']),
            models.Index(fields=['status']),
            models.Index(fields=['-response_date']),
        ]

    def __str__(self):
        return f"{self.visit.visit_number} - {self.template.name}"

    def generate_summary(self):
        """Generate a summary of all field responses."""
        summary = {}
        for field_response in self.field_responses.all():
            summary[field_response.field.field_name] = {
                'label': field_response.field.field_label,
                'value': field_response.get_display_value(),
                'type': field_response.field.field_type
            }
        self.response_summary = summary
        self.save()
        return summary


class ClinicalNoteTemplateFieldResponse(models.Model):
    """
    Field Response Model - Individual field answers.

    Stores the actual value for each field in a template response.
    """

    id = models.AutoField(primary_key=True)

    # Tenant Information
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant identifier for multi-tenancy"
    )

    response = models.ForeignKey(
        ClinicalNoteTemplateResponse,
        on_delete=models.CASCADE,
        related_name='field_responses'
    )
    field = models.ForeignKey(
        ClinicalNoteTemplateField,
        on_delete=models.CASCADE,
        related_name='responses'
    )

    # Value Storage (use appropriate field based on type)
    value_text = models.TextField(blank=True)
    value_number = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    value_boolean = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_datetime = models.DateTimeField(null=True, blank=True)
    value_time = models.TimeField(null=True, blank=True)
    value_json = models.JSONField(default=dict, blank=True)
    value_file = models.FileField(
        upload_to='clinical_notes/responses/%Y/%m/',
        null=True,
        blank=True
    )

    # For multiselect - store selected option IDs
    selected_options = models.ManyToManyField(
        ClinicalNoteTemplateFieldOption,
        blank=True,
        related_name='field_responses'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'clinical_note_template_field_responses'
        ordering = ['response', 'field__display_order']
        verbose_name = 'Template Field Response'
        verbose_name_plural = 'Template Field Responses'
        unique_together = [['response', 'field']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['response']),
        ]

    def __str__(self):
        return f"{self.response.visit.visit_number} - {self.field.field_label}"

    def get_value(self):
        """Get the value based on field type."""
        field_type = self.field.field_type

        if field_type in ['text', 'textarea']:
            return self.value_text
        elif field_type in ['number', 'decimal']:
            return self.value_number
        elif field_type == 'boolean':
            return self.value_boolean
        elif field_type == 'date':
            return self.value_date
        elif field_type == 'datetime':
            return self.value_datetime
        elif field_type == 'time':
            return self.value_time
        elif field_type == 'json':
            return self.value_json
        elif field_type in ['image', 'file']:
            return self.value_file.url if self.value_file else None
        elif field_type in ['select', 'radio']:
            # Return single selected option
            option = self.selected_options.first()
            return option.option_value if option else None
        elif field_type in ['multiselect', 'checkbox']:
            # Return list of selected options
            return list(self.selected_options.values_list('option_value', flat=True))

        return None

    def get_display_value(self):
        """Get human-readable display value."""
        field_type = self.field.field_type

        if field_type in ['select', 'radio']:
            option = self.selected_options.first()
            return option.option_label if option else None
        elif field_type in ['multiselect', 'checkbox']:
            return list(self.selected_options.values_list('option_label', flat=True))
        elif field_type == 'boolean':
            return 'Yes' if self.value_boolean else 'No' if self.value_boolean is False else None

        return self.get_value()

    def set_value(self, value):
        """Set the value based on field type."""
        field_type = self.field.field_type

        if field_type in ['text', 'textarea']:
            self.value_text = str(value) if value else ''
        elif field_type in ['number', 'decimal']:
            self.value_number = Decimal(str(value)) if value else None
        elif field_type == 'boolean':
            self.value_boolean = bool(value) if value is not None else None
        elif field_type == 'date':
            self.value_date = value
        elif field_type == 'datetime':
            self.value_datetime = value
        elif field_type == 'time':
            self.value_time = value
        elif field_type == 'json':
            self.value_json = value if isinstance(value, dict) else {}
        elif field_type in ['image', 'file']:
            self.value_file = value

        self.save()