# ipd/models.py
from django.db import models, transaction, IntegrityError, connection
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
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

    CLAIM_STATUS_CHOICES = [
        ('not_applicable', 'Not Applicable'),
        ('not_started', 'Not Started'),
        ('documents_pending', 'Documents Pending'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('settled', 'Settled'),
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

    # Registration classification & doctors (additive — IPD Registration form)
    ADMISSION_TYPE_CHOICES = [
        ('regular', 'Regular'),
        ('emergency', 'Emergency'),
        ('transfer', 'Transfer'),
        ('readmission', 'Readmission'),
    ]
    admission_type = models.CharField(
        max_length=20,
        choices=ADMISSION_TYPE_CHOICES,
        default='regular',
        help_text="Type of admission",
    )
    reference_doctor_id = models.UUIDField(
        null=True, blank=True,
        help_text="SuperAdmin User ID of the reference/referring doctor",
    )
    notify_reference_doctor = models.BooleanField(
        default=False,
        help_text="Whether to send an SMS to the reference doctor",
    )
    consulting_doctor_ids = models.JSONField(
        default=list, blank=True,
        help_text="List of SuperAdmin User IDs of consulting doctors (multiple allowed)",
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

    # Insurance / Mediclaim Information
    has_mediclaim = models.BooleanField(
        default=False,
        help_text="Whether the patient has Mediclaim/TPA coverage for this admission"
    )
    tpa_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Selected or entered TPA/insurance provider name"
    )
    claim_status = models.CharField(
        max_length=30,
        choices=CLAIM_STATUS_CHOICES,
        default='not_applicable',
        help_text="Manual claim processing status"
    )
    claim_reference_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="TPA claim/pre-auth/reference number"
    )
    claim_notes = models.TextField(
        blank=True,
        help_text="Manual notes for claim processing"
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
            models.Index(fields=['tenant_id', 'has_mediclaim']),
            models.Index(fields=['tenant_id', 'claim_status']),
        ]

    def __str__(self):
        return f"{self.admission_id} - {self.patient}"

    def save(self, *args, **kwargs):
        """Auto-generate admission_id if not set and handle bed occupancy.

        admission_id is always backend-generated, scoped per tenant and per day
        (IPD/YYYYMMDD/###). Generation is race-safe: it locks existing rows for the
        tenant/date and retries on the rare unique-constraint collision, so every
        tenant gets its own clash-free sequence without the frontend sending an ID.
        """
        is_new = self.pk is None

        if not self.admission_id:
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    with transaction.atomic():
                        # Lock existing rows for this tenant/date to avoid races
                        admission_day = self._admission_day()
                        Admission.objects.select_for_update().filter(
                            tenant_id=self.tenant_id,
                            admission_date__date=admission_day
                        ).exists()

                        self.admission_id = self.generate_admission_id_for_tenant(
                            self.tenant_id,
                            admission_day
                        )
                        super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    if attempt == max_retries - 1:
                        raise
                    import time
                    time.sleep(0.1 * (2 ** attempt))
                    self.admission_id = None
                    continue
        else:
            super().save(*args, **kwargs)

        # Mark bed as occupied on new admission
        if is_new and self.bed and self.status == 'admitted':
            self.bed.mark_occupied()

    def _admission_day(self):
        """Return the date portion of admission_date (defaults to today)."""
        value = self.admission_date or timezone.now()
        return value.date() if hasattr(value, 'date') else value

    @staticmethod
    def generate_admission_id_for_tenant(tenant_id, admission_day):
        """Generate a unique admission ID per tenant: IPD/YYYYMMDD/###

        Fetches matching IDs for this tenant/date and sorts in Python to ensure
        correct numeric sequencing (001 < 010 < 100) regardless of DB string sort.
        """
        from datetime import date

        admission_day = admission_day if isinstance(admission_day, date) else admission_day.date()
        date_str = admission_day.strftime('%Y%m%d')
        prefix = f"IPD/{date_str}/"

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT admission_id FROM ipd_admissions
                WHERE tenant_id = %s AND admission_date::date = %s
                AND admission_id LIKE %s
                """,
                [str(tenant_id), admission_day, f"{prefix}%"]
            )
            results = cursor.fetchall()

        next_seq = 1
        for row in results:
            try:
                sequence = int(row[0].split('/')[-1])
                next_seq = max(next_seq, sequence + 1)
            except (ValueError, IndexError):
                continue

        return f"{prefix}{next_seq:03d}"

    @staticmethod
    def generate_admission_id():
        """Deprecated: use generate_admission_id_for_tenant(tenant_id, admission_day).

        Kept for backward compatibility; it does not isolate by tenant.
        """
        raise NotImplementedError(
            "Use generate_admission_id_for_tenant(tenant_id, admission_day) instead"
        )

    def calculate_length_of_stay(self):
        """Calculate length of stay in days."""
        if self.discharge_date:
            delta = self.discharge_date - self.admission_date
            return delta.days
        else:
            delta = timezone.now() - self.admission_date
            return delta.days

    def discharge(self, discharge_type='Normal', discharge_summary='', discharged_by_user_id=None, discharge_date=None):
        """Discharge the patient and release the bed.

        Args:
            discharge_type: Type of discharge (e.g., 'Normal', 'Against Medical Advice')
            discharge_summary: Summary notes for discharge
            discharged_by_user_id: ID of user performing discharge
            discharge_date: Optional specific discharge date/time (defaults to current time)
        """
        self.status = 'discharged'
        self.discharge_date = discharge_date or timezone.now()
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
    IPD Billing Model - Billing for IPD admissions.

    Supports multiple bills per admission (like OPD).
    Summarizes all charges including bed charges, diagnostics, pharmacy, etc.
    """

    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
    ]

    PAYMENT_MODE_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('netbanking', 'Net Banking'),
        ('insurance', 'Insurance'),
        ('cheque', 'Cheque'),
        ('other', 'Other'),
    ]

    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    # Changed from OneToOneField to ForeignKey to allow multiple bills per admission
    admission = models.ForeignKey(
        Admission,
        on_delete=models.PROTECT,
        related_name='ipd_bills',
        help_text="Admission this bill belongs to"
    )

    bill_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text="Unique bill identifier (e.g., IPD-BILL/20231223/001)"
    )
    bill_date = models.DateTimeField(
        default=timezone.now,
        help_text="Bill generation date"
    )

    # Doctor Reference
    doctor_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Attending doctor ID"
    )

    # Diagnosis and Remarks
    diagnosis = models.TextField(blank=True, help_text="Diagnosis for this bill")
    remarks = models.TextField(blank=True, help_text="Additional remarks or notes")

    # Financial Details (Auto-calculated from items)
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total amount (sum of items)"
    )

    # Discount (percentage or amount)
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Discount percentage (0-100)"
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Discount amount (calculated or manual)"
    )

    # Payable amount (after discount)
    payable_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Amount to be paid (total - discount)"
    )

    # Payment Details
    payment_mode = models.CharField(
        max_length=20,
        choices=PAYMENT_MODE_CHOICES,
        default='cash',
        help_text="Mode of payment"
    )
    payment_details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Payment transaction details (JSON)"
    )
    received_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Amount received from patient"
    )
    balance_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Balance due (payable - received)"
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid'
    )

    # Audit Fields
    billed_by_id = models.UUIDField(
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
        verbose_name = 'IPD Bill'
        verbose_name_plural = 'IPD Bills'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'payment_status']),
            models.Index(fields=['admission', 'bill_date']),
            models.Index(fields=['bill_number'], name='ipd_bill_number_idx'),
            models.Index(fields=['payment_status'], name='ipd_payment_status_idx'),
        ]

    def __str__(self):
        return f"{self.bill_number} - {self.admission.admission_id}"

    def save(self, *args, **kwargs):
        """Save IPD bill with auto-calculations."""
        from django.db import transaction, IntegrityError

        max_retries = 3
        last_exception = None

        for _ in range(max_retries):
            save_kwargs = kwargs.copy()
            try:
                with transaction.atomic():
                    is_new_instance = self.pk is None

                    if not self.bill_number:
                        self.bill_number = self._generate_bill_number()

                    # Check if this is a signal-triggered save
                    is_signal_save = 'update_fields' in save_kwargs

                    if is_new_instance:
                        # For NEW instances: save all fields first to get PK
                        super().save(*args, **save_kwargs)
                        save_kwargs.pop('force_insert', None)
                        save_kwargs.pop('force_update', None)
                        save_kwargs.pop('using', None)
                        save_kwargs.pop('update_fields', None)

                        # Then calculate and save derived fields
                        self._calculate_derived_totals()
                        save_kwargs['update_fields'] = ['total_amount', 'discount_amount', 'payable_amount', 'balance_amount', 'payment_status']
                        super().save(*args, **save_kwargs)

                    elif is_signal_save:
                        # Signal-triggered save: only recalculate and save specified fields
                        self._calculate_derived_totals()
                        super().save(*args, **save_kwargs)

                    else:
                        # Normal update: save all changed fields first, then recalculate
                        super().save(*args, **save_kwargs)

                        # Then recalculate derived fields and save them
                        self._calculate_derived_totals()
                        save_kwargs['update_fields'] = ['total_amount', 'discount_amount', 'payable_amount', 'balance_amount', 'payment_status']
                        super().save(*args, **save_kwargs)

                return
            except IntegrityError as exc:
                last_exception = exc
                if 'ipd_bill_number_idx' in str(exc) or 'ipd_billings_bill_number_key' in str(exc):
                    self.bill_number = None
                    continue
                raise

        if last_exception:
            raise last_exception

    def _generate_bill_number(self):
        """Generate unique bill number: IPD-BILL/YYYYMMDD/###

        Scoped per tenant_id (CLAUDE.md tenant isolation rules) — previously
        this counted ALL bills for the day across every tenant, which both
        leaked cross-tenant sequence information and made numbering
        non-deterministic per tenant. Must be an instance method (not
        @staticmethod) since it needs self.tenant_id.
        """
        from datetime import date
        today = date.today()
        date_str = today.strftime('%Y%m%d')

        # Get count of bills for today, scoped to this tenant only
        today_count = IPDBilling.objects.filter(
            tenant_id=self.tenant_id,
            bill_date__date=today
        ).count() + 1

        return f"IPD-BILL/{date_str}/{today_count:03d}"

    def _calculate_derived_totals(self):
        """
        Calculate and update derived financial fields.
        Called automatically by save() method.

        Calculations:
        1. total_amount = sum of all item total_prices
        2. discount_amount = (total_amount * discount_percent / 100) OR manual discount_amount
        3. payable_amount = total_amount - discount_amount
        4. balance_amount = payable_amount - received_amount
        5. payment_status = 'paid' | 'partial' | 'unpaid'
        """
        # Sum all bill items
        items_total = self.items.aggregate(
            total=models.Sum('total_price')
        )['total'] or Decimal('0.00')

        self.total_amount = items_total

        # Calculate discount
        if self.discount_percent > 0:
            # Calculate discount from percentage (overrides manual discount_amount)
            self.discount_amount = (self.total_amount * self.discount_percent / Decimal('100.00')).quantize(Decimal('0.01'))
        # else: keep existing discount_amount (allows manual discounts when discount_percent is 0)

        # Ensure discount_amount is set
        if self.discount_amount is None:
            self.discount_amount = Decimal('0.00')

        # Calculate payable amount
        self.payable_amount = self.total_amount - self.discount_amount

        # Calculate balance
        self.balance_amount = self.payable_amount - self.received_amount

        # Update payment status
        # NOTE: payable_amount > 0 is required for 'paid' — a brand-new bill
        # with no items yet has payable_amount == received_amount == 0, and
        # 0 >= 0 is True, so without this guard every empty bill was
        # incorrectly marked 'paid' the instant it was created (before any
        # item was ever added). That falsely triggered the BILL_LOCKED guard
        # on bill-item create/update/delete, making it look like there was no
        # way to add items to a fresh bill at all.
        if self.payable_amount > Decimal('0.00') and self.received_amount >= self.payable_amount:
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
        self.save()

    def get_bed_day_info(self):
        """
        Returns bed day tracking info for this admission:
          - total_los: full length of stay (days)
          - already_billed_days: days billed in OTHER bills for this admission
          - remaining_days: unbilled days available for this bill to charge
          - this_bill_days: bed days currently in this bill's bed item (0 if none)
        """
        if not self.admission.bed:
            return {'total_los': 0, 'already_billed_days': 0, 'remaining_days': 0, 'this_bill_days': 0}

        if self.admission.discharge_date:
            delta = self.admission.discharge_date - self.admission.admission_date
        else:
            delta = timezone.now() - self.admission.admission_date

        total_los = max(1, delta.days if delta.days > 0 else 1)

        from django.db.models import Sum as DSum
        admission_ct = ContentType.objects.get_for_model(self.admission)

        # Days billed in OTHER bills for this admission
        already_billed = (
            IPDBillItem.objects
            .filter(
                bill__admission=self.admission,
                source='Bed',
                origin_content_type=admission_ct,
                origin_object_id=self.admission.pk,
            )
            .exclude(bill=self)
            .aggregate(total=DSum('quantity'))['total'] or 0
        )

        # Days in THIS bill's bed item
        try:
            this_item = IPDBillItem.objects.get(
                bill=self,
                source='Bed',
                origin_content_type=admission_ct,
                origin_object_id=self.admission.pk,
            )
            this_bill_days = int(this_item.quantity)
        except IPDBillItem.DoesNotExist:
            this_bill_days = 0

        remaining_days = max(0, total_los - int(already_billed))

        return {
            'total_los': total_los,
            'already_billed_days': int(already_billed),
            'remaining_days': remaining_days,
            'this_bill_days': this_bill_days,
        }

    def add_bed_charges(self):
        """
        Calculate and add bed charges based on length of stay.

        Only bills the REMAINING unbilled days for this admission — days already
        billed in other bills for the same admission are excluded.

        Automatically creates/updates IPDBillItem with:
        - Proper calculation: (discharge_date or current_date) - admission_date
        - Minimum 1 day total charge across all bills
        - Links to Admission via origin_order GFK
        - Sets system_calculated_price for manual override tracking
        """
        if not self.admission.bed:
            return

        admission_ct = ContentType.objects.get_for_model(self.admission)

        info = self.get_bed_day_info()
        total_los = info['total_los']
        already_billed_days = info['already_billed_days']
        days_to_bill = info['remaining_days']

        if days_to_bill <= 0:
            # All days already billed in other bills — skip bed item for this bill
            return None

        bed_charge_per_day = self.admission.bed.daily_charge
        from_date = self.admission.admission_date.date()
        to_date = (self.admission.discharge_date or timezone.now()).date()

        notes = (
            f"Bed charges: {days_to_bill} of {total_los} total day(s) "
            f"({from_date} to {to_date})"
        )
        if already_billed_days > 0:
            notes += f". {already_billed_days} day(s) billed in other bills."

        # Create or update bed charge item for remaining days only
        bed_item, created = IPDBillItem.objects.update_or_create(
            bill=self,
            source='Bed',
            origin_content_type=admission_ct,
            origin_object_id=self.admission.pk,
            defaults={
                'tenant_id': self.tenant_id,
                'item_name': f"{self.admission.bed} - {days_to_bill} day(s)",
                'quantity': days_to_bill,
                'unit_price': bed_charge_per_day,
                'system_calculated_price': bed_charge_per_day,
                'total_price': bed_charge_per_day * days_to_bill,
                'notes': notes,
            }
        )
        # No need to call save() — signal auto-recalculates totals

        return bed_item


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
        ('Therapy', 'Therapy'),
        ('Package', 'Package'),
        ('Service', 'Service'),
        ('Other', 'Other'),
    ]

    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    bill = models.ForeignKey(
        IPDBilling,
        on_delete=models.CASCADE,
        related_name='items',
        help_text="IPD bill this item belongs to"
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

    # Pricing with Manual Override Support
    system_calculated_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="System-calculated price from master data"
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Actual unit price charged (may differ from system price)"
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total price for this item"
    )
    is_price_overridden = models.BooleanField(
        default=False,
        help_text="Flag indicating if unit_price was manually changed from system_calculated_price"
    )

    # Origin GFK — what this line item was generated FROM.
    # For source='Bed' items this points at the Admission itself (the dedup
    # key used by IPDBilling.get_bed_day_info()/add_bed_charges() to compute
    # already-billed bed-days across ALL bills for the admission — NOT at any
    # clinical order/model). For catalog-sourced items (Procedure/Package/
    # Service/Investigation-backed Lab/Radiology items) it points at the
    # catalog row itself. For fully custom/manual items it is left null.
    origin_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Type of the source record (Admission for bed charges, or a catalog row)",
        related_name='+'
    )
    origin_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the source record referenced by origin_content_type"
    )
    origin = GenericForeignKey('origin_content_type', 'origin_object_id')

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ipd_bill_items"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id"]),
            models.Index(fields=["tenant_id", "bill"]),
            models.Index(fields=["origin_content_type", "origin_object_id"]),
        ]

    def __str__(self):
        return f"{self.item_name} x{self.quantity} = {self.total_price}"


