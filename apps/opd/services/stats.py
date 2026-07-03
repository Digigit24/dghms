"""OPD statistics service functions.

Extracted from ``VisitViewSet.statistics``, ``VisitViewSet.doctor_stats`` and
``OPDBillViewSet.statistics`` so that both the original endpoints and the
consolidated dashboard endpoint (``GET /api/dashboard/summary/``) share a
single implementation. The return value of each function is exactly the
``data`` payload the corresponding endpoint has always returned — do not
change the shape without checking every frontend consumer.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog
from django.db.models import (
    Avg,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
)
from django.db.models.functions import TruncDate

log = structlog.get_logger(__name__)


def compute_visit_statistics(
    tenant_id: Any,
    start_date: datetime.date,
    end_date: datetime.date,
) -> dict:
    """Aggregate OPD visit statistics for a date range.

    Returns the ``data`` dict of ``GET /api/opd/visits/statistics/``.
    """
    from apps.opd.models import Visit

    visits = Visit.objects.filter(
        tenant_id=tenant_id,
        visit_date__gte=start_date,
        visit_date__lte=end_date,
    )

    # Single aggregation query for all monetary stats
    agg = visits.aggregate(
        total_visits=Count('id'),
        waiting=Count('id', filter=Q(status='waiting')),
        in_consultation=Count('id', filter=Q(status='in_consultation')),
        completed=Count('id', filter=Q(status='completed')),
        cancelled=Count('id', filter=Q(status='cancelled')),
        total_revenue=Sum('total_amount'),
        paid_revenue=Sum('paid_amount', filter=Q(payment_status='paid')),
        pending_amount=Sum('balance_amount'),
    )

    # Breakdown queries (separate but lightweight)
    by_type = list(visits.values('visit_type').annotate(count=Count('id')))

    return {
        'total_visits': agg['total_visits'] or 0,
        'by_status': {
            'waiting': agg['waiting'] or 0,
            'in_consultation': agg['in_consultation'] or 0,
            'completed': agg['completed'] or 0,
            'cancelled': agg['cancelled'] or 0,
        },
        'by_type': by_type,
        'total_revenue': agg['total_revenue'] or 0,
        'paid_revenue': agg['paid_revenue'] or 0,
        'pending_amount': agg['pending_amount'] or 0,
    }


def compute_visit_daily_trend(
    tenant_id: Any,
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[dict]:
    """Per-day visit/completed/revenue series for the requested range."""
    from apps.opd.models import Visit

    visits = Visit.objects.filter(
        tenant_id=tenant_id,
        visit_date__gte=start_date,
        visit_date__lte=end_date,
    )

    daily_trend = list(
        visits.annotate(day=TruncDate('visit_date'))
              .values('day')
              .annotate(
                  visits=Count('id'),
                  completed=Count('id', filter=Q(status='completed')),
                  revenue=Sum('total_amount'),
              )
              .order_by('day')
    )
    return [
        {
            'date': str(row['day']),
            'visits': row['visits'] or 0,
            'completed': row['completed'] or 0,
            'revenue': float(row['revenue'] or 0),
        }
        for row in daily_trend
    ]


def compute_doctor_stats(
    tenant_id: Any,
    date_from: datetime.date,
    date_to: datetime.date,
    doctor_id: Optional[int] = None,
) -> list[dict]:
    """Per-doctor OPD visit aggregation for the admin dashboard.

    Returns the ``data`` list of ``GET /api/opd/visits/doctor_stats/``.

    Single-pass version of what used to be an N+1 loop in the viewset:
    the average consultation duration is aggregated in the database, and
    all DoctorProfile rows (with specialties) are fetched in one query.
    """
    from apps.doctors.models import DoctorProfile
    from apps.opd.models import Visit

    qs = Visit.objects.filter(
        tenant_id=tenant_id,
        visit_date__gte=date_from,
        visit_date__lte=date_to,
    )
    if doctor_id is not None:
        qs = qs.filter(doctor_id=doctor_id)

    duration_expr = ExpressionWrapper(
        F('consultation_end_time') - F('consultation_start_time'),
        output_field=DurationField(),
    )

    doctor_rows = list(
        qs.values(
            'doctor',
            _first_name=F('doctor__first_name'),
            _last_name=F('doctor__last_name'),
        ).annotate(
            visits_count=Count('id'),
            waiting=Count('id', filter=Q(status='waiting')),
            in_consultation=Count('id', filter=Q(status='in_consultation')),
            completed=Count('id', filter=Q(status='completed')),
            revenue=Sum('total_amount'),
            _avg_duration=Avg(
                duration_expr,
                filter=Q(
                    consultation_start_time__isnull=False,
                    consultation_end_time__isnull=False,
                    consultation_end_time__gt=F('consultation_start_time'),
                ),
            ),
        ).order_by('-visits_count')
    )

    # IPD active admissions per doctor (always current, independent of range).
    # Admission.doctor_id stores the SuperAdmin user_id (UUID).
    try:
        from apps.ipd.models import Admission

        ipd_rows = (
            Admission.objects
            .filter(tenant_id=tenant_id, status='admitted')
            .values('doctor_id')
            .annotate(ipd_count=Count('id'))
        )
        ipd_map = {str(r['doctor_id']): r['ipd_count'] for r in ipd_rows}
    except Exception as exc:
        log.warning(
            "opd_doctor_stats_ipd_lookup_failed",
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        ipd_map = {}

    # One query for every doctor profile in the result set (was N+1).
    profile_ids = [row['doctor'] for row in doctor_rows if row['doctor'] is not None]
    profile_map = {
        profile.id: profile
        for profile in DoctorProfile.objects.filter(
            tenant_id=tenant_id, id__in=profile_ids
        ).prefetch_related('specialties')
    }

    for row in doctor_rows:
        # Compose full name
        fn = row.pop('_first_name', '') or ''
        ln = row.pop('_last_name', '') or ''
        row['doctor_name'] = f"{fn} {ln}".strip() or f"Doctor #{row['doctor']}"

        # Average consultation minutes (DB-aggregated timedelta -> minutes)
        avg_duration = row.pop('_avg_duration', None)
        row['avg_consultation_mins'] = (
            round(avg_duration.total_seconds() / 60, 1)
            if avg_duration is not None else None
        )

        # Normalise revenue — keep both new and legacy field names
        raw_rev = row.get('revenue')
        row['revenue_today'] = str(raw_rev or '0.00')   # legacy
        row['revenue'] = str(raw_rev or '0.00')

        # Backward-compat alias
        row['visits_today'] = row['visits_count']

        profile = profile_map.get(row['doctor'])
        if profile is not None:
            row['ipd_admissions'] = ipd_map.get(str(profile.user_id), 0)
            row['doctor_specialty'] = (
                ', '.join(s.name for s in profile.specialties.all()) or None
            )
        else:
            row['ipd_admissions'] = 0
            row['doctor_specialty'] = None

    return doctor_rows


def compute_bill_statistics(
    tenant_id: Any,
    start_date: datetime.date,
    end_date: Optional[datetime.date] = None,
) -> dict:
    """Aggregate OPD bill statistics.

    Returns the ``data`` dict of ``GET /api/opd/bills/statistics/``
    (serialized through ``OPDBillStatisticsSerializer``). ``end_date`` is
    only used by the dashboard endpoint; the legacy endpoint filters from
    ``start_date`` onwards only.
    """
    from apps.opd.models import OPDBill
    from apps.opd.serializers import OPDBillStatisticsSerializer

    bills = OPDBill.objects.filter(
        tenant_id=tenant_id,
        bill_date__date__gte=start_date,
    )
    if end_date is not None:
        bills = bills.filter(bill_date__date__lte=end_date)

    total_bills = bills.count()
    bills_paid = bills.filter(payment_status='paid').count()
    bills_partial = bills.filter(payment_status='partial').count()
    bills_unpaid = bills.filter(payment_status='unpaid').count()

    total_revenue = bills.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
    paid_revenue = bills.aggregate(Sum('received_amount'))['received_amount__sum'] or Decimal('0.00')
    pending_amount = bills.aggregate(Sum('balance_amount'))['balance_amount__sum'] or Decimal('0.00')
    total_discount = bills.aggregate(Sum('discount_amount'))['discount_amount__sum'] or Decimal('0.00')
    average_bill_amount = bills.aggregate(Avg('total_amount'))['total_amount__avg'] or Decimal('0.00')

    # Breakdown by OPD type
    by_opd_type = list(bills.values('opd_type').annotate(
        count=Count('id'),
        revenue=Sum('total_amount')
    ))

    # Breakdown by payment mode
    by_payment_mode = list(bills.values('payment_mode').annotate(
        count=Count('id'),
        amount=Sum('received_amount')
    ))

    data = {
        'total_bills': total_bills,
        'total_revenue': total_revenue,
        'paid_revenue': paid_revenue,
        'pending_amount': pending_amount,
        'total_discount': total_discount,
        'bills_paid': bills_paid,
        'bills_partial': bills_partial,
        'bills_unpaid': bills_unpaid,
        'by_opd_type': by_opd_type,
        'by_payment_mode': by_payment_mode,
        'average_bill_amount': round(average_bill_amount, 2),
    }

    return OPDBillStatisticsSerializer(data).data
