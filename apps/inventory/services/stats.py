"""Inventory statistics service functions.

Extracted from ``InventoryDashboardViewSet.stats`` and
``StockAlertViewSet.summary`` so both the original endpoints and the
consolidated dashboard endpoint share one implementation.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django.db.models import Count, F, Sum
from django.utils import timezone

EXPIRY_WARNING_DAYS = 90  # keep in sync with apps.inventory.views


def compute_dashboard_stats(tenant_id: Any) -> dict:
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

    today = timezone.now().date()
    expiry_cutoff = today + datetime.timedelta(days=EXPIRY_WARNING_DAYS)

    items = InventoryItem.objects.filter(tenant_id=tenant_id)

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
    expiring_soon_count = batches.filter(
        expiry_date__lte=expiry_cutoff,
        expiry_date__gte=today,
        remaining_quantity__gt=0,
    ).count()
    expired_count = batches.filter(
        expiry_date__lt=today, remaining_quantity__gt=0
    ).count()

    total_categories = InventoryCategory.objects.filter(
        tenant_id=tenant_id, is_active=True
    ).count()

    alerts = StockAlert.objects.filter(tenant_id=tenant_id)
    active_alerts = alerts.filter(is_active=True).count()
    unacknowledged_alerts = alerts.filter(is_active=True, is_acknowledged=False).count()

    total_stock_value = (
        items.filter(is_active=True)
        .aggregate(v=Sum(F("current_stock") * F("purchase_price")))["v"]
        or Decimal("0.00")
    )

    recent_transactions = StockTransaction.objects.filter(
        tenant_id=tenant_id
    ).select_related("item", "batch").order_by("-created_at")[:10]

    return {
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


def compute_alerts_summary(tenant_id: Any) -> dict:
    """Active stock alert counts by type.

    Returns the ``data`` dict of ``GET /api/inventory/alerts/summary/``.
    """
    from apps.inventory.models import StockAlert

    qs = StockAlert.objects.filter(tenant_id=tenant_id, is_active=True)
    counts = qs.values("alert_type").annotate(count=Count("id"))
    result = {row["alert_type"]: row["count"] for row in counts}
    total = sum(result.values())
    unacknowledged = qs.filter(is_acknowledged=False).count()
    return {
        "total":          total,
        "unacknowledged": unacknowledged,
        "by_type":        result,
    }
