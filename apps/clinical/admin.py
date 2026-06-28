"""Django admin configuration for the clinical app."""

from django.contrib import admin

from common.admin_site import TenantModelAdmin, hms_admin_site

from .models import (
    ClinicalFieldValue,
    ClinicalForm,
    ClinicalFormField,
    ClinicalFormGenerationRequest,
    ClinicalFormSection,
    ClinicalPicklist,
    ClinicalPicklistItem,
    ClinicalRecord,
    ClinicalRecordAuditLog,
    SavedFormSnapshot,
    UserFormPreference,
)


@admin.register(ClinicalForm, site=hms_admin_site)
class ClinicalFormAdmin(TenantModelAdmin):
    list_display = (
        "code",
        "name",
        "version",
        "status",
        "entity_type",
        "is_system",
        "is_active",
        "tenant_id",
        "created_at",
    )
    list_filter = ("status", "entity_type", "is_system", "is_active")
    search_fields = ("code", "name")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")
    fieldsets = (
        ("Form", {"fields": ("code", "name", "description", "version", "status", "entity_type")}),
        ("Flags", {"fields": ("is_system", "is_active", "config")}),
        ("System", {"fields": ("tenant_id", "created_by_user_id", "created_at", "updated_at")}),
    )


class ClinicalFormFieldInline(admin.TabularInline):
    model = ClinicalFormField
    extra = 0
    fields = ("field_key", "field_type", "label", "display_order", "is_required", "is_active")
    readonly_fields = ("tenant_id",)


@admin.register(ClinicalFormSection, site=hms_admin_site)
class ClinicalFormSectionAdmin(TenantModelAdmin):
    list_display = ("form", "code", "title", "display_order", "is_active", "tenant_id")
    list_filter = ("is_active",)
    search_fields = ("form__code", "code", "title")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")
    inlines = [ClinicalFormFieldInline]


@admin.register(ClinicalFormField, site=hms_admin_site)
class ClinicalFormFieldAdmin(TenantModelAdmin):
    list_display = (
        "section",
        "field_key",
        "field_type",
        "label",
        "display_order",
        "is_required",
        "is_active",
        "tenant_id",
    )
    list_filter = ("field_type", "is_required", "is_active")
    search_fields = ("field_key", "label", "section__code")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


class ClinicalPicklistItemInline(admin.TabularInline):
    model = ClinicalPicklistItem
    extra = 0
    fields = ("label", "value", "display_order", "is_active")
    readonly_fields = ("tenant_id",)


@admin.register(ClinicalPicklist, site=hms_admin_site)
class ClinicalPicklistAdmin(TenantModelAdmin):
    list_display = ("code", "name", "is_system", "is_active", "tenant_id", "created_at")
    list_filter = ("is_system", "is_active")
    search_fields = ("code", "name")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")
    inlines = [ClinicalPicklistItemInline]


@admin.register(ClinicalPicklistItem, site=hms_admin_site)
class ClinicalPicklistItemAdmin(TenantModelAdmin):
    list_display = ("picklist", "label", "value", "display_order", "is_active", "tenant_id")
    list_filter = ("is_active",)
    search_fields = ("label", "value", "picklist__code")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


class ClinicalFieldValueInline(admin.TabularInline):
    model = ClinicalFieldValue
    extra = 0
    fields = ("field", "value_text", "value_number", "value_boolean", "value_date", "value_json")
    readonly_fields = ("tenant_id", "field")


@admin.register(ClinicalRecord, site=hms_admin_site)
class ClinicalRecordAdmin(TenantModelAdmin):
    list_display = (
        "id",
        "form",
        "encounter_type",
        "encounter_id",
        "status",
        "is_locked",
        "version",
        "tenant_id",
        "created_at",
    )
    list_filter = ("status", "is_locked", "is_active")
    search_fields = ("form__code", "encounter_type", "encounter_id")
    readonly_fields = (
        "tenant_id",
        "locked_by_user_id",
        "locked_at",
        "created_at",
        "updated_at",
        "created_by_user_id",
    )
    inlines = [ClinicalFieldValueInline]


@admin.register(ClinicalFieldValue, site=hms_admin_site)
class ClinicalFieldValueAdmin(TenantModelAdmin):
    list_display = (
        "record",
        "field",
        "value_text",
        "value_number",
        "value_boolean",
        "value_date",
        "tenant_id",
    )
    list_filter = ("is_active",)
    search_fields = ("record__id", "field__field_key")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


@admin.register(UserFormPreference, site=hms_admin_site)
class UserFormPreferenceAdmin(TenantModelAdmin):
    list_display = ("user_id", "form", "is_active", "tenant_id", "created_at")
    list_filter = ("is_active",)
    search_fields = ("form__code",)
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


@admin.register(SavedFormSnapshot, site=hms_admin_site)
class SavedFormSnapshotAdmin(TenantModelAdmin):
    list_display = ("record", "name", "is_active", "tenant_id", "created_at")
    list_filter = ("is_active",)
    search_fields = ("record__id", "name")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


@admin.register(ClinicalRecordAuditLog, site=hms_admin_site)
class ClinicalRecordAuditLogAdmin(TenantModelAdmin):
    list_display = ("record", "action", "user_id", "tenant_id", "created_at")
    list_filter = ("action",)
    search_fields = ("record__id", "action")
    readonly_fields = ("tenant_id", "created_at", "created_by_user_id")

    def has_change_permission(self, request, obj=None):
        # Audit logs are append-only.
        return False

    def has_delete_permission(self, request, obj=None):
        # Audit logs are append-only.
        return False


@admin.register(ClinicalFormGenerationRequest, site=hms_admin_site)
class ClinicalFormGenerationRequestAdmin(TenantModelAdmin):
    list_display = (
        "id",
        "entity_type",
        "status",
        "applied_form",
        "tenant_id",
        "created_at",
    )
    list_filter = ("status", "entity_type")
    search_fields = ("prompt", "error_message")
    readonly_fields = (
        "tenant_id",
        "created_at",
        "updated_at",
        "created_by_user_id",
        "applied_form",
    )
    fieldsets = (
        ("Prompt", {"fields": ("prompt", "extra_instructions", "entity_type")}),
        ("Result", {"fields": ("status", "generated_draft", "applied_form", "error_message")}),
        ("System", {"fields": ("tenant_id", "created_by_user_id", "created_at", "updated_at")}),
    )
