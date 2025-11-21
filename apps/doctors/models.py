from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid


class Specialty(models.Model):
    """Medical specialties"""
    # Tenant isolation
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant this specialty belongs to"
    )

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'specialties'
        verbose_name = 'Specialty'
        verbose_name_plural = 'Specialties'
        ordering = ['name']
        unique_together = [['tenant_id', 'code']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['name']),
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
            models.Index(fields=['tenant_id', 'is_active']),
        ]

    def __str__(self):
        return self.name


class DoctorProfile(models.Model):
    """
    Doctor profile linked to SuperAdmin User via user_id UUID.
    All doctors MUST have a user account (required for login).
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('on_leave', 'On Leave'),
        ('inactive', 'Inactive'),
    ]

    # Tenant isolation
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant this doctor belongs to"
    )

    # Link to SuperAdmin User (REQUIRED - doctors must be able to login)
    user_id = models.UUIDField(
        unique=True,
        db_index=True,
        help_text="SuperAdmin User ID (required for doctors)"
    )

    # Name fields (for display purposes - can be synced from SuperAdmin)
    first_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Doctor's first name (cached from SuperAdmin or manually entered)"
    )
    last_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Doctor's last name (cached from SuperAdmin or manually entered)"
    )

    # License Information
    medical_license_number = models.CharField(max_length=64, blank=True, null=True)
    license_issuing_authority = models.CharField(max_length=128, blank=True, null=True)
    license_issue_date = models.DateField(blank=True, null=True)
    license_expiry_date = models.DateField(blank=True, null=True)

    # Professional Information
    qualifications = models.TextField(blank=True, null=True)
    specialties = models.ManyToManyField(
        Specialty,
        related_name='doctors',
    
        blank=True, 
       
    )
    years_of_experience = models.PositiveIntegerField(default=0,blank=True, null=True)

    # Consultation Settings
    consultation_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Consultation fee in INR",
        blank=True, 
        null=True,
    )
    follow_up_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        blank=True, null=True,
        help_text="Follow-up consultation fee in INR"
    )

    consultation_duration = models.PositiveIntegerField(
        default=15,
        
        help_text="Duration in minutes"
    )
    is_available_online = models.BooleanField(default=False)
    is_available_offline = models.BooleanField(default=True)

    # Status
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default='active'

    )

    # Ratings & Statistics (read-only, updated by system)
    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
        editable=False
    )
    total_reviews = models.PositiveIntegerField(default=0, editable=False)
    total_consultations = models.PositiveIntegerField(default=0, editable=False)

    # Additional Information
    signature = models.TextField(blank=True, null=True)
    languages_spoken = models.TextField(
        blank=True,
        null=True,
        help_text="Comma-separated languages"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'doctor_profiles'
        verbose_name = 'Doctor Profile'
        verbose_name_plural = 'Doctor Profiles'
        ordering = ['-created_at']
        unique_together = [['tenant_id', 'user_id']]
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['user_id']),
            models.Index(fields=['status']),
            models.Index(fields=['medical_license_number']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['tenant_id', 'status']),
        ]
        permissions = [
            ("view_all_doctors", "Can view all doctor profiles"),
            ("manage_doctor_schedule", "Can manage doctor schedules"),
        ]

    def __str__(self):
        if self.first_name or self.last_name:
            return f"Dr. {self.full_name}"
        return f"DoctorProfile ({self.user_id})"

    @property
    def full_name(self):
        """Return doctor's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return f"Doctor {self.user_id}"

    @property
    def is_license_valid(self):
        """
        Check if license is valid based on expiry date.
        Returns:
            True: License is valid (expiry date is today or in future)
            False: License has expired
            None: No expiry date set (unknown status)
        """
        if not self.license_expiry_date:
            return None
        return self.license_expiry_date >= timezone.localdate()

    def clean(self):
        """Validate model fields"""
        errors = {}

        if self.follow_up_fee is not None and self.follow_up_fee < 0:
            errors['follow_up_fee'] = 'Follow-up fee cannot be negative.'

        # Validate license dates
        if self.license_issue_date and self.license_expiry_date:
            if self.license_expiry_date < self.license_issue_date:
                errors['license_expiry_date'] = 'Expiry date cannot be before issue date.'

        # Validate consultation fee
        if self.consultation_fee is not None and self.consultation_fee < 0:
            errors['consultation_fee'] = 'Consultation fee cannot be negative.'

        # Validate consultation duration
        if self.consultation_duration and self.consultation_duration < 5:
            errors['consultation_duration'] = 'Consultation duration must be at least 5 minutes.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)


class DoctorAvailability(models.Model):
    """Weekly availability schedule for doctors"""
    DAYS_OF_WEEK = [
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday'),
    ]

    # Tenant isolation
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant this availability belongs to"
    )

    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name='availability'
    )
    day_of_week = models.CharField(max_length=16, choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    max_appointments = models.PositiveIntegerField(
        default=0,
        help_text="Maximum appointments for this slot (0 = unlimited)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'doctor_availability'
        verbose_name = 'Doctor Availability'
        verbose_name_plural = 'Doctor Availability'
        ordering = ['doctor', 'day_of_week', 'start_time']
        unique_together = ['doctor', 'day_of_week', 'start_time']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['doctor', 'day_of_week']),
            models.Index(fields=['is_available']),
            models.Index(fields=['tenant_id', 'doctor']),
        ]

    def __str__(self):
        return f'{self.doctor} - {self.get_day_of_week_display()} {self.start_time}-{self.end_time}'

    def clean(self):
        """Validate availability slot"""
        if self.end_time <= self.start_time:
            raise ValidationError({
                'end_time': 'End time must be after start time.'
            })

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)
