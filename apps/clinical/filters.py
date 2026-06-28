"""Filter sets for clinical endpoints."""

import django_filters
from django_filters.rest_framework import FilterSet

from .models import ClinicalForm, ClinicalPicklistItem, ClinicalRecord


class ClinicalFormFilter(FilterSet):
    """Filter for clinical form templates."""

    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    entity_type = django_filters.CharFilter(field_name="entity_type", lookup_expr="exact")
    is_system = django_filters.BooleanFilter(field_name="is_system")
    code = django_filters.CharFilter(field_name="code", lookup_expr="exact")

    class Meta:
        model = ClinicalForm
        fields = ["status", "entity_type", "is_system", "code"]


class ClinicalRecordFilter(FilterSet):
    """Filter for clinical record instances."""

    form = django_filters.NumberFilter(field_name="form", lookup_expr="exact")
    encounter_type = django_filters.CharFilter(field_name="encounter_type", lookup_expr="exact")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    patient_user_id = django_filters.UUIDFilter(field_name="patient_user_id", lookup_expr="exact")

    class Meta:
        model = ClinicalRecord
        fields = ["form", "encounter_type", "status", "patient_user_id"]


class ClinicalPicklistItemFilter(FilterSet):
    """Filter for picklist items."""

    picklist = django_filters.NumberFilter(field_name="picklist", lookup_expr="exact")
    value = django_filters.CharFilter(field_name="value", lookup_expr="exact")

    class Meta:
        model = ClinicalPicklistItem
        fields = ["picklist", "value"]
