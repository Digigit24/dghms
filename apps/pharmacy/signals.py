from asyncio.log import logger
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import PharmacyOrder
from apps.payments.models import Transaction, PaymentCategory

@receiver(post_save, sender=PharmacyOrder)
def create_pharmacy_transaction(sender, instance, created, **kwargs):
    if created and instance.total_amount > 0:
        try:
            pharmacy_category, _ = PaymentCategory.objects.get_or_create(
                name='Pharmacy Sales',
                defaults={
                    'category_type': 'income',
                    'description': 'Income from pharmacy product sales'
                }
            )

            Transaction.objects.create(
                amount=instance.total_amount,
                category=pharmacy_category,
                transaction_type='payment',
                payment_method=instance.payment_status or 'other',
                user=instance.user,
                content_type=ContentType.objects.get_for_model(PharmacyOrder),
                object_id=instance.id,
                description=f"Pharmacy Order {instance.id}"
            )
        except Exception as e:
            logger.error(f"Failed to create transaction for order {instance.id}: {e}")


