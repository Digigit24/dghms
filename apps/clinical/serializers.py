"""Serializers for the clinical forms and records app."""

import uuid as _uuid
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from rest_framework import serializers

from common.mixins import TenantMixin
from common.serializers import TenantAwareSerializer

_SYSTEM_TENANT_ID = _uuid.UUID("00000000-0000-0000-0000-000000000000")


def _tenant_id_from_context(context) -> _uuid.UUID | None:
    """Extract the request's tenant_id from serializer context, or None."""
    request = context.get("request") if context else None
    return getattr(request, "tenant_id", None) if request else None

from .models import (  # noqa: E402
    ClinicalFieldValue,
    ClinicalForm,
    ClinicalFormField,
    ClinicalFormGenerationRequest,
    ClinicalFormSection,
    ClinicalPicklist,
    ClinicalPicklistItem,
    ClinicalRecord,
    SavedFormSnapshot,
    UserFormPreference,
)


# ---------------------------------------------------------------------------
# Form structure serializers
# ---------------------------------------------------------------------------


class ClinicalFormFieldSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for a single form field."""

    class Meta:
        model = ClinicalFormField
        fields = "__all__"
        read_only_fields = ["tenant_id"]

    def validate_section(self, value):
        """Ensure the section belongs to the request tenant."""
        tid = _tenant_id_from_context(self.context)
        if tid is None:
            return value
        if not ClinicalFormSection.objects.filter(
            Q(tenant_id=tid) | Q(form__is_system=True, form__tenant_id=_SYSTEM_TENANT_ID),
            pk=value.pk,
        ).exists():
            raise serializers.ValidationError("Section not found or access denied.")
        return value

    def validate_picklist(self, value):
        """Ensure the picklist belongs to the request tenant or is a system picklist."""
        if value is None:
            return value
        tid = _tenant_id_from_context(self.context)
        if tid is None:
            return value
        if not ClinicalPicklist.objects.filter(
            Q(tenant_id=tid) | Q(is_system=True, tenant_id=_SYSTEM_TENANT_ID),
            pk=value.pk,
        ).exists():
            raise serializers.ValidationError("Picklist not found or access denied.")
        return value


class ClinicalFormSectionSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for a form section with nested fields."""

    section_fields = ClinicalFormFieldSerializer(many=True, read_only=True, source="fields")

    class Meta:
        model = ClinicalFormSection
        fields = "__all__"
        read_only_fields = ["tenant_id"]


class ClinicalFormSectionWriteSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for section writes (without nested fields)."""

    class Meta:
        model = ClinicalFormSection
        fields = "__all__"
        read_only_fields = ["tenant_id"]

    def validate_form(self, value):
        """Ensure the form FK belongs to the request tenant or is a system form."""
        tid = _tenant_id_from_context(self.context)
        if tid is None:
            return value
        if not ClinicalForm.objects.filter(
            Q(tenant_id=tid) | Q(is_system=True, tenant_id=_SYSTEM_TENANT_ID),
            pk=value.pk,
        ).exists():
            raise serializers.ValidationError("Form not found or access denied.")
        return value


class ClinicalFormSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for clinical form templates."""

    class Meta:
        model = ClinicalForm
        fields = "__all__"
        read_only_fields = ["tenant_id", "is_system", "version", "created_by_user_id"]


class ClinicalFormStructureSerializer(serializers.ModelSerializer):
    """Read-only serializer that expands a form into sections and fields."""

    sections = ClinicalFormSectionSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicalForm
        fields = [
            "id",
            "tenant_id",
            "code",
            "name",
            "description",
            "version",
            "status",
            "is_system",
            "entity_type",
            "config",
            "is_active",
            "created_at",
            "updated_at",
            "created_by_user_id",
            "sections",
        ]


# ---------------------------------------------------------------------------
# Picklist serializers
# ---------------------------------------------------------------------------


class ClinicalPicklistItemSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for a picklist item."""

    class Meta:
        model = ClinicalPicklistItem
        fields = "__all__"
        read_only_fields = ["tenant_id"]


class ClinicalPicklistSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for picklists, optionally including items."""

    items = ClinicalPicklistItemSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicalPicklist
        fields = "__all__"
        read_only_fields = ["tenant_id"]


# ---------------------------------------------------------------------------
# Record and value serializers
# ---------------------------------------------------------------------------


class ClinicalFieldValueSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for a typed field value."""

    field_key = serializers.CharField(source="field.field_key", read_only=True)
    field_type = serializers.CharField(source="field.field_type", read_only=True)

    class Meta:
        model = ClinicalFieldValue
        fields = "__all__"
        read_only_fields = ["tenant_id"]


class ClinicalRecordListSerializer(TenantMixin, serializers.ModelSerializer):
    """Lightweight serializer for record lists."""

    form_code = serializers.CharField(source="form.code", read_only=True)
    form_name = serializers.CharField(source="form.name", read_only=True)

    class Meta:
        model = ClinicalRecord
        fields = [
            "id",
            "tenant_id",
            "form",
            "form_code",
            "form_name",
            "encounter_type",
            "encounter_id",
            "patient_user_id",
            "status",
            "is_locked",
            "locked_by_user_id",
            "locked_at",
            "version",
            "is_active",
            "created_at",
            "updated_at",
            "created_by_user_id",
        ]


class ClinicalRecordDetailSerializer(TenantMixin, serializers.ModelSerializer):
    """Full record serializer including field values."""

    form_code = serializers.CharField(source="form.code", read_only=True)
    form_name = serializers.CharField(source="form.name", read_only=True)
    field_values = ClinicalFieldValueSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicalRecord
        fields = "__all__"
        read_only_fields = ["tenant_id"]


class ClinicalRecordWriteSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for record creates/updates."""

    class Meta:
        model = ClinicalRecord
        fields = "__all__"
        read_only_fields = [
            "tenant_id",
            "status",
            "is_locked",
            "locked_by_user_id",
            "locked_at",
            "version",
            "created_by_user_id",
        ]

    def validate_form(self, value):
        """Ensure the form FK belongs to the request tenant or is a system form."""
        tid = _tenant_id_from_context(self.context)
        if tid is None:
            return value
        if not ClinicalForm.objects.filter(
            Q(tenant_id=tid) | Q(is_system=True, tenant_id=_SYSTEM_TENANT_ID),
            pk=value.pk,
        ).exists():
            raise serializers.ValidationError("Form not found or access denied.")
        return value


