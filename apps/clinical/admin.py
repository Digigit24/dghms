"""Django admin configuration for the clinical app."""

from django.contrib import admin

from common.admin_site import TenantModelAdmin, hms_admin_site

from .models import (
    ClinicalDocumentInstance,
    ClinicalDocumentTemplate,
    ClinicalFieldValue,
    ClinicalForm,
    ClinicalFormField,
    ClinicalFormGroup,
    ClinicalFormGroupItem,
    ClinicalFormSection,
    ClinicalPicklist,
    ClinicalPicklistGroup,
    ClinicalPicklistGroupMembership,
    ClinicalPicklistItem,
    ClinicalPrintTemplate,
    ClinicalRecord,
    ClinicalRecordAuditLog,
    FormSectionPlacement,
    MrdChecklistLine,
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
    list_display = ("code", "title", "is_system", "is_active", "tenant_id")
    list_filter = ("is_system", "is_active")
    search_fields = ("code", "title")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")
    inlines = [ClinicalFormFieldInline]


@admin.register(FormSectionPlacement, site=hms_admin_site)
class FormSectionPlacementAdmin(TenantModelAdmin):
    list_display = ("form", "section", "instance_key", "display_order", "is_active", "tenant_id")
    list_filter = ("is_active",)
    search_fields = ("form__code", "section__code", "instance_key")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


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
    fields = ("label", "label_mr", "label_hi", "value", "display_order", "is_active")
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
    fields = ("field", "value_text", "value_number", "value_boolean", "value_date", "value_datetime", "value_time", "value_json", "picklist_item")
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
        "value_datetime",
        "value_time",
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
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ClinicalFormGroup, site=hms_admin_site)
class ClinicalFormGroupAdmin(TenantModelAdmin):
    list_display = ("code", "name", "group_type", "parent", "entity_type", "display_order", "tenant_id")
    list_filter = ("group_type", "entity_type", "is_system", "is_active")
    search_fields = ("code", "name")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


@admin.register(ClinicalFormGroupItem, site=hms_admin_site)
class ClinicalFormGroupItemAdmin(TenantModelAdmin):
    list_display = ("group", "form", "display_order", "badge_when_filled", "tenant_id")
    search_fields = ("group__code", "form__code")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


@admin.register(ClinicalPicklistGroup, site=hms_admin_site)
class ClinicalPicklistGroupAdmin(TenantModelAdmin):
    list_display = ("code", "name", "is_system", "is_active", "tenant_id")
    search_fields = ("code", "name")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


@admin.register(ClinicalPicklistGroupMembership, site=hms_admin_site)
class ClinicalPicklistGroupMembershipAdmin(TenantModelAdmin):
    list_display = ("group", "picklist", "display_order", "tenant_id")
    search_fields = ("group__code", "picklist__code")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


@admin.register(ClinicalDocumentTemplate, site=hms_admin_site)
class ClinicalDocumentTemplateAdmin(TenantModelAdmin):
    list_display = ("code", "name", "doc_type", "bucket", "display_order", "is_system", "tenant_id")
    list_filter = ("doc_type", "bucket", "is_system", "is_active")
    search_fields = ("code", "name")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


@admin.register(ClinicalDocumentInstance, site=hms_admin_site)
class ClinicalDocumentInstanceAdmin(TenantModelAdmin):
    list_display = ("template", "encounter_type", "encounter_id", "language", "status", "tenant_id", "created_at")
    list_filter = ("status", "language", "encounter_type")
    search_fields = ("template__code", "encounter_id")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


@admin.register(ClinicalPrintTemplate, site=hms_admin_site)
class ClinicalPrintTemplateAdmin(TenantModelAdmin):
    list_display = ("code", "target_type", "target_code", "layout", "language", "tenant_id")
    list_filter = ("target_type", "layout", "language", "is_active")
    search_fields = ("code", "target_code")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")


@admin.register(MrdChecklistLine, site=hms_admin_site)
class MrdChecklistLineAdmin(TenantModelAdmin):
    list_display = ("code", "label", "bucket", "source_type", "source_code", "display_order", "tenant_id")
    list_filter = ("bucket", "source_type", "is_system", "is_active")
    search_fields = ("code", "label", "source_code")
    readonly_fields = ("tenant_id", "created_at", "updated_at", "created_by_user_id")
