# ipd/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
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
        instance.bill.save(update_fields=['total_amount', 'discount_amount', 'payable_amount', 'balance_amount', 'payment_status', 'paid_transition_at'])


# New signal for IPDBilling
@receiver([post_save, post_delete], sender=IPDBilling)
def update_admission_payment_status(sender, instance, **kwargs):
    """
    Recompute the associated Admission's billing rollup fields (total_charges,
    total_advance_paid, advance_applied, advance_balance, total_received,
    balance_due) whenever an IPDBilling is saved or deleted.

    Re-fetches the Admission rather than using instance.admission directly:
    instance.admission may be a stale cached object from before this bill's
    change if the caller accessed it earlier in the same request, and
    recompute_billing_rollup() only needs the pk anyway.
    """
    admission_id = instance.admission_id
    if not admission_id:
        return

    from .models import Admission

    admission = Admission.objects.filter(pk=admission_id).first()
    if admission:
        admission.recompute_billing_rollup()
