"""Patient statistics service functions.

Extracted from ``PatientProfileViewSet.statistics`` so both the original
endpoint and the consolidated dashboard endpoint share one implementation.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDate


def compute_patient_statistics(tenant_id: Any, group_by_day: bool = False) -> dict:
    """Tenant-scoped patient statistics.

    Returns the ``data`` dict of ``GET /api/patients/statistics/``
    (serialized through ``PatientStatisticsSerializer``).
    """
    from apps.patients.models import PatientProfile
    from apps.patients.serializers import PatientStatisticsSerializer

    base_qs = PatientProfile.objects.filter(tenant_id=tenant_id)

    total = base_qs.count()
    active = base_qs.filter(status='active').count()
    inactive = base_qs.filter(status='inactive').count()
    deceased = base_qs.filter(status='deceased').count()

    today = datetime.date.today()
    patients_with_insurance = base_qs.filter(
        insurance_provider__isnull=False,
        insurance_expiry_date__gte=today
    ).count()
    avg_age = base_qs.aggregate(avg=Avg('age'))['avg'] or 0
    total_visits = base_qs.aggregate(total=Sum('total_visits'))['total'] or 0

    gender_dist = {label: base_qs.filter(gender=code).count()
                   for code, label in getattr(PatientProfile, 'GENDER_CHOICES', [])}

    blood_dist = {}
    for bg_code, _bg_label in getattr(PatientProfile, 'BLOOD_GROUP_CHOICES', []):
        c = base_qs.filter(blood_group=bg_code).count()
        if c > 0:
            blood_dist[bg_code] = c

    registrations_today = base_qs.filter(registration_date__date=today).count()

    data = {
        'total_patients': total,
        'active_patients': active,
        'inactive_patients': inactive,
        'deceased_patients': deceased,
        'patients_with_insurance': patients_with_insurance,
        'average_age': round(avg_age, 1),
        'total_visits': total_visits,
        'gender_distribution': gender_dist,
        'blood_group_distribution': blood_dist,
        'registrations_today': registrations_today,
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
