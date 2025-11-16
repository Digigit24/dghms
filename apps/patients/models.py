from django.db import models
from django.core.validators import RegexValidator
import datetime
import uuid


class PatientProfile(models.Model):
    """
    Patient profile - linked to SuperAdmin User via user_id UUID.
    Walk-in patients have user_id=None.
    """
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]

    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]

    MARITAL_STATUS_CHOICES = [
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('deceased', 'Deceased'),
    ]

    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )

    # Tenant isolation
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant this patient belongs to"
    )

    # Link to SuperAdmin User (optional for walk-ins)
    user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SuperAdmin User ID (null for walk-in patients)"
    )

    # Unique Identifier
    patient_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False
    )

    # Personal Info (required for walk-ins)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField(null=True, blank=True)
    age = models.PositiveIntegerField(editable=False)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)

    # Contact (required)
    mobile_primary = models.CharField(
        max_length=15,
        validators=[phone_regex]
    )
    mobile_secondary = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[phone_regex]
    )
    email = models.EmailField(blank=True, null=True)

    # Address
    address_line1 = models.CharField(max_length=200, null=True, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True, null=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, default='India')
    pincode = models.CharField(max_length=10, null=True, blank=True)

    # Medical Info
    blood_group = models.CharField(
        max_length=5,
        choices=BLOOD_GROUP_CHOICES,
        blank=True,
        null=True
    )
    height = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Height in cm"
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Weight in kg"
    )
    bmi = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        editable=False
    )

    # Social Info
    marital_status = models.CharField(
        max_length=20,
        choices=MARITAL_STATUS_CHOICES,
        default='single',
        null=True,
        blank=True
    )
    occupation = models.CharField(max_length=100, blank=True, null=True)

    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_phone = models.CharField(
        max_length=15,
        validators=[phone_regex],
        null=True,
        blank=True
    )
    emergency_contact_relation = models.CharField(max_length=50, null=True, blank=True)

    # Insurance
    insurance_provider = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )
    insurance_policy_number = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    insurance_expiry_date = models.DateField(blank=True, null=True)

    # Hospital Info
    registration_date = models.DateTimeField(auto_now_add=True)
    last_visit_date = models.DateTimeField(null=True, blank=True)
    total_visits = models.PositiveIntegerField(default=0)

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SuperAdmin User ID who created this patient"
    )

    class Meta:
        db_table = 'patient_profiles'
        verbose_name = 'Patient Profile'
        verbose_name_plural = 'Patient Profiles'
        ordering = ['-registration_date']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['user_id']),
            models.Index(fields=['patient_id']),
            models.Index(fields=['mobile_primary']),
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['status']),
            models.Index(fields=['tenant_id', 'status']),
        ]
        permissions = [
            ("view_all_patients", "Can view all patient records"),
            ("discharge_patient", "Can discharge patients"),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.patient_id})"

    def save(self, *args, **kwargs):
        # Generate patient ID
        if not self.patient_id:
            self.patient_id = self.generate_patient_id()

        # Calculate age
        if self.date_of_birth:
            today = datetime.date.today()
            self.age = today.year - self.date_of_birth.year - (
                (today.month, today.day) <
                (self.date_of_birth.month, self.date_of_birth.day)
            )

        # Calculate BMI
        if self.height and self.weight:
            height_m = float(self.height) / 100
            self.bmi = float(self.weight) / (height_m ** 2)

        super().save(*args, **kwargs)

    @property
    def full_name(self):
        """Returns full name"""
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"

    @property
    def full_address(self):
        """Returns formatted full address"""
        parts = [
            self.address_line1,
            self.address_line2,
            self.city,
            self.state,
            self.pincode,
            self.country
        ]
        return ', '.join(filter(None, parts))

    @property
    def is_insurance_valid(self):
        """Check if insurance is valid"""
        if not self.insurance_expiry_date:
            return False
        return self.insurance_expiry_date > datetime.date.today()

    @classmethod
    def generate_patient_id(cls):
        """Generate unique patient ID: PAT2025XXXX"""
        year = datetime.datetime.now().year
        last = cls.objects.filter(
            patient_id__startswith=f'PAT{year}'
        ).order_by('-patient_id').first()

        if last:
            try:
                num = int(last.patient_id[-4:]) + 1
            except ValueError:
                num = 1
        else:
            num = 1

        return f'PAT{year}{num:04d}'


class PatientVitals(models.Model):
    """Patient vital signs"""
    # Tenant isolation
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant this record belongs to"
    )

    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name='vitals'
    )

    recorded_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SuperAdmin User ID who recorded these vitals"
    )

    # Vital signs
    temperature = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="°C"
    )
    blood_pressure_systolic = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="mmHg"
    )
    blood_pressure_diastolic = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="mmHg"
    )
    heart_rate = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="BPM"
    )
    respiratory_rate = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Breaths/min"
    )
    oxygen_saturation = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="SpO2 %"
    )
    blood_glucose = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="mg/dL"
    )

    notes = models.TextField(blank=True, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'patient_vitals'
        verbose_name = 'Patient Vitals'
        verbose_name_plural = 'Patient Vitals'
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['patient', '-recorded_at']),
            models.Index(fields=['tenant_id', 'patient']),
        ]

    def __str__(self):
        return f"{self.patient.full_name} - {self.recorded_at.date()}"

    @property
    def blood_pressure(self):
        """Returns blood pressure in format: systolic/diastolic"""
        if self.blood_pressure_systolic and self.blood_pressure_diastolic:
            return f"{self.blood_pressure_systolic}/{self.blood_pressure_diastolic}"
        return None


class PatientAllergy(models.Model):
    """Patient allergies"""
    SEVERITY_CHOICES = [
        ('mild', 'Mild'),
        ('moderate', 'Moderate'),
        ('severe', 'Severe'),
        ('life_threatening', 'Life Threatening'),
    ]

    ALLERGY_TYPES = [
        ('drug', 'Drug/Medication'),
        ('food', 'Food'),
        ('environmental', 'Environmental'),
        ('contact', 'Contact'),
        ('other', 'Other'),
    ]

    # Tenant isolation
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant this record belongs to"
    )

    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name='allergies'
    )
    allergy_type = models.CharField(max_length=20, choices=ALLERGY_TYPES)
    allergen = models.CharField(max_length=200)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    symptoms = models.TextField()
    treatment = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    recorded_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SuperAdmin User ID who recorded this allergy"
    )

    class Meta:
        db_table = 'patient_allergies'
        verbose_name = 'Patient Allergy'
        verbose_name_plural = 'Patient Allergies'
        unique_together = ['patient', 'allergen']
        ordering = ['-severity', 'allergen']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['patient', 'is_active']),
            models.Index(fields=['tenant_id', 'patient']),
        ]

    def __str__(self):
        return f"{self.patient.full_name} - {self.allergen}"
