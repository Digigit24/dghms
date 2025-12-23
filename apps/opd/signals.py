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
        # The save() method will call _calculate_derived_totals() automatically
        # Just trigger a save to recalculate totals
        instance.bill.save(update_fields=['total_amount', 'discount_amount', 'payable_amount', 'balance_amount', 'payment_status'])


# New signal for OPDBill
@receiver([post_save, post_delete], sender=OPDBill)
def update_visit_payment_status(sender, instance, **kwargs):
    """
    Signal to update the associated Visit's payment status and total/paid amounts
    whenever an OPDBill is saved or deleted.
    """
    if instance.visit:
        visit = instance.visit

        # Calculate aggregated amounts from all OPDBills associated with this visit
        bill_aggregates = OPDBill.objects.filter(visit=visit).aggregate(
            total_amount_sum=Sum('total_amount'),
            received_amount_sum=Sum('received_amount')
        )

        # Update visit's total and paid amounts
        visit.total_amount = bill_aggregates['total_amount_sum'] or Decimal('0.00')
        visit.paid_amount = bill_aggregates['received_amount_sum'] or Decimal('0.00')

        # Update payment status (this method calls save() on the Visit)
        visit.update_payment_status()

