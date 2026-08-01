"""Pharmacy statistics service functions.

Extracted from ``PharmacyProductViewSet.statistics`` and
``PharmacyOrderViewSet.statistics`` so both the original endpoints and the
consolidated dashboard endpoint share one implementation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from django.db.models import Count, F, Q, QuerySet, Sum
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

    totals = queryset.aggregate(
        total_products=Count('id'),
        active_products=Count('id', filter=Q(is_active=True)),
        inactive_products=Count('id', filter=Q(is_active=False)),
        in_stock_products=Count('id', filter=Q(quantity__gt=0, is_active=True)),
        out_of_stock_products=Count('id', filter=Q(quantity=0, is_active=True)),
        low_stock_products=Count('id', filter=Q(
            quantity__lte=F('minimum_stock_level'), quantity__gt=0, is_active=True,
        )),
        near_expiry_products=Count('id', filter=Q(
            expiry_date__lte=today + timedelta(days=90),
            expiry_date__gte=today,
            is_active=True,
        )),
        expired_products=Count('id', filter=Q(expiry_date__lt=today)),
    )
    return {
        **totals,
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

    return queryset.aggregate(
        total_orders=Count('id'),
        pending_orders=Count('id', filter=Q(status='pending')),
        processing_orders=Count('id', filter=Q(status='processing')),
        shipped_orders=Count('id', filter=Q(status='shipped')),
        delivered_orders=Count('id', filter=Q(status='delivered')),
        cancelled_orders=Count('id', filter=Q(status='cancelled')),
        total_spent=Sum('total_amount', filter=Q(payment_status='paid'), default=0),
    )