# ---------------------------------------------------------------------------
# Snapshot / preference serializers
# ---------------------------------------------------------------------------


class UserFormPreferenceSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for per-user form preferences."""

    class Meta:
        model = UserFormPreference
        fields = "__all__"
        # user_id is always sourced from the JWT, never from client input
        read_only_fields = ["tenant_id", "user_id"]

    def validate_form(self, value):
        """Ensure the form FK belongs to the request tenant or is a system form."""
        tid = _tenant_id_from_context(self.context)
        if tid is None:
            return value
        if not ClinicalForm.objects.filter(
            Q(tenant_id=tid) | Q(is_system=True, tenant_id=_SYSTEM_TENANT_ID),
            pk=value.pk,
        ).exists():
            raise serializers.ValidationError("Form not found or access denied.")
        return value


class SavedFormSnapshotSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for saved record snapshots."""

    class Meta:
        model = SavedFormSnapshot
        fields = "__all__"
        read_only_fields = ["tenant_id"]

    def validate_record(self, value):
        """Ensure the record belongs to the request tenant."""
        tid = _tenant_id_from_context(self.context)
        if tid is None:
            return value
        if not ClinicalRecord.objects.filter(tenant_id=tid, pk=value.pk).exists():
            raise serializers.ValidationError("Record not found or not accessible.")
        return value


class ClinicalFormGenerationRequestSerializer(TenantAwareSerializer):
    """Serializer for ClinicalFormGenerationRequest."""

    class Meta:
        model = ClinicalFormGenerationRequest
        fields = [
            "id", "tenant_id", "prompt", "extra_instructions", "entity_type",
            "status", "generated_draft", "error_message", "applied_form",
            "created_at", "updated_at", "created_by_user_id",
        ]
        read_only_fields = [
            "id", "tenant_id", "status", "generated_draft", "error_message",
            "applied_form", "created_at", "updated_at", "created_by_user_id",
        ]


class ApplyFormDraftSerializer(serializers.Serializer):
    """Input serializer for the 'apply' action on a GenerationRequest."""

    target_form_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="If provided, apply the draft to an existing form. Otherwise create a new form.",
    )


class GenerateFormRequestSerializer(serializers.Serializer):
    """Input for the AI form generation wizard."""

    prompt = serializers.CharField(help_text="Natural-language description of the form to generate.")
    entity_type = serializers.ChoiceField(
        choices=[("opd_visit", "OPD Visit"), ("ipd_admission", "IPD Admission"), ("generic", "Generic")],
        default="generic",
        required=False,
    )
    extra_instructions = serializers.CharField(required=False, allow_blank=True, default="")


class RegenerateFormRequestSerializer(serializers.Serializer):
    """Input for regenerating an AI form draft."""

    extra_instructions = serializers.CharField(required=False, allow_blank=True, default="")


class FieldValueBulkUpsertItemSerializer(serializers.Serializer):
    """A single field value in a bulk upsert payload."""

    field_id = serializers.IntegerField()
    value_text = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    value_number = serializers.DecimalField(max_digits=20, decimal_places=6, required=False, allow_null=True, default=None)
    value_boolean = serializers.BooleanField(required=False, allow_null=True, default=None)
    value_date = serializers.DateField(required=False, allow_null=True, default=None)
    value_json = serializers.JSONField(required=False, allow_null=True, default=None)


class FieldValueBulkUpsertSerializer(serializers.Serializer):
    """Payload for bulk upsert of field values on a clinical record."""

    values = FieldValueBulkUpsertItemSerializer(many=True)


def coerce_field_value(field, value_text: str) -> dict:
    """Coerce a text value to the appropriate typed column for a given field.

    Returns a dict of keyword arguments suitable for passing to
    ``ClinicalFieldValue.objects.update_or_create(defaults=...)``.
    Per the MCP-friendly API rule: natural-language tolerance on write.
    """
    from .models import ClinicalFormField

    result: dict = {"value_text": value_text}

    if field.field_type == ClinicalFormField.FieldType.NUMBER:
        try:
            result["value_number"] = Decimal(str(value_text).replace(",", ""))
        except (InvalidOperation, ValueError):
            pass
    elif field.field_type == ClinicalFormField.FieldType.BOOLEAN:
        result["value_boolean"] = str(value_text).lower() in ("1", "true", "yes", "on")
    elif field.field_type == ClinicalFormField.FieldType.DATE:
        from django.utils.dateparse import parse_date
        parsed = parse_date(str(value_text))
        if parsed:
            result["value_date"] = parsed
    elif field.field_type == ClinicalFormField.FieldType.DATETIME:
        from django.utils.dateparse import parse_datetime
        parsed = parse_datetime(str(value_text))
        if parsed:
            result["value_date"] = parsed

    return result
