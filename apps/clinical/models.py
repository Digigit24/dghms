"""Clinical forms, records, and value storage for DigiHMS.

This module implements the new clinical documentation system. Legacy OPD/IPD
encounters are referenced via ``encounter_type`` + ``encounter_id`` (D-08) so
no frozen apps are modified.
"""


from django.db import models


class ClinicalForm(models.Model):
    """A reusable clinical form template (vitals, history, notes, etc.)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        STAGING = "staging", "Staging"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class EntityType(models.TextChoices):
        OPD_VISIT = "opd_visit", "OPD Visit"
        IPD_ADMISSION = "ipd_admission", "IPD Admission"
        GENERIC = "generic", "Generic"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64, db_index=True, help_text="Stable machine identifier for MCP")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_system = models.BooleanField(default=False, help_text="System forms are seeded and protected")
    entity_type = models.CharField(max_length=32, choices=EntityType.choices, default=EntityType.GENERIC)
    config = models.JSONField(default=dict, blank=True, help_text="Layout/display configuration")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_forms"
        ordering = ["-created_at"]
        unique_together = [["tenant_id", "code"]]
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "entity_type"]),
            models.Index(fields=["tenant_id", "is_system"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class ClinicalFormSection(models.Model):
    """A logical section within a clinical form."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    form = models.ForeignKey(
        ClinicalForm,
        on_delete=models.CASCADE,
        related_name="sections",
        db_index=True,
    )
    code = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)
    is_collapsed = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_form_sections"
        ordering = ["form", "display_order", "id"]
        unique_together = [["tenant_id", "form", "code"]]
        indexes = [
            models.Index(fields=["tenant_id", "form", "display_order"]),
        ]

    def __str__(self):
        return f"{self.form.code} / {self.title}"


