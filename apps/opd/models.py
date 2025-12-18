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
    
    def record_payment(self, amount, mode='cash', details=None):
        """Record a payment for this bill."""
        self.received_amount += Decimal(str(amount))
        self.payment_mode = mode
        
        if details:
            self.payment_details = details
        
        self.calculate_totals()
        self.save()
        
        # Update visit payment status
        self.visit.paid_amount += Decimal(str(amount))
        self.visit.update_payment_status()


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
    
    def record_payment(self, amount, mode='cash', details=None):
        """Record a payment for this bill."""
        self.received_amount += Decimal(str(amount))
        self.payment_mode = mode
        
        if details:
            self.payment_details = details
        
        self.calculate_totals()
        self.save()
        
        # Update visit payment status
        self.visit.paid_amount += Decimal(str(amount))
        self.visit.update_payment_status()


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
    Supports multiple doctors filling same template on same visit via response_sequence.
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

    # Multiple Doctor Support
    response_sequence = models.IntegerField(
        default=1,
        help_text="Sequence number for multiple responses (1st, 2nd, 3rd fill of same template on same visit)"
    )
    original_assigned_doctor_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="User ID of originally assigned doctor (tracks who was first assigned)"
    )
    doctor_switched_reason = models.TextField(
        blank=True,
        help_text="Reason for doctor change (absence, handover, specialty consultation, etc.)"
    )

    # Response Metadata
    response_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )

    # Review Workflow
    is_reviewed = models.BooleanField(
        default=False,
        help_text="Has this response been reviewed/approved by supervising doctor"
    )

    # Canvas Integration for Stylus Input
    canvas_data = models.FileField(
        upload_to='clinical_notes/canvas/%Y/%m/',
        null=True,
        blank=True,
        help_text="Canvas image if doctor used stylus instead of structured input"
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
        unique_together = [['visit', 'template', 'response_sequence']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['visit']),
            models.Index(fields=['template']),
            models.Index(fields=['status']),
            models.Index(fields=['-response_date']),
            models.Index(fields=['visit', 'template', 'response_sequence']),
            models.Index(fields=['original_assigned_doctor_id']),
            models.Index(fields=['is_reviewed']),
        ]

    def __str__(self):
        return f"{self.visit.visit_number} - {self.template.name} (Seq: {self.response_sequence})"

    def save(self, *args, **kwargs):
        """Auto-calculate response_sequence if not set."""
        if not self.response_sequence:
            # Get max sequence for this visit + template combination
            max_seq = ClinicalNoteTemplateResponse.objects.filter(
                visit=self.visit,
                template=self.template
            ).aggregate(models.Max('response_sequence'))['response_sequence__max']
            self.response_sequence = (max_seq or 0) + 1
        super().save(*args, **kwargs)

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

    @classmethod
    def create_with_doctor_switch(cls, visit, template, current_doctor_id, original_doctor_id=None, switch_reason='', **kwargs):
        """
        Create a new response with doctor switch tracking.

        Args:
            visit: Visit instance
            template: ClinicalNoteTemplate instance
            current_doctor_id: UUID of current doctor filling this
            original_doctor_id: UUID of originally assigned doctor (optional)
            switch_reason: Reason for doctor change
            **kwargs: Additional fields for the response

        Returns:
            ClinicalNoteTemplateResponse instance
        """
        response = cls(
            visit=visit,
            template=template,
            filled_by_id=current_doctor_id,
            original_assigned_doctor_id=original_doctor_id or current_doctor_id,
            doctor_switched_reason=switch_reason,
            tenant_id=visit.tenant_id,
            **kwargs
        )
        response.save()
        return response

    def clone_from_template(self, response_template):
        """
        Clone field values from a saved ResponseTemplate (copy-paste template).

        Args:
            response_template: ClinicalNoteResponseTemplate instance

        Returns:
            List of created ClinicalNoteTemplateFieldResponse instances
        """
        from decimal import Decimal
        from django.utils import timezone

        field_responses = []
        template_values = response_template.template_field_values or {}

        for field_name, field_data in template_values.items():
            try:
                # Find the field in current template
                field = self.template.fields.get(field_name=field_name)

                # Create field response
                field_response = ClinicalNoteTemplateFieldResponse(
                    response=self,
                    field=field,
                    tenant_id=self.tenant_id
                )

                # Set value based on type
                field_type = field_data.get('type')
                value = field_data.get('value')

                if field_type in ['text', 'textarea']:
                    field_response.value_text = value or ''
                elif field_type in ['number', 'decimal']:
                    field_response.value_number = Decimal(str(value)) if value else None
                elif field_type == 'boolean':
                    field_response.value_boolean = bool(value) if value is not None else None
                elif field_type == 'date':
                    field_response.value_date = value
                elif field_type == 'datetime':
                    field_response.value_datetime = value
                elif field_type == 'time':
                    field_response.value_time = value
                elif field_type == 'json':
                    field_response.value_json = value if isinstance(value, dict) else {}

                field_response.save()

                # Handle multiselect options
                if field_type in ['select', 'radio', 'multiselect', 'checkbox'] and value:
                    option_ids = value if isinstance(value, list) else [value]
                    field_response.selected_options.set(option_ids)

                field_responses.append(field_response)

            except ClinicalNoteTemplateField.DoesNotExist:
                continue  # Skip if field no longer exists in template

        # Regenerate summary
        self.generate_summary()

        return field_responses

    def convert_to_reusable_template(self, template_name, description='', created_by_id=None):
        """
        Convert current response into a reusable template for copy-paste.

        Args:
            template_name: Name for the reusable template
            description: Description of what this template is for
            created_by_id: UUID of user creating this template

        Returns:
            ClinicalNoteResponseTemplate instance
        """
        # Collect all field values
        template_field_values = {}
        for field_response in self.field_responses.all():
            field_name = field_response.field.field_name
            template_field_values[field_name] = {
                'label': field_response.field.field_label,
                'type': field_response.field.field_type,
                'value': field_response.get_value()
            }

        # Create reusable template
        response_template = ClinicalNoteResponseTemplate(
            name=template_name,
            description=description,
            source_response=self,
            template_field_values=template_field_values,
            created_by_id=created_by_id or self.filled_by_id,
            tenant_id=self.tenant_id
        )
        response_template.save()

        return response_template

    def compare_with_response(self, other_response):
        """
        Compare this response with another response for the same visit/template.

        Args:
            other_response: Another ClinicalNoteTemplateResponse instance

        Returns:
            dict: Comparison showing what changed between responses
        """
        if self.visit != other_response.visit or self.template != other_response.template:
            raise ValueError("Can only compare responses from same visit and template")

        comparison = {
            'metadata': {
                'response_1': {
                    'sequence': self.response_sequence,
                    'filled_by_id': str(self.filled_by_id),
                    'filled_at': self.response_date.isoformat() if self.response_date else None,
                    'status': self.status,
                },
                'response_2': {
                    'sequence': other_response.response_sequence,
                    'filled_by_id': str(other_response.filled_by_id),
                    'filled_at': other_response.response_date.isoformat() if other_response.response_date else None,
                    'status': other_response.status,
                }
            },
            'field_changes': []
        }

        # Compare field responses
        self_fields = {fr.field.field_name: fr for fr in self.field_responses.all()}
        other_fields = {fr.field.field_name: fr for fr in other_response.field_responses.all()}

        all_field_names = set(self_fields.keys()) | set(other_fields.keys())

        for field_name in all_field_names:
            self_fr = self_fields.get(field_name)
            other_fr = other_fields.get(field_name)

            self_value = self_fr.get_display_value() if self_fr else None
            other_value = other_fr.get_display_value() if other_fr else None

            if self_value != other_value:
                comparison['field_changes'].append({
                    'field_name': field_name,
                    'field_label': (self_fr or other_fr).field.field_label,
                    'response_1_value': self_value,
                    'response_2_value': other_value,
                    'changed': True
                })

        return comparison


