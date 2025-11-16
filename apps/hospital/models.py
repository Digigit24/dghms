from django.db import models
from django.core.exceptions import ValidationError


class Hospital(models.Model):
    """
    Hospital/Clinic configuration - Singleton model.
    Only one instance allowed in the entire system.
    """
    TYPE_CHOICES = [
        ('clinic', 'Clinic'),
        ('hospital', 'Hospital'),
    ]

    # Tenant
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")

    # Basic Information
    name = models.CharField(max_length=200)
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='hospital'
    )
    tagline = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        help_text="Brief tagline or slogan"
    )
    
    # Contact Information
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    alternate_phone = models.CharField(max_length=15, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    
    # Address
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    pincode = models.CharField(max_length=10)
    
    # Media - temporarily disabled ImageField
    logo = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Logo URL (ImageField disabled temporarily)"
    )
    
    # Settings
    working_hours = models.CharField(
        max_length=100,
        default='24/7',
        help_text="e.g., '9 AM - 9 PM' or '24/7'"
    )
    has_emergency = models.BooleanField(
        default=True,
        help_text="Has emergency services"
    )
    has_pharmacy = models.BooleanField(
        default=True,
        help_text="Has in-house pharmacy"
    )
    has_laboratory = models.BooleanField(
        default=True,
        help_text="Has in-house laboratory"
    )
    
    # Additional
    registration_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Hospital registration number"
    )
    established_date = models.DateField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'hospital_config'
        verbose_name = 'Hospital Configuration'
        verbose_name_plural = 'Hospital Configuration'
        indexes = [
            models.Index(fields=['tenant_id']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"
    
    def save(self, *args, **kwargs):
        """Enforce singleton pattern - only one hospital allowed"""
        if not self.pk and Hospital.objects.exists():
            raise ValidationError(
                'Hospital configuration already exists. '
                'Please update the existing record instead of creating a new one.'
            )
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Prevent deletion of hospital configuration"""
        raise ValidationError(
            'Hospital configuration cannot be deleted. '
            'Please update it instead.'
        )
    
    @classmethod
    def get_hospital(cls):
        """Get the hospital instance (singleton)"""
        hospital = cls.objects.first()
        if not hospital:
            raise ValidationError(
                'Hospital configuration not found. '
                'Please create one via Django admin.'
            )
        return hospital
    
    @property
    def full_address(self):
        """Returns formatted full address"""
        return f"{self.address}, {self.city}, {self.state} {self.pincode}, {self.country}"

