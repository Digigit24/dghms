"""Serializers for the clinical forms and records app."""

import uuid as _uuid
from decimal import Decimal, InvalidOperation

from django.db.models import Prefetch, Q
from rest_framework import serializers

from common.mixins import TenantMixin
from common.serializers import TenantAwareSerializer

_SYSTEM_TENANT_ID = _uuid.UUID("00000000-0000-0000-0000-000000000000")


def _tenant_id_from_context(context) -> _uuid.UUID | None:
    """Extract the request's tenant_id from serializer context, or None."""
    request = context.get("request") if context else None
    return getattr(request, "tenant_id", None) if request else None


def _accessible_section_q(tenant_id) -> Q:
    """Section access rule shared by serializers.

    Sections are reusable and can become globally shared by being placed on a
    system form even if the section's own duplicated ``is_system`` flag is
    stale. Keep validation aligned with ClinicalFormSectionViewSet.
    """
    return Q(tenant_id=tenant_id) | (
        Q(tenant_id=_SYSTEM_TENANT_ID)
        & (Q(is_system=True) | Q(form_placements__form__is_system=True))
    )

from .models import (  # noqa: E402
    ClinicalDocumentInstance,
    ClinicalDocumentTemplate,
    ClinicalFieldValue,
    ClinicalForm,
    ClinicalFormField,
    ClinicalFormGroup,
    ClinicalFormGroupItem,
    ClinicalFormGenerationRequest,
    ClinicalFormSection,
    ClinicalFormTemplate,
    ClinicalPicklist,
    ClinicalPicklistGroup,
    ClinicalPicklistGroupMembership,
    ClinicalPicklistItem,
    ClinicalPrintTemplate,
    ClinicalRecord,
    FormSectionPlacement,
    MrdChecklistLine,
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
            _accessible_section_q(tid),
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
    """Serializer for reusable section definition writes."""

    sync_pharmacy = serializers.BooleanField(required=False, write_only=True)
    sync_lab = serializers.BooleanField(required=False, write_only=True)

    class Meta:
        model = ClinicalFormSection
        fields = "__all__"
        read_only_fields = ["tenant_id"]

    @staticmethod
    def _sync_roles(config):
        roles = {
            role for role in (config.get("roles") or [])
            if role in {"prescription", "investigation"}
        }
        if config.get("role") in {"prescription", "investigation"}:
            roles.add(config["role"])
        return roles

    @classmethod
    def _resolved_toggle(cls, instance, destination):
        config = instance.config or {}
        role = "prescription" if destination == "pharmacy" else "investigation"
        visible = "visible_to_pharmacy" if destination == "pharmacy" else "visible_to_lab"
        return role in cls._sync_roles(config) or config.get(visible) is True

    @classmethod
    def _apply_toggles(cls, instance, validated_data):
        pharmacy = validated_data.pop("sync_pharmacy", None)
        lab = validated_data.pop("sync_lab", None)
        if pharmacy is None and lab is None:
            return validated_data

        config = dict(validated_data.get("config", instance.config or {}))
        roles = cls._sync_roles(config)
        has_grid = instance.fields.filter(
            field_type=ClinicalFormField.FieldType.GRID,
            is_active=True,
        ).exists()

        for enabled, role, visible_key in (
            (pharmacy, "prescription", "visible_to_pharmacy"),
            (lab, "investigation", "visible_to_lab"),
        ):
            if enabled is None:
                continue
            if enabled and has_grid:
                roles.add(role)
                config.pop(visible_key, None)
            elif enabled:
                roles.discard(role)
                config[visible_key] = True
            else:
                roles.discard(role)
                config.pop(visible_key, None)

        config.pop("role", None)
        config.pop("roles", None)
        if len(roles) == 1:
            config["role"] = next(iter(roles))
        elif roles:
            # Keep a singular role for legacy readers and the complete list for
            # the new independent two-toggle contract.
            ordered = [r for r in ("prescription", "investigation") if r in roles]
            config["role"] = ordered[0]
            config["roles"] = ordered
        validated_data["config"] = config
        return validated_data

    def update(self, instance, validated_data):
        validated_data = self._apply_toggles(instance, validated_data)
        return super().update(instance, validated_data)

    def create(self, validated_data):
        # A new section has no fields yet, so enabled toggles resolve to
        # read-only visibility. Re-toggling after a GRID field is added upgrades
        # it to structured sync.
        sync_pharmacy = validated_data.pop("sync_pharmacy", None)
        sync_lab = validated_data.pop("sync_lab", None)
        config = dict(validated_data.get("config") or {})
        if sync_pharmacy:
            config["visible_to_pharmacy"] = True
        if sync_lab:
            config["visible_to_lab"] = True
        validated_data["config"] = config
        return super().create(validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["sync_pharmacy"] = self._resolved_toggle(instance, "pharmacy")
        data["sync_lab"] = self._resolved_toggle(instance, "lab")
        return data


class FormSectionPlacementSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for attaching reusable sections to forms."""

    section_code = serializers.CharField(source="section.code", read_only=True)
    section_title = serializers.CharField(source="section.title", read_only=True)

    class Meta:
        model = FormSectionPlacement
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

    def validate_section(self, value):
        """Ensure the section belongs to the request tenant or is a system section."""
        tid = _tenant_id_from_context(self.context)
        if tid is None:
            return value
        if not ClinicalFormSection.objects.filter(
            _accessible_section_q(tid),
            pk=value.pk,
        ).exists():
            raise serializers.ValidationError("Section not found or access denied.")
        return value


class ClinicalFormSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for clinical form templates."""

    class Meta:
        model = ClinicalForm
        fields = "__all__"
        read_only_fields = ["tenant_id", "is_system", "version", "created_by_user_id"]


class ClinicalFormStructureSerializer(serializers.ModelSerializer):
    """Read-only serializer that expands a form into sections and fields."""

    sections = serializers.SerializerMethodField()

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

    def get_sections(self, form):
        active_items = ClinicalPicklistItem.objects.filter(is_active=True).order_by(
            "display_order", "id"
        )
        active_fields = (
            ClinicalFormField.objects.filter(is_active=True)
            .select_related("picklist")
            .prefetch_related(
                Prefetch(
                    "picklist__items",
                    queryset=active_items,
                    to_attr="active_items",
                )
            )
            .order_by("display_order", "id")
        )
        placements = (
            form.section_placements.filter(is_active=True, section__is_active=True)
            .select_related("section")
            .prefetch_related(
                Prefetch(
                    "section__fields",
                    queryset=active_fields,
                    to_attr="active_fields",
                )
            )
            .order_by("display_order", "id")
        )
        result = []
        for placement in placements:
            section = placement.section
            fields = []
            for field in section.active_fields:
                field_data = ClinicalFormFieldSerializer(field, context=self.context).data
                if field.picklist_id:
                    field_data["picklist_items"] = ClinicalPicklistItemSerializer(
                        field.picklist.active_items,
                        many=True,
                    ).data
                fields.append(field_data)
            result.append(
                {
                    "id": section.id,
                    "placement_id": placement.id,
                    "instance_key": placement.instance_key,
                    "tenant_id": section.tenant_id,
                    "code": section.code,
                    "title": placement.title_override or section.title,
                    "description": section.description,
                    "display_order": placement.display_order,
                    "is_collapsed": placement.is_collapsed,
                    "visibility_rule": placement.visibility_rule,
                    "config": {**(section.config or {}), **(placement.config or {})},
                    "is_active": section.is_active,
                    "created_at": section.created_at,
                    "updated_at": section.updated_at,
                    "created_by_user_id": section.created_by_user_id,
                    "section_fields": fields,
                    # Resolved pharmacy/lab sync flags — same resolution logic as
                    # ClinicalFormSectionWriteSerializer.to_representation, so the
                    # admin forms UI can show correct toggle state without
                    # inferring it from raw `config` itself.
                    "sync_pharmacy": ClinicalFormSectionWriteSerializer._resolved_toggle(section, "pharmacy"),
                    "sync_lab": ClinicalFormSectionWriteSerializer._resolved_toggle(section, "lab"),
                }
            )
        return result


class ClinicalFormGroupItemSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for forms attached to clinical groups."""

    form_code = serializers.CharField(source="form.code", read_only=True)
    form_name = serializers.CharField(source="form.name", read_only=True)

    class Meta:
        model = ClinicalFormGroupItem
        fields = "__all__"
        read_only_fields = ["tenant_id"]


class ClinicalFormGroupSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for clinical form group trees."""

    items = ClinicalFormGroupItemSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicalFormGroup
        fields = "__all__"
        read_only_fields = ["tenant_id"]


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


class ClinicalPicklistGroupMembershipSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for picklist group membership."""

    picklist_code = serializers.CharField(source="picklist.code", read_only=True)
    picklist_name = serializers.CharField(source="picklist.name", read_only=True)

    class Meta:
        model = ClinicalPicklistGroupMembership
        fields = "__all__"
        read_only_fields = ["tenant_id"]


class ClinicalPicklistGroupSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for picklist groups."""

    memberships = ClinicalPicklistGroupMembershipSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicalPicklistGroup
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
            "occurrence_index",
            "patient_user_id",
            "status",
            "is_locked",
            "locked_by_user_id",
            "locked_at",
            "version",
            "form_version",
            "structure_snapshot",
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
            "form_version",
            "structure_snapshot",
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
    value_datetime = serializers.DateTimeField(required=False, allow_null=True, default=None)
    value_time = serializers.TimeField(required=False, allow_null=True, default=None)
    value_json = serializers.JSONField(required=False, allow_null=True, default=None)
    picklist_item_id = serializers.IntegerField(required=False, allow_null=True, default=None)


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
            result["value_datetime"] = parsed
    elif field.field_type == ClinicalFormField.FieldType.TIME:
        from django.utils.dateparse import parse_time
        parsed = parse_time(str(value_text))
        if parsed:
            result["value_time"] = parsed
    elif field.field_type in (
        ClinicalFormField.FieldType.GRID,
        ClinicalFormField.FieldType.MULTISELECT,
        ClinicalFormField.FieldType.DATA_REF,
    ):
        result["value_json"] = value_text

    return result


class ClinicalDocumentTemplateSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for document templates."""

    class Meta:
        model = ClinicalDocumentTemplate
        fields = "__all__"
        read_only_fields = ["tenant_id"]


class ClinicalDocumentInstanceSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for document instances."""

    template_code = serializers.CharField(source="template.code", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)

    class Meta:
        model = ClinicalDocumentInstance
        fields = "__all__"
        read_only_fields = ["tenant_id"]


class ClinicalPrintTemplateSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for print templates."""

    class Meta:
        model = ClinicalPrintTemplate
        fields = "__all__"
        read_only_fields = ["tenant_id"]


class MrdChecklistLineSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for MRD checklist configuration lines."""

    class Meta:
        model = MrdChecklistLine
        fields = "__all__"
        read_only_fields = ["tenant_id"]


class ClinicalFormTemplateSerializer(TenantMixin, serializers.ModelSerializer):
    """Named, reusable field-value templates for a form (e.g. prescription templates)."""

    form_code = serializers.CharField(source="form.code", read_only=True)

    class Meta:
        model = ClinicalFormTemplate
        fields = "__all__"
        read_only_fields = ["tenant_id", "created_by_user_id"]


class EncounterFormsQuerySerializer(serializers.Serializer):
    """Query params for encounter form resolution."""

    encounter_type = serializers.ChoiceField(choices=["opd_visit", "ipd_admission", "generic"])
    encounter_id = serializers.IntegerField()
