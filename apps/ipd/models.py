# ipd/models.py
from django.db import models
from django.contrib.contenttypes.fields import GenericRelation
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from django.utils import timezone


class Ward(models.Model):
    """
    Ward Model - Physical ward/unit in the hospital.

    Defines different wards like General, ICU, Private rooms, etc.
    """

    WARD_TYPE_CHOICES = [
        ('general', 'General Ward'),
        ('icu', 'ICU'),
        ('private', 'Private'),
        ('semi_private', 'Semi-Private'),
        ('deluxe', 'Deluxe'),
        ('nicu', 'NICU'),
        ('picu', 'PICU'),
        ('emergency', 'Emergency'),
        ('maternity', 'Maternity'),
        ('pediatric', 'Pediatric'),
        ('surgical', 'Surgical'),
        ('other', 'Other'),
    ]

    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    name = models.CharField(
        max_length=200,
        help_text="Ward name (e.g., 'General Ward A', 'ICU Floor 3')"
    )
    type = models.CharField(
        max_length=20,
        choices=WARD_TYPE_CHOICES,
        default='general'
    )
    floor = models.CharField(
        max_length=50,
        blank=True,
        help_text="Floor/location (e.g., 'Ground Floor', '3rd Floor')"
    )
    total_beds = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ipd_wards'
        ordering = ['floor', 'name']
        verbose_name = 'IPD Ward'
        verbose_name_plural = 'IPD Wards'
        unique_together = [['tenant_id', 'name']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'is_active']),
            models.Index(fields=['type']),
        ]

    def __str__(self):
        return f"{self.name} ({self.type})"

    def get_available_beds_count(self):
        """Return count of available (unoccupied) beds."""
        return self.beds.filter(is_occupied=False, is_active=True).count()

    def get_occupied_beds_count(self):
        """Return count of occupied beds."""
        return self.beds.filter(is_occupied=True).count()


class Bed(models.Model):
    """
    Bed Model - Individual bed in a ward.

    Tracks bed availability, type, and daily charges.
    """

    BED_TYPE_CHOICES = [
        ('general', 'General Bed'),
        ('icu', 'ICU Bed'),
        ('ventilator', 'Ventilator Bed'),
        ('private', 'Private Bed'),
        ('semi_private', 'Semi-Private Bed'),
        ('deluxe', 'Deluxe Bed'),
        ('cabin', 'Cabin'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('maintenance', 'Under Maintenance'),
        ('reserved', 'Reserved'),
        ('cleaning', 'Cleaning'),
    ]

    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    ward = models.ForeignKey(
        Ward,
        on_delete=models.CASCADE,
        related_name='beds'
    )
    bed_number = models.CharField(
        max_length=50,
        help_text="Bed number/identifier (e.g., 'A-101', 'ICU-05')"
    )
    bed_type = models.CharField(
        max_length=20,
        choices=BED_TYPE_CHOICES,
        default='general'
    )
    daily_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Daily charge for this bed"
    )
    is_occupied = models.BooleanField(
        default=False,
        help_text="Whether bed is currently occupied"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='available'
    )
    is_active = models.BooleanField(default=True)

    # Additional Features
    has_oxygen = models.BooleanField(default=False)
    has_ventilator = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ipd_beds'
        ordering = ['ward', 'bed_number']
        verbose_name = 'IPD Bed'
        verbose_name_plural = 'IPD Beds'
        unique_together = [['tenant_id', 'ward', 'bed_number']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'is_occupied']),
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['ward', 'is_occupied']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.ward.name} - {self.bed_number}"

    def mark_occupied(self):
        """Mark bed as occupied."""
        self.is_occupied = True
        self.status = 'occupied'
        self.save(update_fields=['is_occupied', 'status', 'updated_at'])

    def mark_available(self):
        """Mark bed as available."""
        self.is_occupied = False
        self.status = 'available'
        self.save(update_fields=['is_occupied', 'status', 'updated_at'])


