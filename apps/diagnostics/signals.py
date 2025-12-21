# diagnostics/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal

from .models import DiagnosticOrder, MedicineOrder, ProcedureOrder, PackageOrder


def create_or_update_bill_item(order_instance, item_name, source):
    """
    Helper function to create or update OPDBillItem or IPDBillItem based on the order.

    Args:
        order_instance: Instance of *Order model (DiagnosticOrder, MedicineOrder, etc.)
        item_name: Name of the item for the bill
        source: Source category for the bill item
    """
    # Only proceed if status is 'completed' and content_object is set
    if order_instance.status != 'completed' or not order_instance.content_object:
        return

    # Check if the content_object is an OPDBillItem or IPDBillItem
    from apps.opd.models import ProcedureBillItem
    from apps.ipd.models import IPDBillItem

    bill_item = order_instance.content_object
    bill_item_type = type(bill_item)

    # Calculate totals
    quantity = getattr(order_instance, 'quantity', 1)
    unit_price = order_instance.price
    total_price = Decimal(str(quantity)) * unit_price

    # Update the bill item
    if bill_item_type == ProcedureBillItem:
        # OPD Bill Item (ProcedureBillItem)
        bill_item.particular_name = item_name
        bill_item.quantity = quantity
        bill_item.unit_charge = unit_price
        bill_item.amount = total_price
        bill_item.save()

    elif bill_item_type == IPDBillItem:
        # IPD Bill Item
        bill_item.item_name = item_name
        bill_item.source = source
        bill_item.quantity = quantity
        bill_item.unit_price = unit_price
        bill_item.total_price = total_price
        bill_item.save()


@receiver(post_save, sender=DiagnosticOrder)
def diagnostic_order_post_save(sender, instance, created, **kwargs):
    """
    Signal receiver for DiagnosticOrder post_save.
    Creates/updates OPDBillItem or IPDBillItem when status='completed' and content_object is set.
    """
    if instance.status == 'completed' and instance.content_object:
        item_name = f"{instance.investigation.name}"
        create_or_update_bill_item(instance, item_name, 'Lab')


@receiver(post_save, sender=MedicineOrder)
def medicine_order_post_save(sender, instance, created, **kwargs):
    """
    Signal receiver for MedicineOrder post_save.
    Creates/updates OPDBillItem or IPDBillItem when status='completed' and content_object is set.
    """
    if instance.status == 'completed' and instance.content_object:
        item_name = f"{instance.product.product_name} x{instance.quantity}"
        create_or_update_bill_item(instance, item_name, 'Pharmacy')


@receiver(post_save, sender=ProcedureOrder)
def procedure_order_post_save(sender, instance, created, **kwargs):
    """
    Signal receiver for ProcedureOrder post_save.
    Creates/updates OPDBillItem or IPDBillItem when status='completed' and content_object is set.
    """
    if instance.status == 'completed' and instance.content_object:
        item_name = f"{instance.procedure.name} x{instance.quantity}"
        create_or_update_bill_item(instance, item_name, 'Procedure')


@receiver(post_save, sender=PackageOrder)
def package_order_post_save(sender, instance, created, **kwargs):
    """
    Signal receiver for PackageOrder post_save.
    Creates/updates OPDBillItem or IPDBillItem when status='completed' and content_object is set.
    """
    if instance.status == 'completed' and instance.content_object:
        item_name = f"{instance.package.name} (Package) x{instance.quantity}"
        create_or_update_bill_item(instance, item_name, 'Procedure')
