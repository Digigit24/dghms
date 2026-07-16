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
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common.cache import CeliyoCache
from common.permissions import IsTenantAuthenticated

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