class IPDBillTemplate(models.Model):
    """
    IPD Bill Template Model - Reusable set of line items for fast bill creation.

    Tenants can save a bill's line items as a template (or hand-craft one)
    and re-apply it to future bills. Bed charges are always auto-computed
    per bill (see IPDBilling.add_bed_charges) so 'Bed' is never a valid
    source for a template item — enforced in IPDBillTemplateItemSerializer.
    """

    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    name = models.CharField(max_length=200, help_text="Template name")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="User who created this template"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ipd_bill_templates'
        ordering = ['name']
        verbose_name = 'IPD Bill Template'
        verbose_name_plural = 'IPD Bill Templates'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'is_active']),
        ]

    def __str__(self):
        return self.name


class IPDBillTemplateItem(models.Model):
    """
    IPD Bill Template Item Model - A single line item within a bill template.

    'Bed' must never be saved as source here — bed charges are always
    computed per-bill from the admission's actual length of stay, never
    part of a reusable template. Enforced in the serializer's validate().
    """

    # Primary Fields
    id = models.AutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    template = models.ForeignKey(
        IPDBillTemplate,
        on_delete=models.CASCADE,
        related_name='items',
        help_text="Bill template this item belongs to"
    )
    item_name = models.CharField(max_length=200, help_text="Description of the item/service")
    source = models.CharField(
        max_length=20,
        choices=IPDBillItem.SOURCE_CHOICES,
        default='Other',
        help_text="Source/category of the charge (never 'Bed')"
    )
    default_quantity = models.PositiveIntegerField(default=1)
    default_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Default unit price applied when this template is used"
    )

    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ipd_bill_template_items'
        ordering = ['id']
        verbose_name = 'IPD Bill Template Item'
        verbose_name_plural = 'IPD Bill Template Items'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'template']),
        ]

    def __str__(self):
        return f"{self.item_name} ({self.template.name})"
