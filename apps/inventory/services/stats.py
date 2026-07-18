"""Inventory statistics service functions.

Extracted from ``InventoryDashboardViewSet.stats`` and
``StockAlertViewSet.summary`` so both the original endpoints and the
consolidated dashboard endpoint share one implementation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Count, F, Sum
from django.utils import timezone

def _filter_by_tags(queryset, tags, field_prefix=""):
    for tag in tags or []:
        queryset = queryset.filter(**{f"{field_prefix}tags__contains": tag})
    return queryset


def compute_dashboard_stats(tenant_id: Any, tags=None) -> dict:
    """Aggregate inventory dashboard statistics.

    Returns the ``data`` dict of ``GET /api/inventory/dashboard/stats/``.
    """
    from apps.inventory.models import (
        InventoryBatch,
        InventoryCategory,
        InventoryItem,
        StockAlert,
        StockTransaction,
    )
    from apps.inventory.serializers import StockTransactionSerializer
    from apps.inventory.services.expiry import (
        get_tenant_default_expiry_alert_days,
        resolve_expiry_alert_days,
    )

    today = timezone.now().date()
    tenant_default = get_tenant_default_expiry_alert_days(tenant_id)

    items = InventoryItem.objects.filter(tenant_id=tenant_id)
    items = _filter_by_tags(items, tags)

    total_items = items.count()
    active_items = items.filter(is_active=True).count()
    low_stock_count = items.filter(
        is_active=True, current_stock__lte=F("reorder_level"), current_stock__gt=0
    ).count()
    out_of_stock_count = items.filter(is_active=True, current_stock__lte=0).count()
    overstock_count = items.filter(
        is_active=True, max_stock_level__gt=0, current_stock__gt=F("max_stock_level")
    ).count()

    batches = InventoryBatch.objects.filter(tenant_id=tenant_id, is_active=True)
    batches = _filter_by_tags(batches, tags, "item__")
    expiring_batches = batches.filter(
        expiry_date__gte=today,
        expiry_date__isnull=False,
        remaining_quantity__gt=0,
    ).select_related("item__category")
    expiring_soon_count = sum(
        1
        for batch in expiring_batches
        if (batch.expiry_date - today).days
        <= resolve_expiry_alert_days(batch.item, tenant_default)
    )
    expired_count = batches.filter(
        expiry_date__lt=today, remaining_quantity__gt=0
    ).count()

    categories = InventoryCategory.objects.filter(tenant_id=tenant_id, is_active=True)
    if tags:
        categories = categories.filter(
            id__in=items.filter(category_id__isnull=False).values("category_id")
        )
    total_categories = categories.count()

    alerts = StockAlert.objects.filter(tenant_id=tenant_id)
    alerts = _filter_by_tags(alerts, tags, "item__")
    active_alerts = alerts.filter(is_active=True).count()
    unacknowledged_alerts = alerts.filter(is_active=True, is_acknowledged=False).count()

    total_stock_value = (
        items.filter(is_active=True)
        .aggregate(v=Sum(F("current_stock") * F("purchase_price")))["v"]
        or Decimal("0.00")
    )

    recent_transactions = StockTransaction.objects.filter(
        tenant_id=tenant_id
    )
    recent_transactions = _filter_by_tags(recent_transactions, tags, "item__")
    recent_transactions = recent_transactions.select_related("item", "batch").order_by("-created_at")[:10]

    return {
        "has_inventory_items": bool(total_items),
        "total_items":           total_items,
        "active_items":          active_items,
        "low_stock_count":       low_stock_count,
        "out_of_stock_count":    out_of_stock_count,
        "overstock_count":       overstock_count,
        "expiring_soon_count":   expiring_soon_count,
        "expired_count":         expired_count,
        "total_categories":      total_categories,
        "active_alerts":         active_alerts,
        "unacknowledged_alerts": unacknowledged_alerts,
        "total_stock_value":     str(total_stock_value),
        "recent_transactions":   StockTransactionSerializer(recent_transactions, many=True).data,
    }


def compute_alerts_summary(tenant_id: Any, tags=None) -> dict:
    """Active stock alert counts by type.

    Returns the ``data`` dict of ``GET /api/inventory/alerts/summary/``.
    """
    from apps.inventory.models import StockAlert

    qs = StockAlert.objects.filter(tenant_id=tenant_id, is_active=True)
    qs = _filter_by_tags(qs, tags, "item__")
    counts = qs.values("alert_type").annotate(count=Count("id"))
    result = {row["alert_type"]: row["count"] for row in counts}
    total = sum(result.values())
    unacknowledged = qs.filter(is_acknowledged=False).count()
    return {
        "total":          total,
        "unacknowledged": unacknowledged,
        "by_type":        result,
    }
