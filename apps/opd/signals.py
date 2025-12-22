# opd/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum # Added Sum import
from decimal import Decimal
from .models import OPDBillItem, OPDBill # Added OPDBill import

@receiver([post_save, post_delete], sender=OPDBillItem)
def update_opd_bill_totals(sender, instance, **kwargs):
    """
    Signal to update the parent OPDBill's totals whenever an
    OPDBillItem is saved or deleted.
    """
    if instance.bill:
        instance.bill._calculate_derived_totals() # Call the new helper method
        # Save the OPDBill instance with updated calculated fields
        instance.bill.save(update_fields=['total_amount', 'discount_amount', 'payable_amount', 'balance_amount', 'payment_status'])


# New signal for OPDBill
@receiver([post_save, post_delete], sender=OPDBill)
def update_visit_payment_status(sender, instance, **kwargs):
    """
    Signal to update the associated Visit's payment status and paid amount
    whenever an OPDBill is saved or deleted.
    """
    if instance.visit:
        visit = instance.visit
        # Calculate total paid amount from all OPDBills associated with this visit
        # Summing received_amount for both 'paid' and 'partial' bills
        total_paid_from_bills = OPDBill.objects.filter(visit=visit).aggregate(Sum('received_amount'))['received_amount__sum'] or Decimal('0.00')
        
        visit.paid_amount = total_paid_from_bills
        visit.update_payment_status() # This method already calls save() on the Visit object.