class Admission(models.Model):
    """
    Admission Model - IPD admission records.

    Core IPD record, equivalent to OPD Visit.
    Tracks patient admission, ward, bed, and discharge information.
    """

    STATUS_CHOICES = [
        ('admitted', 'Admitted'),
        ('discharged', 'Discharged'),
        ('transferred', 'Transferred'),
        ('absconded', 'Absconded'),
        ('referred', 'Referred'),
        ('death', 'Death'),
    ]

    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    admission_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique admission identifier (e.g., IPD/20231223/001)"
    )

    # Patient and Doctor References
    patient = models.ForeignKey(
        'patients.PatientProfile',
        on_delete=models.PROTECT,
        related_name='ipd_admissions'
    )
    doctor_id = models.UUIDField(
        db_index=True,
        help_text="SuperAdmin User ID of attending doctor"
    )

    # Ward and Bed
    ward = models.ForeignKey(
        Ward,
        on_delete=models.PROTECT,
        related_name='admissions'
    )
    bed = models.ForeignKey(
        Bed,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='admissions',
        help_text="Current bed assignment"
    )

    # Admission Information
    admission_date = models.DateTimeField(
        default=timezone.now,
        help_text="Date and time of admission"
    )
    reason = models.TextField(
        help_text="Reason for admission"
    )
    provisional_diagnosis = models.TextField(
        blank=True,
        help_text="Initial diagnosis at admission"
    )
    final_diagnosis = models.TextField(
        blank=True,
        help_text="Final diagnosis at discharge"
    )

    # Discharge Information
    discharge_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date and time of discharge"
    )
    discharge_summary = models.TextField(
        blank=True,
        help_text="Discharge summary and instructions"
    )
    discharge_type = models.CharField(
        max_length=100,
        blank=True,
        help_text="Type of discharge (e.g., 'Normal', 'Against Medical Advice')"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='admitted'
    )

    # Audit Fields
    created_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="User who created this admission record"
    )
    discharged_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="User who discharged the patient"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Generic Relation for ClinicalNoteTemplateResponse and other encounter-based models
    template_responses = GenericRelation(
        'opd.ClinicalNoteTemplateResponse',
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='admission'
    )

    class Meta:
        db_table = 'ipd_admissions'
        ordering = ['-admission_date']
        verbose_name = 'IPD Admission'
        verbose_name_plural = 'IPD Admissions'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['tenant_id', 'admission_date']),
            models.Index(fields=['admission_id'], name='ipd_admission_id_idx'),
            models.Index(fields=['patient', 'admission_date'], name='ipd_patient_date_idx'),
            models.Index(fields=['doctor_id', 'admission_date'], name='ipd_doctor_date_idx'),
            models.Index(fields=['status'], name='ipd_status_idx'),
        ]

    def __str__(self):
        return f"{self.admission_id} - {self.patient}"

    def save(self, *args, **kwargs):
        """Auto-generate admission_id if not set and handle bed occupancy."""
        if not self.admission_id:
            self.admission_id = self.generate_admission_id()

        is_new = self.pk is None

        super().save(*args, **kwargs)

        # Mark bed as occupied on new admission
        if is_new and self.bed and self.status == 'admitted':
            self.bed.mark_occupied()

    @staticmethod
    def generate_admission_id():
        """Generate unique admission ID: IPD/YYYYMMDD/###"""
        from datetime import date
        today = date.today()
        date_str = today.strftime('%Y%m%d')

        # Get count of admissions for today
        today_count = Admission.objects.filter(
            admission_date__date=today
        ).count() + 1

        return f"IPD/{date_str}/{today_count:03d}"

    def calculate_length_of_stay(self):
        """Calculate length of stay in days."""
        if self.discharge_date:
            delta = self.discharge_date - self.admission_date
            return delta.days
        else:
            delta = timezone.now() - self.admission_date
            return delta.days

    def discharge(self, discharge_type='Normal', discharge_summary='', discharged_by_user_id=None):
        """Discharge the patient and release the bed."""
        self.status = 'discharged'
        self.discharge_date = timezone.now()
        self.discharge_type = discharge_type
        self.discharge_summary = discharge_summary
        self.discharged_by_user_id = discharged_by_user_id
        self.save()

        # Release bed
        if self.bed:
            self.bed.mark_available()


class BedTransfer(models.Model):
    """
    Bed Transfer Model - Track bed transfers within hospital.

    Records when a patient is moved from one bed to another,
    important for accurate billing and bed management.
    """

    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    admission = models.ForeignKey(
        Admission,
        on_delete=models.CASCADE,
        related_name='bed_transfers'
    )
    from_bed = models.ForeignKey(
        Bed,
        on_delete=models.PROTECT,
        related_name='transfers_from',
        help_text="Original bed"
    )
    to_bed = models.ForeignKey(
        Bed,
        on_delete=models.PROTECT,
        related_name='transfers_to',
        help_text="New bed"
    )

    transfer_date = models.DateTimeField(
        default=timezone.now,
        help_text="Date and time of transfer"
    )
    reason = models.TextField(
        help_text="Reason for bed transfer"
    )
    performed_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="User who performed the transfer"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ipd_bed_transfers'
        ordering = ['-transfer_date']
        verbose_name = 'IPD Bed Transfer'
        verbose_name_plural = 'IPD Bed Transfers'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['admission', '-transfer_date']),
            models.Index(fields=['transfer_date']),
        ]

    def __str__(self):
        return f"{self.admission.admission_id} - {self.from_bed} to {self.to_bed}"

    def save(self, *args, **kwargs):
        """Handle bed status updates on transfer."""
        is_new = self.pk is None

        super().save(*args, **kwargs)

        if is_new:
            # Release old bed
            self.from_bed.mark_available()

            # Occupy new bed
            self.to_bed.mark_occupied()

            # Update admission's current bed
            self.admission.bed = self.to_bed
            self.admission.save(update_fields=['bed', 'updated_at'])


