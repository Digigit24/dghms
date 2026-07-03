"""Pharmacy statistics service functions.

Extracted from ``PharmacyProductViewSet.statistics`` and
``PharmacyOrderViewSet.statistics`` so both the original endpoints and the
consolidated dashboard endpoint share one implementation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from django.db.models import F, QuerySet, Sum
from django.utils import timezone


def compute_product_statistics(
    tenant_id: Any,
    queryset: Optional[QuerySet] = None,
) -> dict:
    """Aggregate pharmacy product statistics.

    Returns the ``data`` dict of ``GET /api/pharmacy/products/statistics/``.

    When ``queryset`` is omitted, the default matches the endpoint's default
    behaviour (tenant-scoped, active products only — the viewset's
    ``get_queryset`` filters ``is_active=True`` unless ``include_inactive``
    is passed).
    """
    from apps.pharmacy.models import PharmacyProduct, ProductCategory

    if queryset is None:
        queryset = PharmacyProduct.objects.filter(tenant_id=tenant_id, is_active=True)

    today = timezone.now().date()

    return {
        'total_products': queryset.count(),
        'active_products': queryset.filter(is_active=True).count(),
        'inactive_products': queryset.filter(is_active=False).count(),
        'in_stock_products': queryset.filter(quantity__gt=0, is_active=True).count(),
        'out_of_stock_products': queryset.filter(quantity=0, is_active=True).count(),
        'low_stock_products': queryset.filter(
            quantity__lte=F('minimum_stock_level'),
            quantity__gt=0,
            is_active=True
        ).count(),
        'near_expiry_products': queryset.filter(
            expiry_date__lte=today + timedelta(days=90),
            expiry_date__gte=today,
            is_active=True
        ).count(),
        'expired_products': queryset.filter(
            expiry_date__lt=today
        ).count(),
        'categories': ProductCategory.objects.filter(
            tenant_id=tenant_id, is_active=True
        ).count(),
    }


def compute_order_statistics(tenant_id: Any) -> dict:
    """Aggregate pharmacy order statistics.

    Returns the ``data`` dict of ``GET /api/pharmacy/orders/statistics/``.
    """
    from apps.pharmacy.models import PharmacyOrder

    queryset = PharmacyOrder.objects.filter(tenant_id=tenant_id)

    return {
        'total_orders': queryset.count(),
        'pending_orders': queryset.filter(status='pending').count(),
        'processing_orders': queryset.filter(status='processing').count(),
        'shipped_orders': queryset.filter(status='shipped').count(),
        'delivered_orders': queryset.filter(status='delivered').count(),
        'cancelled_orders': queryset.filter(status='cancelled').count(),
        'total_spent': queryset.filter(
            payment_status='paid'
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
    }
