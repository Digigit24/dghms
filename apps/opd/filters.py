# apps/opd/filters.py
import django_filters
from .models import Visit


class VisitFilter(django_filters.FilterSet):
    """
    Custom FilterSet for Visit model.
    Adds date range lookups (visit_date__gte / visit_date__lte)
    that filterset_fields alone cannot provide.
    """
    status = django_filters.CharFilter(field_name='status', lookup_expr='exact')
    visit_type = django_filters.CharFilter(field_name='visit_type', lookup_expr='exact')
    payment_status = django_filters.CharFilter(field_name='payment_status', lookup_expr='exact')
    is_follow_up = django_filters.BooleanFilter(field_name='is_follow_up')
    patient = django_filters.NumberFilter(field_name='patient', lookup_expr='exact')
    doctor = django_filters.NumberFilter(field_name='doctor', lookup_expr='exact')

    # Exact date match
    visit_date = django_filters.DateFilter(
        field_name='visit_date',
        lookup_expr='exact',
        label='Visit date (YYYY-MM-DD)',
    )
    # Date range — what the frontend sends
    visit_date__gte = django_filters.DateFilter(
        field_name='visit_date',
        lookup_expr='gte',
        label='Visit date on or after (YYYY-MM-DD)',
    )
    visit_date__lte = django_filters.DateFilter(
        field_name='visit_date',
        lookup_expr='lte',
        label='Visit date on or before (YYYY-MM-DD)',
    )

    class Meta:
        model = Visit
        fields = ['status', 'visit_type', 'payment_status', 'is_follow_up', 'patient', 'doctor', 'visit_date']
