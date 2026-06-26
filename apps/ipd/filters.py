# apps/ipd/filters.py
import django_filters
from .models import Admission


class AdmissionFilter(django_filters.FilterSet):
    """
    Custom FilterSet for Admission to support date range filtering.
    Replaces filterset_fields in AdmissionViewSet.
    """
    status = django_filters.CharFilter(field_name='status', lookup_expr='exact')
    ward = django_filters.NumberFilter(field_name='ward', lookup_expr='exact')
    doctor_id = django_filters.UUIDFilter(field_name='doctor_id', lookup_expr='exact')
    patient = django_filters.NumberFilter(field_name='patient', lookup_expr='exact')
    has_mediclaim = django_filters.BooleanFilter(field_name='has_mediclaim')
    claim_status = django_filters.CharFilter(field_name='claim_status', lookup_expr='exact')
    tpa_name = django_filters.CharFilter(field_name='tpa_name', lookup_expr='icontains')

    admission_date__gte = django_filters.DateFilter(
        field_name='admission_date',
        lookup_expr='date__gte',
        label='Admitted on or after (YYYY-MM-DD)',
    )
    admission_date__lte = django_filters.DateFilter(
        field_name='admission_date',
        lookup_expr='date__lte',
        label='Admitted on or before (YYYY-MM-DD)',
    )
    discharge_date__gte = django_filters.DateFilter(
        field_name='discharge_date',
        lookup_expr='date__gte',
        label='Discharged on or after (YYYY-MM-DD)',
    )
    discharge_date__lte = django_filters.DateFilter(
        field_name='discharge_date',
        lookup_expr='date__lte',
        label='Discharged on or before (YYYY-MM-DD)',
    )

    class Meta:
        model = Admission
        fields = ['status', 'ward', 'doctor_id', 'patient', 'has_mediclaim', 'claim_status', 'tpa_name']