class ClinicalNoteTemplateFieldResponse(models.Model):
    """
    Field Response Model - Individual field answers.

    Stores the actual value for each field in a template response.
    Supports both keyboard input and stylus/canvas input.
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

    # Canvas/Stylus Input Support
    full_canvas_json = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        help_text="Full Excalidraw JSON data for the canvas."
    )
    canvas_thumbnail = models.ImageField(
        upload_to='canvas_thumbnails/%Y/%m/',
        null=True,
        blank=True,
        help_text="Auto-generated thumbnail of the canvas."
    )
    canvas_version_history = models.JSONField(
        default=list,
        blank=True,
        null=True,
        help_text="History of previous canvas JSON states."
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

    def save(self, *args, **kwargs):
        # Track changes to full_canvas_json for version history
        if self.pk is not None:
            try:
                orig = ClinicalNoteTemplateFieldResponse.objects.get(pk=self.pk)
                if orig.full_canvas_json != self.full_canvas_json and orig.full_canvas_json:
                    if self.canvas_version_history is None:
                        self.canvas_version_history = []
                    self.canvas_version_history.append(orig.full_canvas_json)
            except ClinicalNoteTemplateFieldResponse.DoesNotExist:
                pass

        # TODO: Implement thumbnail generation from full_canvas_json.
        # This requires a library to convert Excalidraw JSON to an image (e.g., SVG or PNG).
        # For example, using a Node.js script with @excalidraw/excalidraw-node
        # or a Python library if one becomes available.
        #
        # from django.core.files.base import ContentFile
        # if self.full_canvas_json and 'elements' in self.full_canvas_json:
        #     try:
        #         image_data = generate_thumbnail_from_json(self.full_canvas_json)
        #         self.canvas_thumbnail.save(f'{self.id}_thumbnail.png', ContentFile(image_data), save=False)
        #     except Exception as e:
        #         # Handle thumbnail generation failure
        #         print(f"Could not generate thumbnail for {self.id}: {e}")

        super().save(*args, **kwargs)

    def get_value(self):
        """Get the value based on field type."""
        field_type = self.field.field_type

        if self.full_canvas_json:
            return self.full_canvas_json

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

        if self.full_canvas_json:
            return f"Canvas Data (Thumbnail: {self.canvas_thumbnail.url if self.canvas_thumbnail else 'Not generated'})"

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
        elif field_type in ['select', 'radio']:
            # For single select, save first then set selected option
            self.save()
            if value:
                # value should be a single option ID
                option_id = value if isinstance(value, (int, str)) else value[0] if isinstance(value, list) else None
                if option_id:
                    self.selected_options.set([option_id])
            return
        elif field_type in ['multiselect', 'checkbox']:
            # For multiple select, save first then set selected options
            self.save()
            if value:
                # value should be a list of option IDs
                option_ids = value if isinstance(value, list) else [value]
                self.selected_options.set(option_ids)
            else:
                self.selected_options.clear()
            return

        self.save()


class ClinicalNoteResponseTemplate(models.Model):
    """
    Clinical Note Response Template Model - Reusable copy-paste templates.

    Allows doctors to save frequently used clinical note patterns as templates
    for quick reuse. For example, a doctor can save a "Standard Follow-up Pattern"
    template with common field values and reuse it for similar cases.

    This is different from ClinicalNoteTemplate which defines the structure/fields,
    while this model stores pre-filled values for quick copy-paste.
    """

    id = models.AutoField(primary_key=True)

    # Tenant Information
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant identifier for multi-tenancy"
    )

    # Template Information
    name = models.CharField(
        max_length=200,
        help_text="User-defined template name (e.g., 'Standard Follow-up', 'Initial Diabetes Consultation')"
    )
    description = models.TextField(
        blank=True,
        help_text="What this response template is for (e.g., 'Standard pattern for diabetes follow-ups')"
    )

    # Source Response
    source_response = models.ForeignKey(
        ClinicalNoteTemplateResponse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='derived_templates',
        help_text="Original response this template was created from"
    )

    # Template Data
    template_field_values = models.JSONField(
        default=dict,
        help_text="Stores cloned field responses for quick reuse. Format: {field_name: {label, type, value}}"
    )

    # Metadata
    is_active = models.BooleanField(
        default=True,
        help_text="Can be archived/deactivated"
    )
    usage_count = models.IntegerField(
        default=0,
        help_text="Number of times this template has been used"
    )

    # Audit
    created_by_id = models.UUIDField(
        db_index=True,
        help_text="User ID of doctor who created this reusable template"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'clinical_note_response_templates'
        ordering = ['-usage_count', '-created_at']
        verbose_name = 'Clinical Note Response Template'
        verbose_name_plural = 'Clinical Note Response Templates'
        unique_together = [['tenant_id', 'name', 'created_by_id']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'is_active']),
            models.Index(fields=['created_by_id']),
            models.Index(fields=['-usage_count']),
        ]

    def __str__(self):
        return f"{self.name} (by User: {self.created_by_id})"

    def apply_to_response(self, clinical_response):
        """
        Apply this template's values to a ClinicalNoteTemplateResponse.

        This is a convenience method that calls clone_from_template on the response.

        Args:
            clinical_response: ClinicalNoteTemplateResponse instance to populate

        Returns:
            List of created ClinicalNoteTemplateFieldResponse instances
        """
        field_responses = clinical_response.clone_from_template(self)

        # Increment usage count
        self.usage_count += 1
        self.save(update_fields=['usage_count', 'updated_at'])

        return field_responses

    def update_field_values(self, field_values_dict):
        """
        Update the template field values.

        Args:
            field_values_dict: Dictionary of field values to update
                Format: {field_name: {label, type, value}}
        """
        self.template_field_values.update(field_values_dict)
        self.save(update_fields=['template_field_values', 'updated_at'])

    def get_field_value(self, field_name):
        """
        Get a specific field value from the template.

        Args:
            field_name: Name of the field

        Returns:
            Field value dict or None if not found
        """
        return self.template_field_values.get(field_name)

    def clone(self, new_name, created_by_id=None):
        """
        Clone this template with a new name.

        Args:
            new_name: Name for the cloned template
            created_by_id: UUID of user creating the clone (defaults to original creator)

        Returns:
            New ClinicalNoteResponseTemplate instance
        """
        cloned_template = ClinicalNoteResponseTemplate(
            tenant_id=self.tenant_id,
            name=new_name,
            description=f"Cloned from: {self.name}",
            source_response=self.source_response,
            template_field_values=self.template_field_values.copy(),
            created_by_id=created_by_id or self.created_by_id
        )
        cloned_template.save()
        return cloned_template