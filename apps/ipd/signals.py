# ipd/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import IPDBillItem

@receiver([post_save, post_delete], sender=IPDBillItem)
def update_ipd_bill_totals(sender, instance, **kwargs):
    """
    Signal to update the parent IPDBilling's totals whenever an
    IPDBillItem is saved or deleted.
    """
    if instance.billing:
        instance.billing.calculate_totals()
        instance.billing.save()
