from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from common.mixins import TenantModelMixin, EncounterMixin

class Therapy(TenantModelMixin):
    """
    Therapy Model - Master list of Ayurvedic treatments.
    """
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True)
    base_charge = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'pk_therapies'
        verbose_name = 'Therapy'
        verbose_name_plural = 'Therapies'
        ordering = ['name']

    def __str__(self):
        return self.name

class PanchakarmaOrder(TenantModelMixin, EncounterMixin):
    """
    Panchakarma Order Model - Links a patient to a therapy via an encounter.
    """
    STATUS_CHOICES = [
        ('ordered', 'Ordered'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    patient = models.ForeignKey(
        'patients.PatientProfile',
        on_delete=models.PROTECT,
        related_name='panchakarma_orders'
    )
    therapy = models.ForeignKey(Therapy, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='ordered'
    )
    order_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pk_orders'
        verbose_name = 'Panchakarma Order'
        verbose_name_plural = 'Panchakarma Orders'
        ordering = ['-order_date']

    def __str__(self):
        return f"{self.therapy.name} for {self.patient}"

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

class PanchakarmaSession(TenantModelMixin):
    """
    Panchakarma Session Model - Tracks individual therapy sessions.
    """
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('missed', 'Missed'),
    ]

    order = models.ForeignKey(
        PanchakarmaOrder,
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    scheduled_date = models.DateTimeField()
    session_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled'
    )
    therapist_id = models.UUIDField(null=True, blank=True, help_text="User ID of the therapist")
    notes = models.TextField(blank=True)
    
    performed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pk_sessions'
        verbose_name = 'Panchakarma Session'
        verbose_name_plural = 'Panchakarma Sessions'
        ordering = ['scheduled_date']

    def __str__(self):
        return f"Session {self.session_number} - {self.order}"
