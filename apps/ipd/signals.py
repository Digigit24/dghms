# ipd/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from decimal import Decimal
from .models import IPDBillItem, IPDBilling

@receiver([post_save, post_delete], sender=IPDBillItem)
def update_ipd_bill_totals(sender, instance, **kwargs):
    """
    Signal to update the parent IPDBilling's totals whenever an
    IPDBillItem is saved or deleted.
    """
    if instance.bill:
        # The save() method will call _calculate_derived_totals() automatically
        # Just trigger a save to recalculate totals
        instance.bill.save(update_fields=['total_amount', 'discount_amount', 'payable_amount', 'balance_amount', 'payment_status'])


# New signal for IPDBilling
@receiver([post_save, post_delete], sender=IPDBilling)
def update_admission_payment_status(sender, instance, **kwargs):
    """
    Signal to update the associated Admission's payment status and total/paid amounts
    whenever an IPDBilling is saved or deleted.

    Note: Admission model needs total_amount, paid_amount, and payment_status fields.
    """
    if instance.admission:
        admission = instance.admission

        # Calculate aggregated amounts from all IPDBillings associated with this admission
        bill_aggregates = IPDBilling.objects.filter(admission=admission).aggregate(
            total_amount_sum=Sum('total_amount'),
            received_amount_sum=Sum('received_amount')
        )

        # Update admission's total and paid amounts (if these fields exist)
        if hasattr(admission, 'total_amount'):
            admission.total_amount = bill_aggregates['total_amount_sum'] or Decimal('0.00')
        if hasattr(admission, 'paid_amount'):
            admission.paid_amount = bill_aggregates['received_amount_sum'] or Decimal('0.00')

        # Update payment status if the model has update_payment_status method
        if hasattr(admission, 'update_payment_status'):
            admission.update_payment_status()
        elif hasattr(admission, 'payment_status'):
            # Manual payment status calculation if no method exists
            if hasattr(admission, 'total_amount') and hasattr(admission, 'paid_amount'):
                if admission.paid_amount >= admission.total_amount and admission.total_amount > 0:
                    admission.payment_status = 'paid'
                elif admission.paid_amount > 0:
                    admission.payment_status = 'partial'
                else:
                    admission.payment_status = 'unpaid'
                admission.save()