class ClinicalFormField(models.Model):
    """A single field/question inside a clinical form section."""

    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        TEXTAREA = "textarea", "Text Area"
        NUMBER = "number", "Number"
        BOOLEAN = "boolean", "Boolean"
        DATE = "date", "Date"
        DATETIME = "datetime", "Date Time"
        PICKLIST = "picklist", "Picklist"
        MULTISELECT = "multiselect", "Multi-select"
        FILE = "file", "File"
        CALCULATED = "calculated", "Calculated"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    section = models.ForeignKey(
        ClinicalFormSection,
        on_delete=models.CASCADE,
        related_name="fields",
        db_index=True,
    )
    field_key = models.CharField(max_length=64, db_index=True, help_text="Stable identifier within the form")
    field_type = models.CharField(max_length=32, choices=FieldType.choices, default=FieldType.TEXT)
    label = models.CharField(max_length=255)
    help_text = models.CharField(max_length=500, blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=False)
    is_read_only = models.BooleanField(default=False)
    default_value = models.JSONField(default=None, null=True, blank=True)
    config = models.JSONField(default=dict, blank=True, help_text="Validation rules, display logic, etc.")
    picklist = models.ForeignKey(
        "ClinicalPicklist",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="form_fields",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_form_fields"
        ordering = ["section", "display_order", "id"]
        unique_together = [["tenant_id", "section", "field_key"]]
        indexes = [
            models.Index(fields=["tenant_id", "section", "display_order"]),
        ]

    def __str__(self):
        return f"{self.section.form.code} / {self.field_key}"


class ClinicalPicklist(models.Model):
    """A reusable list of options for picklist/multiselect fields."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64, db_index=True, help_text="Stable machine identifier")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_system = models.BooleanField(default=False, help_text="System picklists are seeded and protected")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_picklists"
        ordering = ["-created_at"]
        unique_together = [["tenant_id", "code"]]
        indexes = [
            models.Index(fields=["tenant_id", "is_system"]),
        ]

    def __str__(self):
        return self.name


class ClinicalPicklistItem(models.Model):
    """A single option within a clinical picklist."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    picklist = models.ForeignKey(
        ClinicalPicklist,
        on_delete=models.CASCADE,
        related_name="items",
        db_index=True,
    )
    label = models.CharField(max_length=255)
    value = models.CharField(max_length=255, db_index=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_picklist_items"
        ordering = ["picklist", "display_order", "id"]
        unique_together = [["tenant_id", "picklist", "value"]]
        indexes = [
            models.Index(fields=["tenant_id", "picklist", "display_order"]),
        ]

    def __str__(self):
        return f"{self.picklist.code} / {self.label}"


class ClinicalRecord(models.Model):
    """An instance of a clinical form filled for a specific encounter."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        LOCKED = "locked", "Locked"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    form = models.ForeignKey(
        ClinicalForm,
        on_delete=models.PROTECT,
        related_name="records",
        db_index=True,
    )
    encounter_type = models.CharField(max_length=32, db_index=True, help_text="e.g. opd_visit, ipd_admission")
    encounter_id = models.PositiveIntegerField(db_index=True)
    patient_user_id = models.UUIDField(null=True, blank=True, db_index=True, help_text="Optional denormalized patient UUID")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    is_locked = models.BooleanField(default=False)
    locked_by_user_id = models.UUIDField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_records"
        ordering = ["-created_at"]
        unique_together = [["tenant_id", "form", "encounter_type", "encounter_id"]]
        indexes = [
            models.Index(fields=["tenant_id", "encounter_type", "encounter_id"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "patient_user_id"]),
        ]

    def __str__(self):
        return f"{self.form.code} / {self.encounter_type}:{self.encounter_id}"


class ClinicalFieldValue(models.Model):
    """Typed value for a single field in a clinical record.

    Values are stored in the column matching the field type so that queries
    and coercions are reliable (D-09).
    """

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    record = models.ForeignKey(
        ClinicalRecord,
        on_delete=models.CASCADE,
        related_name="field_values",
        db_index=True,
    )
    field = models.ForeignKey(
        ClinicalFormField,
        on_delete=models.PROTECT,
        related_name="field_values",
        db_index=True,
    )
    value_text = models.TextField(null=True, blank=True)
    value_number = models.DecimalField(max_digits=19, decimal_places=6, null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_json = models.JSONField(default=None, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_field_values"
        ordering = ["record", "field__display_order"]
        unique_together = [["tenant_id", "record", "field"]]
        indexes = [
            models.Index(fields=["tenant_id", "record"]),
            models.Index(fields=["tenant_id", "field"]),
        ]

    def __str__(self):
        return f"{self.record_id} / {self.field.field_key}"


class UserFormPreference(models.Model):
    """Per-user display preferences for a clinical form."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    user_id = models.UUIDField(db_index=True, help_text="SuperAdmin User ID")
    form = models.ForeignKey(
        ClinicalForm,
        on_delete=models.CASCADE,
        related_name="user_preferences",
        db_index=True,
    )
    config = models.JSONField(default=dict, blank=True, help_text="Collapsed sections, default values, etc.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_user_form_preferences"
        ordering = ["-created_at"]
        unique_together = [["tenant_id", "user_id", "form"]]

    def __str__(self):
        return f"{self.user_id} / {self.form.code}"


class SavedFormSnapshot(models.Model):
    """A point-in-time snapshot of a clinical record."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    record = models.ForeignKey(
        ClinicalRecord,
        on_delete=models.CASCADE,
        related_name="snapshots",
        db_index=True,
    )
    name = models.CharField(max_length=200)
    snapshot_data = models.JSONField(default=dict, help_text="Serialized record + field values")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_saved_form_snapshots"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "record"]),
        ]

    def __str__(self):
        return f"{self.record_id} / {self.name}"


class ClinicalRecordAuditLog(models.Model):
    """Append-only audit trail for clinical record changes (NABH compliant).

    This model intentionally has no ``updated_at`` field (R-10).
    """

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        LOCKED = "locked", "Locked"
        UNLOCKED = "unlocked", "Unlocked"
        SNAPSHOT_CREATED = "snapshot_created", "Snapshot Created"
        FIELD_VALUES_UPSERTED = "field_values_upserted", "Field Values Upserted"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    record = models.ForeignKey(
        ClinicalRecord,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        db_index=True,
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    user_id = models.UUIDField(db_index=True, help_text="SuperAdmin User ID who performed the action")
    metadata = models.JSONField(default=dict, blank=True, help_text="Ids and codes only; no field values")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_record_audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "-created_at"]),
            models.Index(fields=["tenant_id", "record", "-created_at"]),
        ]

    def __str__(self):
        return f"AuditLog {self.action} on record {self.record_id}"


class ClinicalFormGenerationRequest(models.Model):
    """Tracks an AI-generated form draft from a natural-language prompt."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        APPLIED = "applied", "Applied"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    prompt = models.TextField(help_text="Natural-language description of the form to generate.")
    extra_instructions = models.TextField(blank=True, default="", help_text="Additional constraints for the AI.")
    entity_type = models.CharField(
        max_length=32,
        choices=ClinicalForm.EntityType.choices,
        default=ClinicalForm.EntityType.GENERIC,
        help_text="The encounter type this form is meant for.",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    generated_draft = models.JSONField(
        null=True, blank=True, default=None, help_text="AI-generated form schema."
    )
    error_message = models.TextField(blank=True, default="")
    applied_form = models.ForeignKey(
        ClinicalForm,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_generation_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_form_generation_requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "applied_form"]),
        ]

    def __str__(self):
        return f"GenerationRequest {self.id} [{self.status}]"
