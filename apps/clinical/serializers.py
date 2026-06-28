"""Serializers for the clinical forms and records app."""

import uuid as _uuid
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from rest_framework import serializers

from common.mixins import TenantMixin

_SYSTEM_TENANT_ID = _uuid.UUID("00000000-0000-0000-0000-000000000000")


def _tenant_id_from_context(context) -> _uuid.UUID | None:
    """Extract the request's tenant_id from serializer context, or None."""
    request = context.get("request") if context else None
    return getattr(request, "tenant_id", None) if request else None

from .models import (
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
            raise serializers.ValidationError("Record not found or access denied.")
        return value


# ---------------------------------------------------------------------------
# Bulk upsert payload serializers
# ---------------------------------------------------------------------------


class FieldValueUpsertItemSerializer(serializers.Serializer):
    """Single item for the bulk field-value upsert endpoint."""

    field_id = serializers.IntegerField(min_value=1, help_text="ID of the ClinicalFormField")
    value_text = serializers.CharField(
        allow_blank=True,
        required=True,
        help_text="Raw string value; will be coerced to the field's typed column.",
    )


class FieldValueBulkUpsertSerializer(serializers.Serializer):
    """Payload for bulk upsert of field values on a record."""

    values = FieldValueUpsertItemSerializer(many=True, min_length=1)


# ---------------------------------------------------------------------------
# Value coercion helpers
# ---------------------------------------------------------------------------


def coerce_field_value(field: ClinicalFormField, value_text: str):
    """Coerce a raw string value into the typed storage for a field.

    Returns a dict of column names -> values suitable for update_or_create
    defaults. Raises ValidationError on type mismatch.
    """
    if value_text is None or value_text == "":
        return {
            "value_text": None,
            "value_number": None,
            "value_boolean": None,
            "value_date": None,
            "value_json": None,
        }

    field_type = field.field_type
    stripped = value_text.strip()

    if field_type == ClinicalFormField.FieldType.TEXT:
        return {"value_text": stripped}

    if field_type == ClinicalFormField.FieldType.TEXTAREA:
        return {"value_text": stripped}

    if field_type == ClinicalFormField.FieldType.NUMBER:
        try:
            return {"value_number": Decimal(stripped)}
        except (InvalidOperation, ValueError) as exc:
            raise serializers.ValidationError(
                {f"field_{field.id}": f"Invalid number for field '{field.field_key}'."}
            ) from exc

    if field_type == ClinicalFormField.FieldType.BOOLEAN:
        lowered = stripped.lower()
        if lowered in ("true", "1", "yes", "y"):
            return {"value_boolean": True}
        if lowered in ("false", "0", "no", "n"):
            return {"value_boolean": False}
        raise serializers.ValidationError(
            {f"field_{field.id}": f"Invalid boolean for field '{field.field_key}'."}
        )

    if field_type == ClinicalFormField.FieldType.DATE:
        try:
            from datetime import date

            return {"value_date": date.fromisoformat(stripped)}
        except ValueError as exc:
            raise serializers.ValidationError(
                {f"field_{field.id}": f"Invalid date (YYYY-MM-DD) for field '{field.field_key}'."}
            ) from exc

    if field_type == ClinicalFormField.FieldType.DATETIME:
        try:
            from datetime import datetime

            return {"value_json": datetime.fromisoformat(stripped).isoformat()}
        except ValueError as exc:
            raise serializers.ValidationError(
                {f"field_{field.id}": f"Invalid datetime for field '{field.field_key}'."}
            ) from exc

    if field_type in (ClinicalFormField.FieldType.PICKLIST, ClinicalFormField.FieldType.MULTISELECT):
        return {"value_text": stripped}

    if field_type == ClinicalFormField.FieldType.FILE:
        return {"value_text": stripped}

    if field_type == ClinicalFormField.FieldType.CALCULATED:
        return {"value_json": stripped}

    # Fallback for unknown types
    return {"value_text": stripped}


# ---------------------------------------------------------------------------
# AI wizard serializers
# ---------------------------------------------------------------------------


class GenerateFormRequestSerializer(serializers.Serializer):
    """Payload for generating a clinical form draft via AI."""

    prompt = serializers.CharField(
        required=True,
        trim_whitespace=True,
        help_text="Natural-language description of the form to generate.",
    )
    extra_instructions = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional extra constraints for the AI (tone, specialty, fields to include, etc.).",
    )
    entity_type = serializers.ChoiceField(
        choices=ClinicalForm.EntityType.choices,
        required=False,
        default=ClinicalForm.EntityType.GENERIC,
        help_text="Encounter type this form targets.",
    )


class RegenerateFormRequestSerializer(serializers.Serializer):
    """Payload for regenerating an existing draft with extra instructions."""

    extra_instructions = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Additional constraints to append to the original prompt.",
    )


class ApplyFormDraftSerializer(serializers.Serializer):
    """Payload for applying an AI draft to the real clinical form schema."""

    dry_run = serializers.BooleanField(
        required=False,
        default=False,
        help_text="If true, validate and return the migration plan without writing to the database.",
    )
    target_code = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default=None,
        max_length=64,
        help_text="Override the generated form code. Normalized to snake_case.",
    )


class ClinicalFormGenerationRequestSerializer(serializers.ModelSerializer):
    """Read serializer for AI generation requests."""

    class Meta:
        model = ClinicalFormGenerationRequest
        fields = [
            "id",
            "tenant_id",
            "prompt",
            "extra_instructions",
            "entity_type",
            "status",
            "generated_draft",
            "applied_form",
            "error_message",
            "created_at",
            "updated_at",
            "created_by_user_id",
        ]
        read_only_fields = fields
