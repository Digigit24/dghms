# diagnostics/models.py
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils import timezone
from common.mixins import TenantModelMixin, EncounterMixin

class Investigation(TenantModelMixin):
    """
    Investigation Model - Master test list (Name, Code, Category, Base Charge).
    """
    CATEGORY_CHOICES = [
        ('laboratory', 'Laboratory'),
        ('radiology', 'Radiology'),
        ('pathology', 'Pathology'),
        ('cardiology', 'Cardiology'),
        ('ultrasound', 'Ultrasound'),
        ('ct_scan', 'CT Scan'),
        ('mri', 'MRI'),
        ('xray', 'X-Ray'),
        ('other', 'Other'),
    ]

    name = models.CharField(
        max_length=200,
        help_text="Test name (e.g., 'Complete Blood Count', 'Chest X-Ray')"
    )
    code = models.CharField(
        max_length=50,
        help_text="Unique test code (e.g., 'CBC', 'CXR')"
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='laboratory'
    )
    base_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Base charge for this test"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'diag_investigations'
        verbose_name = 'Investigation'
        verbose_name_plural = 'Investigations'
        unique_together = [['tenant_id', 'code']]
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.code} - {self.name}"

class Requisition(TenantModelMixin, EncounterMixin):
    """
    Requisition Model - Inherits from EncounterMixin.
    Fields: patient (FK), requesting_doctor_id (UUID), status, priority.
    """
    REQUISITION_TYPE_CHOICES = [
        ('investigation', 'Investigation'),
        ('medicine', 'Medicine'),
        ('procedure', 'Procedure'),
        ('package', 'Package'),
    ]

    STATUS_CHOICES = [
        ('ordered', 'Ordered'),
        ('sample_collected', 'Sample Collected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('routine', 'Routine'),
        ('urgent', 'Urgent'),
        ('stat', 'STAT (Immediate)'),
    ]

    requisition_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text="Unique requisition identifier"
    )

    requisition_type = models.CharField(
        max_length=20,
        choices=REQUISITION_TYPE_CHOICES,
        default='investigation',
        help_text="Type of requisition: investigation, medicine, procedure, or package"
    )

    patient = models.ForeignKey(
        'patients.PatientProfile',
        on_delete=models.PROTECT,
        related_name='requisitions'
    )
    requesting_doctor_id = models.UUIDField(
        db_index=True,
        help_text="SuperAdmin User ID of doctor who ordered the test"
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ordered'
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='routine'
    )
    
    order_date = models.DateTimeField(auto_now_add=True)
    clinical_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'diag_requisitions'
        verbose_name = 'Requisition'
        verbose_name_plural = 'Requisitions'
        ordering = ['-order_date']

    def __str__(self):
        return f"REQ {self.requisition_number or self.id} - {self.patient}"

    def save(self, *args, **kwargs):
        if not self.requisition_number:
            self.requisition_number = self.generate_requisition_number()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_requisition_number():
        from datetime import date
        today = date.today()
        date_str = today.strftime('%Y%m%d')
        # Simple random or count based logic could be better, here we use a simple timestamp/random approach or just count
        # For simplicity in this context, let's assume a count based on date is enough or let DB handle if we used a sequence.
        # But since we need a string:
        import uuid
        return f"REQ-{date_str}-{uuid.uuid4().hex[:6].upper()}"

    @property
    def billing_target(self):
        """
        Identifies the "Billing Target."
        If the encounter is a Visit, charges go to OPDBilling.
        If it's an Admission, charges go to IPDBillItem.
        """
        if self.content_type.model == 'visit':
            return 'OPDBilling'
        elif self.content_type.model == 'admission':
            return 'IPDBillItem'
        return None

class DiagnosticOrder(TenantModelMixin):
    """
    DiagnosticOrder: Links Requisition to Investigation.
    Tracks individual test status and sample_id.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sample_collected', 'Sample Collected'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    requisition = models.ForeignKey(
        Requisition,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    investigation = models.ForeignKey(
        Investigation,
        on_delete=models.PROTECT,
        related_name='orders'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    sample_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Barcode or ID of the sample"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # GenericForeignKey to link to OPDBillItem or IPDBillItem
    bill_item_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Type of bill item (OPDBillItem or IPDBillItem)",
        related_name='+'
    )
    bill_item_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the bill item"
    )
    bill_item_link = GenericForeignKey('bill_item_content_type', 'bill_item_object_id')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'diag_orders'
        verbose_name = 'Diagnostic Order'
        verbose_name_plural = 'Diagnostic Orders'
        indexes = [
            models.Index(fields=['bill_item_content_type', 'bill_item_object_id']),
        ]

    def __str__(self):
        return f"{self.investigation.name} ({self.status})"
    
    def save(self, *args, **kwargs):
        if not self.price and self.investigation:
            self.price = self.investigation.base_charge
        super().save(*args, **kwargs)

class MedicineOrder(TenantModelMixin):
    """
    MedicineOrder: Links Requisition to PharmacyProduct.
    Tracks medicine orders with quantity and price.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('dispensed', 'Dispensed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    requisition = models.ForeignKey(
        Requisition,
        on_delete=models.CASCADE,
        related_name='medicine_orders'
    )
    product = models.ForeignKey(
        'pharmacy.PharmacyProduct',
        on_delete=models.PROTECT,
        related_name='medicine_orders'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Quantity of medicine ordered"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # GenericForeignKey to link to OPDBillItem or IPDBillItem
    bill_item_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Type of bill item (OPDBillItem or IPDBillItem)",
        related_name='+'
    )
    bill_item_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the bill item"
    )
    bill_item_link = GenericForeignKey('bill_item_content_type', 'bill_item_object_id')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'diag_medicine_orders'
        verbose_name = 'Medicine Order'
        verbose_name_plural = 'Medicine Orders'
        indexes = [
            models.Index(fields=['bill_item_content_type', 'bill_item_object_id']),
        ]

    def __str__(self):
        return f"{self.product.product_name} x{self.quantity} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.price and self.product:
            self.price = self.product.selling_price or self.product.mrp
        super().save(*args, **kwargs)

