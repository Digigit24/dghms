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