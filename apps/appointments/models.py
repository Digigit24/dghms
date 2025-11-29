from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class AppointmentType(models.Model):
    """Types of medical appointments"""
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    duration_default = models.PositiveIntegerField(default=15)  # Default duration in minutes
    base_consultation_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    class Meta:
        db_table = 'appointment_types'
        verbose_name = 'Appointment Type'
        verbose_name_plural = 'Appointment Types'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'name']),
        ]
    
    def __str__(self):
        return self.name


class Appointment(models.Model):
    """Comprehensive Appointment Model"""
    class StatusChoices(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        CONFIRMED = 'confirmed', 'Confirmed'
        CHECKED_IN = 'checked_in', 'Checked In'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        NO_SHOW = 'no_show', 'No Show'
        RESCHEDULED = 'rescheduled', 'Rescheduled'

    class PriorityChoices(models.TextChoices):
        LOW = 'low', 'Low'
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'

    # Unique Identifiers
    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True, help_text="Tenant this record belongs to")
    appointment_id = models.CharField(
        max_length=36,
        unique=True,
        editable=False
    )

    # Foreign Key Relationships
    patient = models.ForeignKey(
        'patients.PatientProfile',
        on_delete=models.PROTECT,
        related_name='appointments'
    )
    doctor = models.ForeignKey(
        'doctors.DoctorProfile', 
        on_delete=models.PROTECT,
        related_name='appointments'
    )
    appointment_type = models.ForeignKey(
        AppointmentType,
        on_delete=models.PROTECT,
        related_name='appointments',
        null=True,
        blank=True,
        help_text="Type of appointment (optional)"
    )

    # Appointment Details
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=15)

    # Status and Priority
    status = models.CharField(
        max_length=20, 
        choices=StatusChoices.choices, 
        default=StatusChoices.SCHEDULED
    )
    priority = models.CharField(
        max_length=10,
        choices=PriorityChoices.choices,
        default=PriorityChoices.NORMAL
    )

    # Medical Information
    chief_complaint = models.TextField(null=True, blank=True)
    symptoms = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    # Follow-up and Referencing
    is_follow_up = models.BooleanField(default=False)
    original_appointment = models.ForeignKey(
        'self', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='follow_ups'
    )

    # Financial Details - Removed payment method
    consultation_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00')
    )

    visit = models.ForeignKey(
    'opd.Visit',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='linked_appointment',  # ← FIXED: unique name
    help_text="Associated OPD visit when patient checks in"
)

    
    # Check-in tracking (NEW)
    check_in_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Time when patient checked in for the appointment"
    )

    # Timing and Check-in Details
    checked_in_at = models.DateTimeField(null=True, blank=True)
    actual_start_time = models.TimeField(null=True, blank=True)
    actual_end_time = models.TimeField(null=True, blank=True)
    waiting_time_minutes = models.PositiveIntegerField(null=True, blank=True)

    # Cancellation Details
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by_id = models.UUIDField(null=True, blank=True, help_text="User who cancelled this appointment")
    cancellation_reason = models.TextField(null=True, blank=True)

    # Approval Details
    approved_by_id = models.UUIDField(null=True, blank=True, help_text="User who approved this appointment")
    approved_at = models.DateTimeField(null=True, blank=True)

    # Creation and Tracking
    created_by_id = models.UUIDField(null=True, blank=True, help_text="User who created this appointment")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'appointments'
        verbose_name = 'Appointment'
        verbose_name_plural = 'Appointments'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'appointment_date']),
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['doctor', 'appointment_date', 'appointment_time']),
            models.Index(fields=['patient', 'appointment_date']),
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['created_at', 'updated_at'])
        ]
        unique_together = [('doctor', 'appointment_date', 'appointment_time')]

    def __str__(self):
        return f"{self.appointment_id} - {self.patient} with {self.doctor}"

    def save(self, *args, **kwargs):
        # Generate appointment ID if not exists
        if not self.appointment_id:
            # Generate a unique appointment ID: APT-2025-000123
            year = timezone.now().year
            last_appointment = Appointment.objects.filter(
                appointment_id__startswith=f'APT-{year}-'
            ).order_by('-appointment_id').first()

            if last_appointment:
                last_number = int(last_appointment.appointment_id.split('-')[-1])
                new_number = last_number + 1
            else:
                new_number = 1

            self.appointment_id = f'APT-{year}-{new_number:06d}'

        # Auto-set consultation fee from appointment type
        if not self.consultation_fee and self.appointment_type:
            # Prefer doctor's consultation fee, fallback to appointment type's base fee
            self.consultation_fee = (
                self.doctor.consultation_fee if hasattr(self.doctor, 'consultation_fee') 
                else self.appointment_type.base_consultation_fee
            )

        # Auto-set end time if not provided
        if not self.end_time:
            from datetime import timedelta, datetime
            start = datetime.combine(datetime.today(), self.appointment_time)
            end = start + timedelta(minutes=self.duration_minutes)
            self.end_time = end.time()

        # Perform validations
        self.full_clean()

        super().save(*args, **kwargs)

    def clean(self):
        # Validate status transitions and business rules
        if self.status == self.StatusChoices.CANCELLED and not self.cancellation_reason:
            raise ValidationError("Cancellation reason is required when status is cancelled")

        if self.is_follow_up and not self.original_appointment:
            raise ValidationError("Follow-up appointments must reference an original appointment")

        # Optional: Add more validation logic like time and duration checks

    def get_waiting_time(self):
        """Calculate waiting time if check-in and start times are available"""
        if self.checked_in_at and self.actual_start_time:
            import datetime
            check_in_time = self.checked_in_at.time()
            start_time = self.actual_start_time
            
            # Convert times to total minutes for comparison
            check_in_minutes = check_in_time.hour * 60 + check_in_time.minute
            start_minutes = start_time.hour * 60 + start_time.minute
            
            self.waiting_time_minutes = max(0, start_minutes - check_in_minutes)
            self.save()

        return self.waiting_time_minutes