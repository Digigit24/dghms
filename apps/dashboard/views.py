"""Consolidated dashboard endpoint.

Replaces ~13 separate frontend calls with a single response. Every section
value is byte-for-byte the same shape as the ``data`` payload of the
corresponding standalone endpoint (the frontend slices this response into its
existing typed hooks), computed via the shared per-app service functions —
never by duplicating query logic here.

The fast-polling live OPD queue endpoint (``/api/opd/visits/queue/``) is
intentionally NOT bundled here.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Optional

import structlog
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.cache import CeliyoCache
from common.permissions import IsTenantAuthenticated, check_permission

log = structlog.get_logger(__name__)

SUMMARY_CACHE_TTL = 60  # seconds


def _parse_date(value: Optional[str]) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class DashboardSummaryView(APIView):
    """GET /api/dashboard/summary/ — all dashboard statistics in one call."""

    permission_classes = [IsTenantAuthenticated]

    @extend_schema(
        summary="Consolidated dashboard summary",
        description=(
            "Returns every dashboard statistics block in a single response. "
            "Each key under `data` has exactly the same shape as the `data` "
            "payload of the corresponding standalone endpoint: "
            "`opd_statistics` (/opd/visits/statistics/), "
            "`opd_doctor_stats` (/opd/visits/doctor_stats/), "
            "`opd_bill_stats` (/opd/bills/statistics/), "
            "`ipd_statistics` (/ipd/admissions/statistics/), "
            "`ipd_billing_stats` (/ipd/billings/statistics/), "
            "`ipd_doctor_stats` (/ipd/admissions/doctor_stats/), "
            "`payment_stats` (/payments/transactions/statistics/), "
            "`pharmacy_product_stats` (/pharmacy/products/statistics/), "
            "`pharmacy_order_stats` (/pharmacy/orders/statistics/), "
            "`inventory_dashboard` (/inventory/dashboard/stats/), "
            "`inventory_alerts` (/inventory/alerts/summary/), "
            "`patient_statistics` (/patients/statistics/), "
            "`appointments_today` (/appointments/appointments/today/). "
            "If a section fails to compute, its key is null and the rest of "
            "the response is still returned. Cached in Redis for 60 seconds "
            "per tenant + date range. The live OPD queue endpoint stays "
            "separate and is not included."
        ),
        parameters=[
            OpenApiParameter(
                name='date_from', type=str, required=False,
                description=(
                    "Range start YYYY-MM-DD. Defaults: today for OPD/IPD "
                    "doctor stats and OPD visit statistics; last 30 days for "
                    "OPD bill statistics; all-time for IPD admission and "
                    "payment statistics."
                ),
            ),
            OpenApiParameter(
                name='date_to', type=str, required=False,
                description="Range end YYYY-MM-DD (defaults to date_from / today).",
            ),
        ],
        responses={200: OpenApiResponse(description="Consolidated dashboard summary")},
        tags=['Dashboard'],
    )
    def get(self, request):
        tenant_id = request.tenant_id

        date_from = _parse_date(request.query_params.get('date_from'))
        date_to = _parse_date(request.query_params.get('date_to'))
        if date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from

        cache_key = (
            f"dashboard:summary:{tenant_id}"
            f":{date_from or 'today'}:{date_to or 'today'}"
        )
        cache = CeliyoCache()
        try:
            cached = cache.get(cache_key)
        except Exception as exc:
            log.warning(
                "dashboard_summary_cache_read_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )
            cached = None
        if cached is not None:
            return Response(cached)

        today = datetime.date.today()
        # Defaults per section mirror each standalone endpoint's defaults.
        range_start = date_from or today
        range_end = date_to or range_start
        bill_start = date_from or (today - datetime.timedelta(days=30))

        def section(name: str, fn: Callable[[], Any]) -> Any:
            """Compute one dashboard section; on failure log and return None."""
            try:
                return fn()
            except Exception as exc:
                log.error(
                    "dashboard_section_failed",
                    tenant_id=str(tenant_id),
                    section=name,
                    error=str(exc),
                    exc_info=True,
                )
                return None

        from apps.appointments.services.stats import (
            base_appointment_queryset,
            compute_today_appointments,
        )
        from apps.inventory.services.stats import (
            compute_alerts_summary,
            compute_dashboard_stats,
        )
        from apps.ipd.services.stats import (
            compute_admission_statistics,
            compute_billing_statistics,
            compute_ipd_doctor_stats,
        )
        from apps.opd.services.stats import (
            compute_bill_statistics,
            compute_doctor_stats,
            compute_visit_statistics,
        )
        from apps.patients.services.stats import compute_patient_statistics
        from apps.payments.services.stats import (
            compute_transaction_statistics,
            tenant_transaction_queryset,
        )
        from apps.pharmacy.services.stats import (
            compute_order_statistics,
            compute_product_statistics,
        )

        data = {
            'generated_at': timezone.now().isoformat(),
            'opd_statistics': section(
                'opd_statistics',
                lambda: compute_visit_statistics(tenant_id, range_start, range_end),
            ),
            'opd_doctor_stats': section(
                'opd_doctor_stats',
                lambda: compute_doctor_stats(tenant_id, range_start, range_end),
            ),
            'opd_bill_stats': section(
                'opd_bill_stats',
                lambda: compute_bill_statistics(tenant_id, bill_start, date_to),
            ),
            'ipd_statistics': section(
                'ipd_statistics',
                lambda: compute_admission_statistics(tenant_id, date_from, date_to),
            ),
            'ipd_billing_stats': section(
                'ipd_billing_stats',
                lambda: compute_billing_statistics(tenant_id),
            ),
            'ipd_doctor_stats': section(
                'ipd_doctor_stats',
                lambda: compute_ipd_doctor_stats(tenant_id, range_start, range_end),
            ),
            'payment_stats': section(
                'payment_stats',
                lambda: compute_transaction_statistics(
                    tenant_transaction_queryset(tenant_id, date_from, date_to)
                ),
            ),
            'pharmacy_product_stats': section(
                'pharmacy_product_stats',
                lambda: compute_product_statistics(tenant_id),
            ),
            'pharmacy_order_stats': section(
                'pharmacy_order_stats',
                lambda: compute_order_statistics(tenant_id),
            ),
            'inventory_dashboard': section(
                'inventory_dashboard',
                lambda: compute_dashboard_stats(tenant_id),
            ),
            'inventory_alerts': section(
                'inventory_alerts',
                lambda: compute_alerts_summary(tenant_id),
            ),
            'patient_statistics': section(
                'patient_statistics',
                lambda: compute_patient_statistics(tenant_id),
            ),
            'appointments_today': section(
                'appointments_today',
                lambda: compute_today_appointments(
                    base_appointment_queryset(tenant_id),
                    context={'request': request},
                ),
            ),
        }

        result = {'success': True, 'data': data}
        try:
            cache.set(cache_key, result, ttl=SUMMARY_CACHE_TTL)
        except Exception as exc:
            log.warning(
                "dashboard_summary_cache_write_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )
        return Response(result)


def _positive_int(value: Optional[str], default: int, max_value: Optional[int] = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(parsed, 1)
    if max_value is not None:
        parsed = min(parsed, max_value)
    return parsed


def _patient_name(patient) -> str:
    if patient is None:
        return ""
    full_name = getattr(patient, "full_name", "")
    if full_name:
        return full_name
    parts = [
        getattr(patient, "first_name", ""),
        getattr(patient, "middle_name", ""),
        getattr(patient, "last_name", ""),
    ]
    return " ".join(part for part in parts if part).strip()


def _doctor_name(doctor) -> str:
    if doctor is None:
        return ""
    first_last = " ".join(
        part
        for part in [
            getattr(doctor, "first_name", ""),
            getattr(doctor, "last_name", ""),
        ]
        if part
    ).strip()
    if first_last:
        return first_last
    return (
        getattr(doctor, "full_name", "")
        or getattr(doctor, "name", "")
        or str(getattr(doctor, "user_id", "") or "")
    )


def _can_view_recent_encounters(request) -> bool:
    """Allow the shared card for patient, pharmacy, or diagnostics users."""
    allowed_permissions = (
        "hms.patients.view",
        "hms.pharmacy.view",
        "hms.diagnostics.view",
    )
    return any(check_permission(request, key) for key in allowed_permissions)


class RecentEncountersView(APIView):
    """GET /api/dashboard/recent-encounters/ — combined OPD/IPD encounter list."""

    permission_classes = [IsTenantAuthenticated]

    @extend_schema(
        summary="Recent OPD/IPD encounters",
        description=(
            "Tenant-scoped combined encounter feed for pharmacy/lab dashboards. "
            "Rows include encounter_type, encounter_id, patient_id, patient_name, "
            "number, doctor_name, date, and status."
        ),
        parameters=[
            OpenApiParameter(name="search", type=str, required=False),
            OpenApiParameter(name="date_from", type=str, required=False),
            OpenApiParameter(name="date_to", type=str, required=False),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={200: OpenApiResponse(description="Combined recent encounters")},
        tags=["Dashboard"],
    )
    def get(self, request):
        if not _can_view_recent_encounters(request):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": "No permission to view recent encounters.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant_id = request.tenant_id
        today = datetime.date.today()
        date_from = _parse_date(request.query_params.get("date_from")) or (
            today - datetime.timedelta(days=30)
        )
        date_to = _parse_date(request.query_params.get("date_to")) or today
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        search = (request.query_params.get("search") or "").strip()
        page = _positive_int(request.query_params.get("page"), 1)
        page_size = _positive_int(request.query_params.get("page_size"), 25, 100)

        from apps.doctors.models import DoctorProfile
        from apps.ipd.models import Admission
        from apps.opd.models import Visit

        opd_qs = Visit.objects.filter(
            tenant_id=tenant_id,
            visit_date__gte=date_from,
            visit_date__lte=date_to,
        ).select_related("patient", "doctor")
        if search:
            opd_qs = opd_qs.filter(
                Q(visit_number__icontains=search)
                | Q(patient__patient_id__icontains=search)
                | Q(patient__first_name__icontains=search)
                | Q(patient__middle_name__icontains=search)
                | Q(patient__last_name__icontains=search)
                | Q(patient__mobile_primary__icontains=search)
            )

        ipd_qs = Admission.objects.filter(
            tenant_id=tenant_id,
            admission_date__date__gte=date_from,
            admission_date__date__lte=date_to,
        ).select_related("patient")
        if search:
            ipd_qs = ipd_qs.filter(
                Q(admission_id__icontains=search)
                | Q(patient__patient_id__icontains=search)
                | Q(patient__first_name__icontains=search)
                | Q(patient__middle_name__icontains=search)
                | Q(patient__last_name__icontains=search)
                | Q(patient__mobile_primary__icontains=search)
            )

        doctor_ids = [admission.doctor_id for admission in ipd_qs if admission.doctor_id]
        ipd_doctors = {
            doctor.user_id: doctor
            for doctor in DoctorProfile.objects.filter(
                tenant_id=tenant_id,
                user_id__in=doctor_ids,
            )
        }

        rows = []
        for visit in opd_qs:
            visit_date = visit.visit_date
            rows.append(
                {
                    "_sort_date": visit_date,
                    "encounter_type": "opd",
                    "encounter_id": visit.id,
                    "patient_id": visit.patient_id,
                    "patient_name": _patient_name(visit.patient),
                    "number": visit.visit_number,
                    "doctor_name": _doctor_name(visit.doctor),
                    "date": visit_date.isoformat() if visit_date else None,
                    "status": visit.status,
                }
            )

        for admission in ipd_qs:
            admission_dt = admission.admission_date
            sort_date = admission_dt.date() if hasattr(admission_dt, "date") else admission_dt
            rows.append(
                {
                    "_sort_date": sort_date,
                    "encounter_type": "ipd",
                    "encounter_id": admission.id,
                    "patient_id": admission.patient_id,
                    "patient_name": _patient_name(admission.patient),
                    "number": admission.admission_id,
                    "doctor_name": _doctor_name(ipd_doctors.get(admission.doctor_id)),
                    "date": admission_dt.isoformat() if admission_dt else None,
                    "status": admission.status,
                }
            )

        rows.sort(key=lambda row: row["_sort_date"] or datetime.date.min, reverse=True)
        count = len(rows)
        start = (page - 1) * page_size
        paged_rows = rows[start : start + page_size]
        for row in paged_rows:
            row.pop("_sort_date", None)

        return Response(
            {
                "success": True,
                "data": {
                    "results": paged_rows,
                    "count": count,
                    "page": page,
                    "page_size": page_size,
                },
            }
        )
