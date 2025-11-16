from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal


class ServiceCategory(models.Model):
    """Service category model"""
    TYPE_CHOICES = [
        ('diagnostic', 'Diagnostic'),
        ('nursing', 'Nursing Care'),
        ('home_care', 'Home Healthcare'),
        ('other', 'Other')
    ]

    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    is_active = models.BooleanField(default=True)
    icon = models.ImageField(
        upload_to='service_categories/', 
        blank=True, 
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'service_categories'
        verbose_name_plural = 'Service Categories'
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'type']),
        ]

    def __str__(self):
        return self.name


class BaseService(models.Model):
    """Abstract base service model"""
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    base_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    discounted_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    category = models.ForeignKey(
        ServiceCategory, 
        on_delete=models.PROTECT,
        related_name='%(class)s_services'
    )
    code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    image = models.ImageField(
        upload_to='services/', 
        blank=True, 
        null=True
    )
    duration_minutes = models.PositiveIntegerField(default=30)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'is_active']),
            models.Index(fields=['tenant_id', 'category']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def calculate_final_price(self):
        """Calculate final price considering discounts"""
        return self.discounted_price or self.base_price


class DiagnosticTest(BaseService):
    """Diagnostic test service"""
    SAMPLE_TYPE_CHOICES = [
        ('blood', 'Blood'),
        ('urine', 'Urine'),
        ('imaging', 'Imaging'),
        ('other', 'Other')
    ]

    REPORTING_TYPE_CHOICES = [
        ('digital', 'Digital'),
        ('physical', 'Physical'),
        ('both', 'Both')
    ]

    sample_type = models.CharField(
        max_length=20, 
        choices=SAMPLE_TYPE_CHOICES
    )
    is_home_collection = models.BooleanField(default=False)
    home_collection_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    preparation_instructions = models.TextField(blank=True, null=True)
    typical_turnaround_time = models.PositiveIntegerField(
        help_text="Turnaround time in hours"
    )
    reporting_type = models.CharField(
        max_length=20, 
        choices=REPORTING_TYPE_CHOICES,
        default='digital'
    )

    class Meta:
        db_table = 'diagnostic_tests'
        verbose_name_plural = 'Diagnostic Tests'


class NursingCarePackage(BaseService):
    """Nursing care package service"""
    PACKAGE_TYPE_CHOICES = [
        ('hourly', 'Hourly'),
        ('half_day', 'Half Day'),
        ('full_day', 'Full Day')
    ]

    TARGET_GROUP_CHOICES = [
        ('elderly', 'Elderly'),
        ('post_surgery', 'Post Surgery'),
        ('child_care', 'Child Care'),
        ('other', 'Other')
    ]

    package_type = models.CharField(
        max_length=20, 
        choices=PACKAGE_TYPE_CHOICES
    )
    included_services = models.JSONField(
        blank=True, 
        null=True, 
        help_text="JSON list of included services"
    )
    max_duration = models.PositiveIntegerField(
        help_text="Maximum duration in hours"
    )
    target_group = models.CharField(
        max_length=20, 
        choices=TARGET_GROUP_CHOICES,
        default='other'
    )

    class Meta:
        db_table = 'nursing_care_packages'
        verbose_name_plural = 'Nursing Care Packages'


class HomeHealthcareService(BaseService):
    """Home healthcare service"""
    SERVICE_TYPE_CHOICES = [
        ('medical_assistance', 'Medical Assistance'),
        ('personal_care', 'Personal Care'),
        ('wound_care', 'Wound Care'),
        ('medication_management', 'Medication Management'),
        ('other', 'Other')
    ]

    STAFF_TYPE_CHOICES = [
        ('nurse', 'Nurse'),
        ('caregiver', 'Caregiver'),
        ('physiotherapist', 'Physiotherapist'),
        ('doctor', 'Doctor')
    ]

    service_type = models.CharField(
        max_length=50, 
        choices=SERVICE_TYPE_CHOICES
    )
    staff_type_required = models.CharField(
        max_length=50, 
        choices=STAFF_TYPE_CHOICES
    )
    equipment_needed = models.TextField(blank=True, null=True)
    max_distance_km = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('10.00')
    )

    class Meta:
        db_table = 'home_healthcare_services'
        verbose_name_plural = 'Home Healthcare Services'