class IPDBilling(models.Model):
    """
    IPD Billing Model - Consolidated billing for IPD admissions.

    Summarizes all charges including bed charges, diagnostics, pharmacy, etc.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    admission = models.OneToOneField(
        Admission,
        on_delete=models.CASCADE,
        related_name='billing',
        primary_key=True
    )
    bill_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique bill identifier (e.g., IPD-BILL/20231223/001)"
    )
    bill_date = models.DateTimeField(auto_now_add=True)

    # Financial Details
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total bill amount"
    )
    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total discount amount"
    )
    tax = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Tax amount"
    )
    paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Amount paid so far"
    )
    balance_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Balance/due amount"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # Audit Fields
    created_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="User who created this bill"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ipd_billings'
        ordering = ['-bill_date']
        verbose_name = 'IPD Billing'
        verbose_name_plural = 'IPD Billings'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['bill_number'], name='ipd_bill_number_idx'),
            models.Index(fields=['status'], name='ipd_bill_status_idx'),
        ]

    def __str__(self):
        return f"{self.bill_number} - {self.admission.admission_id}"

    def save(self, *args, **kwargs):
        """Auto-generate bill number and calculate totals."""
        if not self.bill_number:
            self.bill_number = self.generate_bill_number()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_bill_number():
        """Generate unique bill number: IPD-BILL/YYYYMMDD/###"""
        from datetime import date
        today = date.today()
        date_str = today.strftime('%Y%m%d')

        # Get count of bills for today
        today_count = IPDBilling.objects.filter(
            bill_date__date=today
        ).count() + 1

        return f"IPD-BILL/{date_str}/{today_count:03d}"

    def calculate_totals(self):
        """Calculate total amount from items."""
        # Sum all bill items
        items_total = sum(
            item.total_price for item in self.items.all()
        )
        self.total_amount = items_total

        # Calculate balance
        net_amount = self.total_amount - self.discount + self.tax
        self.balance_amount = net_amount - self.paid_amount

        # Update status
        if self.paid_amount >= net_amount:
            self.status = 'paid'
            self.balance_amount = Decimal('0.00')
        elif self.paid_amount > Decimal('0.00'):
            self.status = 'partial'
        else:
            self.status = 'pending'

    def add_bed_charges(self):
        """Calculate and add bed charges based on length of stay."""
        if not self.admission.bed:
            return

        length_of_stay = self.admission.calculate_length_of_stay()
        if length_of_stay <= 0:
            length_of_stay = 1  # Minimum 1 day charge

        bed_charge_per_day = self.admission.bed.daily_charge
        total_bed_charge = bed_charge_per_day * length_of_stay

        # Create or update bed charge item
        IPDBillItem.objects.update_or_create(
            billing=self,
            source='Bed',
            item_name=f"{self.admission.bed} - {length_of_stay} day(s)",
            defaults={
                'quantity': length_of_stay,
                'unit_price': bed_charge_per_day,
                'total_price': total_bed_charge,
            }
        )

        self.calculate_totals()
        self.save()


class IPDBillItem(models.Model):
    """
    IPD Bill Item Model - Line items in IPD bills.

    Granular items like bed charges, pharmacy items, lab tests, etc.
    """

    SOURCE_CHOICES = [
        ('Bed', 'Bed Charges'),
        ('Pharmacy', 'Pharmacy'),
        ('Lab', 'Laboratory'),
        ('Radiology', 'Radiology'),
        ('Consultation', 'Consultation'),
        ('Procedure', 'Procedure'),
        ('Surgery', 'Surgery'),
        ('Other', 'Other'),
    ]

    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    billing = models.ForeignKey(
        IPDBilling,
        on_delete=models.CASCADE,
        related_name='items'
    )
    item_name = models.CharField(
        max_length=200,
        help_text="Description of the item/service"
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='Other',
        help_text="Source/category of the charge"
    )
    quantity = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Quantity (e.g., days for bed, units for medicine)"
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Price per unit"
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total price (quantity × unit_price)"
    )

    # Additional Details
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this item"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ipd_bill_items'
        ordering = ['billing', 'source', 'id']
        verbose_name = 'IPD Bill Item'
        verbose_name_plural = 'IPD Bill Items'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['billing', 'source']),
        ]

    def __str__(self):
        return f"{self.item_name} - {self.quantity} × {self.unit_price}"

    def save(self, *args, **kwargs):
        """Calculate total price before saving."""
        self.total_price = Decimal(str(self.quantity)) * self.unit_price
        super().save(*args, **kwargs)

        # Recalculate billing totals
        self.billing.calculate_totals()
        self.billing.save()
