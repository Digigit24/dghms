"""Patient statistics service functions.

Extracted from ``PatientProfileViewSet.statistics`` so both the original
endpoint and the consolidated dashboard endpoint share one implementation.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate


def compute_patient_statistics(tenant_id: Any, group_by_day: bool = False) -> dict:
    """Tenant-scoped patient statistics.

    Returns the ``data`` dict of ``GET /api/patients/statistics/``
    (serialized through ``PatientStatisticsSerializer``).
    """
    from apps.patients.models import PatientProfile
    from apps.patients.serializers import PatientStatisticsSerializer

    base_qs = PatientProfile.objects.filter(tenant_id=tenant_id)

    today = datetime.date.today()
    totals = base_qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active')),
        inactive=Count('id', filter=Q(status='inactive')),
        deceased=Count('id', filter=Q(status='deceased')),
        insured=Count('id', filter=Q(
            insurance_provider__isnull=False,
            insurance_expiry_date__gte=today,
        )),
        registrations_today=Count(
            'id', filter=Q(registration_date__date=today)
        ),
        avg_age=Avg('age'),
        total_visits=Sum('total_visits'),
    )
    gender_counts = dict(
        base_qs.values_list('gender').annotate(count=Count('id'))
    )
    gender_dist = {
        label: gender_counts.get(code, 0)
        for code, label in getattr(PatientProfile, 'GENDER_CHOICES', [])
    }
    blood_dist = dict(
        base_qs.exclude(blood_group='')
        .values_list('blood_group')
        .annotate(count=Count('id'))
    )

    data = {
        'total_patients': totals['total'],
        'active_patients': totals['active'],
        'inactive_patients': totals['inactive'],
        'deceased_patients': totals['deceased'],
        'patients_with_insurance': totals['insured'],
        'average_age': round(totals['avg_age'] or 0, 1),
        'total_visits': totals['total_visits'] or 0,
        'gender_distribution': gender_dist,
        'blood_group_distribution': blood_dist,
        'registrations_today': totals['registrations_today'],
    }

    if group_by_day:
        start_date = today - datetime.timedelta(days=29)
        daily_trend = list(
            base_qs.filter(registration_date__date__gte=start_date)
                   .annotate(day=TruncDate('registration_date'))
                   .values('day')
                   .annotate(registrations=Count('id'))
                   .order_by('day')
        )
        data['daily_trend'] = [
            {'date': str(row['day']), 'registrations': row['registrations'] or 0}
            for row in daily_trend
        ]

    return PatientStatisticsSerializer(data).data
