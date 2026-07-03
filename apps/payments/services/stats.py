"""Payments / transaction statistics service functions.

Extracted from ``TransactionViewSet.statistics`` so both the original
endpoint and the consolidated dashboard endpoint share one implementation.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from django.db.models import Count, Q, QuerySet, Sum


def tenant_transaction_queryset(
    tenant_id: Any,
    date_from: Optional[datetime.date] = None,
    date_to: Optional[datetime.date] = None,
) -> QuerySet:
    """Tenant-scoped Transaction queryset with optional date-range filtering.

    Mirrors the date filtering applied by ``TransactionViewSet.get_queryset``.
    """
    from apps.payments.models import Transaction

    queryset = Transaction.objects.filter(tenant_id=tenant_id)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    return queryset


def compute_transaction_statistics(queryset: QuerySet) -> dict:
    """Aggregate transaction statistics over a (pre-scoped) queryset.

    Returns the ``data`` dict of ``GET /api/payments/transactions/statistics/``.
    The caller is responsible for tenant scoping (and any ownership scoping).
    """
    stats = queryset.aggregate(
        total_transactions=Count('id'),
        total_amount=Sum('amount'),
        total_payments=Sum('amount', filter=Q(transaction_type='payment')),
        total_expenses=Sum('amount', filter=Q(transaction_type='expense')),
        total_refunds=Sum('amount', filter=Q(transaction_type='refund'))
    )

    # Payment method breakdown
    payment_method_breakdown = queryset.values('payment_method').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    )

    # Transaction type breakdown
    transaction_type_breakdown = queryset.values('transaction_type').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    )

    return {
        'overall_stats': {
            'total_transactions': stats['total_transactions'],
            'total_amount': float(stats['total_amount'] or 0),
            'total_payments': float(stats['total_payments'] or 0),
            'total_expenses': float(stats['total_expenses'] or 0),
            'total_refunds': float(stats['total_refunds'] or 0)
        },
        'payment_method_breakdown': list(payment_method_breakdown),
        'transaction_type_breakdown': list(transaction_type_breakdown)
    }