class ProcedureOrder(TenantModelMixin):
    """
    ProcedureOrder: Links Requisition to ProcedureMaster.
    Tracks procedure orders with quantity and price.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    requisition = models.ForeignKey(
        Requisition,
        on_delete=models.CASCADE,
        related_name='procedure_orders'
    )
    procedure = models.ForeignKey(
        'opd.ProcedureMaster',
        on_delete=models.PROTECT,
        related_name='procedure_orders'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Number of times procedure is to be performed"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # GenericForeignKey to link to OPDBillItem or IPDBillItem
    bill_item_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Type of bill item (OPDBillItem or IPDBillItem)",
        related_name='+'
    )
    bill_item_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the bill item"
    )
    bill_item_link = GenericForeignKey('bill_item_content_type', 'bill_item_object_id')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'diag_procedure_orders'
        verbose_name = 'Procedure Order'
        verbose_name_plural = 'Procedure Orders'
        indexes = [
            models.Index(fields=['bill_item_content_type', 'bill_item_object_id']),
        ]

    def __str__(self):
        return f"{self.procedure.name} x{self.quantity} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.price and self.procedure:
            self.price = self.procedure.default_charge
        super().save(*args, **kwargs)

class PackageOrder(TenantModelMixin):
    """
    PackageOrder: Links Requisition to ProcedurePackage.
    Tracks package orders with quantity and price.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    requisition = models.ForeignKey(
        Requisition,
        on_delete=models.CASCADE,
        related_name='package_orders'
    )
    package = models.ForeignKey(
        'opd.ProcedurePackage',
        on_delete=models.PROTECT,
        related_name='package_orders'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Number of packages ordered"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # GenericForeignKey to link to OPDBillItem or IPDBillItem
    bill_item_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Type of bill item (OPDBillItem or IPDBillItem)",
        related_name='+'
    )
    bill_item_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the bill item"
    )
    bill_item_link = GenericForeignKey('bill_item_content_type', 'bill_item_object_id')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'diag_package_orders'
        verbose_name = 'Package Order'
        verbose_name_plural = 'Package Orders'
        indexes = [
            models.Index(fields=['bill_item_content_type', 'bill_item_object_id']),
        ]

    def __str__(self):
        return f"{self.package.name} x{self.quantity} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.price and self.package:
            self.price = self.package.discounted_charge
        super().save(*args, **kwargs)

class LabReport(TenantModelMixin):
    """
    LabReport: Links to DiagnosticOrder. 
    Fields: result_data (JSON), attachment, technician_id, verified_by.
    """
    diagnostic_order = models.OneToOneField(
        DiagnosticOrder,
        on_delete=models.CASCADE,
        related_name='report'
    )
    result_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured result data"
    )
    attachment = models.FileField(
        upload_to='diagnostics/reports/%Y/%m/',
        null=True,
        blank=True
    )
    technician_id = models.UUIDField(
        null=True, 
        blank=True,
        help_text="User ID of the technician who entered results"
    )
    verified_by = models.UUIDField(
        null=True, 
        blank=True,
        help_text="User ID of the doctor/pathologist who verified results"
    )
    
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'diag_lab_reports'
        verbose_name = 'Lab Report'
        verbose_name_plural = 'Lab Reports'

    def __str__(self):
        return f"Report for {self.diagnostic_order}"

class InvestigationRange(TenantModelMixin):
    """
    InvestigationRange: Reference values (Min/Max/Unit) for tests.
    """
    investigation = models.ForeignKey(
        Investigation,
        on_delete=models.CASCADE,
        related_name='ranges'
    )
    gender = models.CharField(
        max_length=20,
        choices=[('Male', 'Male'), ('Female', 'Female'), ('Any', 'Any')],
        default='Any'
    )
    min_age = models.IntegerField(default=0, help_text="Minimum age in years")
    max_age = models.IntegerField(default=120, help_text="Maximum age in years")
    
    min_value = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    max_value = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    unit = models.CharField(max_length=50, blank=True)
    
    text_reference = models.TextField(
        blank=True, 
        help_text="Textual reference range if numerical is not applicable"
    )

    class Meta:
        db_table = 'diag_investigation_ranges'
        verbose_name = 'Investigation Range'
        verbose_name_plural = 'Investigation Ranges'

    def __str__(self):
        return f"{self.investigation.name} Range"