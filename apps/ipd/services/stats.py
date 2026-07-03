"""IPD statistics service functions.

Extracted from ``AdmissionViewSet.statistics``, ``AdmissionViewSet.doctor_stats``
and ``IPDBillingViewSet.statistics`` so that both the original endpoints and
the consolidated dashboard endpoint (``GET /api/dashboard/summary/``) share a
single implementation. The return value of each function is exactly the
``data`` payload the corresponding endpoint has always returned.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

import structlog
from django.db.models import Avg, Count, IntegerField, Q, Sum
from django.db.models.expressions import RawSQL
from django.utils import timezone

log = structlog.get_logger(__name__)


def annotated_admission_queryset(tenant_id: Any):
    """Tenant-scoped Admission queryset annotated with ``los_days``.

    Mirrors ``AdmissionViewSet.get_queryset()`` (RawSQL cast keeps the
    PostgreSQL DATE - DATE arithmetic unambiguous → integer days).
    """
    from apps.ipd.models import Admission

    today = timezone.now().date()
    return Admission.objects.filter(tenant_id=tenant_id).annotate(
        los_days=RawSQL(
            "COALESCE(discharge_date::date, %s) - admission_date::date",
            (today,),
            output_field=IntegerField(),
        )
    )


def compute_admission_statistics(
    tenant_id: Any,
    date_from: Optional[datetime.date] = None,
    date_to: Optional[datetime.date] = None,
) -> dict:
    """Aggregate IPD admission statistics (plus live bed occupancy).

    Returns the ``data`` dict of ``GET /api/ipd/admissions/statistics/``.
    When no dates are given, admission counts are all-time; bed occupancy
    is always live.
    """
    from apps.ipd.models import Bed

    today = datetime.date.today()

    qs = annotated_admission_queryset(tenant_id)
    if date_from:
        qs = qs.filter(admission_date__date__gte=date_from)
    if date_to:
        qs = qs.filter(admission_date__date__lte=date_to)

    agg = qs.aggregate(
        total_admissions=Count('id'),
        currently_admitted=Count('id', filter=Q(status='admitted')),
        discharged_today=Count(
            'id',
            filter=Q(status='discharged', discharge_date__date=today)
        ),
        discharged=Count('id', filter=Q(status='discharged')),
        transferred=Count('id', filter=Q(status='transferred')),
        absconded=Count('id', filter=Q(status='absconded')),
        referred=Count('id', filter=Q(status='referred')),
        death=Count('id', filter=Q(status='death')),
        mediclaim=Count('id', filter=Q(has_mediclaim=True)),
        claim_not_started=Count('id', filter=Q(claim_status='not_started')),
        claim_documents_pending=Count('id', filter=Q(claim_status='documents_pending')),
        claim_submitted=Count('id', filter=Q(claim_status='submitted')),
        claim_under_review=Count('id', filter=Q(claim_status='under_review')),
        claim_approved=Count('id', filter=Q(claim_status='approved')),
        claim_rejected=Count('id', filter=Q(claim_status='rejected')),
        claim_settled=Count('id', filter=Q(claim_status='settled')),
    )

    avg_result = qs.filter(
        status='discharged',
        discharge_date__isnull=False,
        admission_date__isnull=False,
    ).aggregate(avg_stay=Avg('los_days'))

    # --- Live bed occupancy (never date-filtered) ---
    bed_agg = Bed.objects.filter(
        tenant_id=tenant_id, is_active=True
    ).aggregate(
        total_beds=Count('id'),
        occupied_beds=Count('id', filter=Q(is_occupied=True)),
        available_beds=Count('id', filter=Q(is_occupied=False, status='available')),
    )
    total_beds = bed_agg['total_beds'] or 0
    occupied_beds = bed_agg['occupied_beds'] or 0
    available_beds = bed_agg['available_beds'] or 0
    occupancy_rate = round(occupied_beds / total_beds * 100, 1) if total_beds > 0 else 0

    return {
        **{k: (v or 0) for k, v in agg.items()},
        'avg_length_of_stay_days': (
            round(avg_result['avg_stay'], 1)
            if avg_result.get('avg_stay') else None
        ),
        # Live bed stats
        'total_beds': total_beds,
        'occupied_beds': occupied_beds,
        'available_beds': available_beds,
        'occupancy_rate': occupancy_rate,
        'by_tpa': list(
            qs.filter(has_mediclaim=True)
            .values('tpa_name')
            .annotate(count=Count('id'))
            .order_by('-count')
        ),
    }


def enrich_doctor_rows(tenant_id: Any, rows: list[dict]) -> list[dict]:
    """Attach doctor name/specialty to per-doctor aggregation rows.

    One DoctorProfile query with prefetched specialties for the whole set
    (Admission.doctor_id stores the SuperAdmin user_id).
    """
    from apps.doctors.models import DoctorProfile

    doctor_ids = [row['doctor_id'] for row in rows if row.get('doctor_id')]
    profiles = (
        DoctorProfile.objects
        .filter(tenant_id=tenant_id, user_id__in=doctor_ids)
        .prefetch_related('specialties')
    )
    profile_map = {str(profile.user_id): profile for profile in profiles}

    for row in rows:
        doctor_key = str(row.get('doctor_id') or '')
        profile = profile_map.get(doctor_key)
        if profile:
            row['doctor_name'] = profile.full_name
            row['doctor_specialty'] = ', '.join(s.name for s in profile.specialties.all()) or None
        else:
            row['doctor_name'] = f"Doctor {doctor_key[:8]}" if doctor_key else "Unassigned"
            row['doctor_specialty'] = None

        avg_stay = row.get('avg_length_of_stay_days')
        row['avg_length_of_stay_days'] = round(float(avg_stay), 1) if avg_stay is not None else None
        row['doctor'] = doctor_key

    return rows


def compute_ipd_doctor_stats(
    tenant_id: Any,
    date_from: datetime.date,
    date_to: datetime.date,
    doctor_user_id: Any = None,
) -> list[dict]:
    """Per-doctor IPD admission statistics.

    Returns the ``data`` list of ``GET /api/ipd/admissions/doctor_stats/``.
    """
    qs = annotated_admission_queryset(tenant_id).filter(
        admission_date__date__gte=date_from,
        admission_date__date__lte=date_to,
    )
    if doctor_user_id is not None:
        qs = qs.filter(doctor_id=doctor_user_id)

    rows = list(
        qs.values('doctor_id').annotate(
            admissions_count=Count('id'),
            active=Count('id', filter=Q(status='admitted')),
            discharged=Count('id', filter=Q(status='discharged')),
            transferred=Count('id', filter=Q(status='transferred')),
            mediclaim_count=Count('id', filter=Q(has_mediclaim=True)),
            claim_pending=Count(
                'id',
                filter=Q(claim_status__in=[
                    'not_started',
                    'documents_pending',
                    'submitted',
                    'under_review',
                ])
            ),
            claim_approved=Count('id', filter=Q(claim_status='approved')),
            claim_rejected=Count('id', filter=Q(claim_status='rejected')),
            claim_settled=Count('id', filter=Q(claim_status='settled')),
            avg_length_of_stay_days=Avg('los_days'),
        ).order_by('-admissions_count')
    )

    return enrich_doctor_rows(tenant_id, rows)


def compute_billing_statistics(
    tenant_id: Any,
    payment_status: Optional[str] = None,
    admission_id: Optional[int] = None,
) -> dict:
    """Aggregate IPD billing statistics.

    Returns the ``data`` dict of ``GET /api/ipd/billings/statistics/``.

    NOTE: IPDBilling.PAYMENT_STATUS_CHOICES is only unpaid/partial/paid —
    'cancelled_amount' has no matching status and always resolves to 0; it is
    kept in the response shape for frontend (IPDBillStats) compatibility.
    The Sum() output alias must never be the same string as the field it
    sums (Django resolves aggregate kwargs by adding each alias into
    query.annotations before resolving its source expression).
    """
    from apps.ipd.models import IPDBilling

    qs = IPDBilling.objects.filter(tenant_id=tenant_id)
    if payment_status:
        qs = qs.filter(payment_status=payment_status)
    if admission_id:
        qs = qs.filter(admission_id=admission_id)

    agg = qs.aggregate(
        total_bills=Count('id'),
        total_amount_sum=Sum('total_amount'),
        paid_amount=Sum('received_amount', filter=Q(payment_status='paid')),
        pending_amount=Sum('balance_amount', filter=Q(payment_status__in=['unpaid', 'partial'])),
        cancelled_amount=Sum('total_amount', filter=Q(payment_status='cancelled')),
    )
    agg['total_amount'] = agg.pop('total_amount_sum')
    for key in ('total_amount', 'paid_amount', 'pending_amount', 'cancelled_amount'):
        if agg[key] is None:
            agg[key] = 0

    return agg
