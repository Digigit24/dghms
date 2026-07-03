"""Appointment service functions.

Extracted from ``AppointmentViewSet.today`` so both the original endpoint and
the consolidated dashboard endpoint share one implementation.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from django.db.models import QuerySet


def base_appointment_queryset(tenant_id: Any) -> QuerySet:
    """Tenant-scoped Appointment queryset with the same select/prefetch as
    ``AppointmentViewSet.queryset`` (no per-row queries when serializing)."""
    from apps.appointments.models import Appointment

    return Appointment.objects.filter(tenant_id=tenant_id).select_related(
        'patient', 'doctor', 'appointment_type', 'original_appointment', 'visit'
    ).prefetch_related('follow_ups')


def compute_today_appointments(
    queryset: QuerySet,
    context: Optional[dict] = None,
) -> list:
    """Today's appointments ordered by time, serialized for the API.

    Returns the ``data`` list of ``GET /api/appointments/appointments/today/``
    (serialized through ``AppointmentDetailSerializer``, the serializer the
    viewset uses for the ``today`` action).
    """
    from apps.appointments.serializers import AppointmentDetailSerializer

    today = datetime.date.today()
    appointments = queryset.filter(
        appointment_date=today
    ).order_by('appointment_time')

    return AppointmentDetailSerializer(
        appointments, many=True, context=context or {}
    ).data
