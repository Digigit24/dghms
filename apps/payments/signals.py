"""
Signal handlers for the payments app.

Automatically creates transaction records when bills are marked as paid.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from decimal import Decimal


@receiver(post_save, sender='opd.OPDBill')
def create_transaction_for_opd_bill(sender, instance, created, **kwargs):
    """
    Auto-create transaction when OPD bill payment_status becomes 'paid'.

    Triggered after:
    - OPD bill is created with payment_status='paid'
    - OPD bill is updated and payment_status changes to 'paid'
    """
    from apps.payments.models import Transaction, PaymentCategory

    # Only create transaction if bill is paid and received_amount > 0
    if instance.payment_status == 'paid' and instance.received_amount > 0:
        # Check if transaction already exists for this bill
        content_type = ContentType.objects.get_for_model(instance)
        existing_transaction = Transaction.objects.filter(
            content_type=content_type,
            object_id=instance.id,
            tenant_id=instance.tenant_id
        ).exists()

        if not existing_transaction:
            # Get or create OPD consultation income category
            category, _ = PaymentCategory.objects.get_or_create(
                tenant_id=instance.tenant_id,
                name='OPD Consultation',
                defaults={
                    'category_type': 'income',
                    'description': 'Income from OPD consultations'
                }
            )

            # Map bill payment_mode to transaction payment_method
            payment_method_mapping = {
                'cash': 'cash',
                'card': 'card',
                'upi': 'upi',
                'bank': 'net_banking',
                'multiple': 'other',
            }
            payment_method = payment_method_mapping.get(
                instance.payment_mode,
                'cash'
            )

            # Create transaction
            Transaction.objects.create(
                tenant_id=instance.tenant_id,
                amount=instance.received_amount,
                category=category,
                transaction_type='payment',
                payment_method=payment_method,
                content_type=content_type,
                object_id=instance.id,
                user_id=instance.billed_by_id,
                description=f"OPD Bill Payment: {instance.bill_number} - {instance.visit.patient.full_name if instance.visit and instance.visit.patient else 'Unknown Patient'}"
            )


@receiver(post_save, sender='payments.Transaction')
def log_transaction_creation(sender, instance, created, **kwargs):
    """
    Optional: Log when transactions are created for audit purposes.
    """
    if created:
        # Future: Add audit logging or notification logic
        pass


# Optional: Handle partial payments
@receiver(post_save, sender='opd.OPDBill')
def create_transaction_for_partial_opd_payment(sender, instance, **kwargs):
    """
    Create additional transaction when partial payment is received.

    This handles the case where multiple payments are made for the same bill.
    Only creates transaction for the delta amount.
    """
    from apps.payments.models import Transaction, PaymentCategory

    # Only handle partial payments
    if instance.payment_status == 'partial' and instance.received_amount > 0:
        content_type = ContentType.objects.get_for_model(instance)

        # Get sum of existing transactions for this bill
        existing_total = Transaction.objects.filter(
            content_type=content_type,
            object_id=instance.id,
            tenant_id=instance.tenant_id,
            transaction_type='payment'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Calculate delta (new payment amount)
        delta = instance.received_amount - existing_total

        # Only create transaction if there's a positive delta
        if delta > Decimal('0.00'):
            # Get or create OPD consultation income category
            category, _ = PaymentCategory.objects.get_or_create(
                tenant_id=instance.tenant_id,
                name='OPD Consultation',
                defaults={
                    'category_type': 'income',
                    'description': 'Income from OPD consultations'
                }
            )

            payment_method_mapping = {
                'cash': 'cash',
                'card': 'card',
                'upi': 'upi',
                'bank': 'net_banking',
                'multiple': 'other',
            }
            payment_method = payment_method_mapping.get(
                instance.payment_mode,
                'cash'
            )

            Transaction.objects.create(
                tenant_id=instance.tenant_id,
                amount=delta,
                category=category,
                transaction_type='payment',
                payment_method=payment_method,
                content_type=content_type,
                object_id=instance.id,
                user_id=instance.billed_by_id,
                description=f"Partial Payment: {instance.bill_number} - {instance.visit.patient.full_name if instance.visit and instance.visit.patient else 'Unknown Patient'}"
            )

