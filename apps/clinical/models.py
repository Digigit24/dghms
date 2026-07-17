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
    """A reusable clinical section definition.

    Forms compose these definitions through FormSectionPlacement. The legacy
    class name is kept so existing imports and migrations stay in the clinical
    app while the model semantics move to reusable sections.
    """

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_system = models.BooleanField(default=False, help_text="System sections are seeded and protected")
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_form_sections"
        ordering = ["code", "id"]
        unique_together = [["tenant_id", "code"]]
        indexes = [
            models.Index(fields=["tenant_id", "code"]),
            models.Index(fields=["tenant_id", "is_system"]),
        ]

    def __str__(self):
        return f"{self.code} / {self.title}"


class FormSectionPlacement(models.Model):
    """Places a reusable section definition inside a form."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    form = models.ForeignKey(
        ClinicalForm,
        on_delete=models.CASCADE,
        related_name="section_placements",
        db_index=True,
    )
    section = models.ForeignKey(
        ClinicalFormSection,
        on_delete=models.PROTECT,
        related_name="form_placements",
        db_index=True,
    )
    instance_key = models.CharField(max_length=64, blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)
    title_override = models.CharField(max_length=200, blank=True, default="")
    is_collapsed = models.BooleanField(default=False)
    visibility_rule = models.JSONField(default=dict, blank=True)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_form_section_placements"
        ordering = ["form", "display_order", "id"]
        unique_together = [["tenant_id", "form", "section", "instance_key"]]
        indexes = [
            models.Index(fields=["tenant_id", "form", "display_order"]),
            models.Index(fields=["tenant_id", "section"]),
        ]

    def __str__(self):
        suffix = f":{self.instance_key}" if self.instance_key else ""
        return f"{self.form.code} / {self.section.code}{suffix}"


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
        TIME = "time", "Time"
        YES_NO = "yes_no", "Yes / No / NA"
        GRID = "grid", "Grid"
        SIGNATURE = "signature", "Signature"
        HEADING = "heading", "Heading"
        DATA_REF = "data_ref", "Data Reference"
        RICH_TEXT = "rich_text", "Rich Text"
        API_SELECT = "api_select", "API Select"  # options from a live app API (e.g. doctors), not a picklist
        PAIN_FACES = "pain_faces", "Pain Faces Scale"  # Wong-Baker style 0-10 face selector
        BODY_DIAGRAM = "body_diagram", "Body Diagram"

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
    label_mr = models.CharField(max_length=255, blank=True, default="")
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
        return f"{self.section.code} / {self.field_key}"


class ClinicalFormGroup(models.Model):
    """Groups forms for drawers, tabs, workflows, and left-rail navigation."""

    class GroupType(models.TextChoices):
        DRAWER_SECTION = "drawer_section", "Drawer Section"
        TAB_SET = "tab_set", "Tab Set"
        WORKFLOW = "workflow", "Workflow"
        LEFT_RAIL = "left_rail", "Left Rail"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=200)
    group_type = models.CharField(max_length=32, choices=GroupType.choices, default=GroupType.DRAWER_SECTION)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    entity_type = models.CharField(max_length=32, choices=ClinicalForm.EntityType.choices, default=ClinicalForm.EntityType.GENERIC)
    display_order = models.PositiveIntegerField(default=0)
    is_system = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_form_groups"
        ordering = ["display_order", "id"]
        unique_together = [["tenant_id", "code"]]
        indexes = [
            models.Index(fields=["tenant_id", "entity_type", "display_order"]),
            models.Index(fields=["tenant_id", "parent", "display_order"]),
        ]

    def __str__(self):
        return self.name


class ClinicalFormGroupItem(models.Model):
    """Attaches a form to a group with display metadata."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    group = models.ForeignKey(ClinicalFormGroup, on_delete=models.CASCADE, related_name="items", db_index=True)
    form = models.ForeignKey(ClinicalForm, on_delete=models.CASCADE, related_name="group_items", db_index=True)
    display_order = models.PositiveIntegerField(default=0)
    badge_when_filled = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_form_group_items"
        ordering = ["group", "display_order", "id"]
        unique_together = [["tenant_id", "group", "form"]]
        indexes = [
            models.Index(fields=["tenant_id", "group", "display_order"]),
            models.Index(fields=["tenant_id", "form"]),
        ]

    def __str__(self):
        return f"{self.group.code} / {self.form.code}"


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
    label_mr = models.CharField(max_length=255, blank=True, default="")
    label_hi = models.CharField(max_length=255, blank=True, default="")
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


class ClinicalPicklistGroup(models.Model):
    """Groups related picklists for authoring and UI discovery."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_system = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_picklist_groups"
        ordering = ["code", "id"]
        unique_together = [["tenant_id", "code"]]
        indexes = [models.Index(fields=["tenant_id", "is_system"])]

    def __str__(self):
        return self.name


class ClinicalPicklistGroupMembership(models.Model):
    """Attaches a picklist to a picklist group."""

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    group = models.ForeignKey(ClinicalPicklistGroup, on_delete=models.CASCADE, related_name="memberships")
    picklist = models.ForeignKey(ClinicalPicklist, on_delete=models.CASCADE, related_name="group_memberships")
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_picklist_group_memberships"
        ordering = ["group", "display_order", "id"]
        unique_together = [["tenant_id", "group", "picklist"]]
        indexes = [
            models.Index(fields=["tenant_id", "group", "display_order"]),
            models.Index(fields=["tenant_id", "picklist"]),
        ]


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
    occurrence_index = models.PositiveIntegerField(
        default=1,
        db_index=True,
        help_text=(
            "1-based instance number for repeatable forms (e.g. round notes, "
            "monitoring charts). Non-repeatable forms always use 1."
        ),
    )
    patient_user_id = models.UUIDField(null=True, blank=True, db_index=True, help_text="Optional denormalized patient UUID")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    is_locked = models.BooleanField(default=False)
    locked_by_user_id = models.UUIDField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    form_version = models.PositiveIntegerField(default=1)
    structure_snapshot = models.JSONField(default=None, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_records"
        ordering = ["-created_at"]
        unique_together = [["tenant_id", "form", "encounter_type", "encounter_id", "occurrence_index"]]
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
    value_datetime = models.DateTimeField(null=True, blank=True)
    value_time = models.TimeField(null=True, blank=True)
    value_json = models.JSONField(default=None, null=True, blank=True)
    picklist_item = models.ForeignKey(
        ClinicalPicklistItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="field_values",
    )
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
            models.Index(fields=["tenant_id", "picklist_item"]),
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


class ClinicalDocumentTemplate(models.Model):
    """Consent, stationery, and certificate template metadata."""

    class DocumentType(models.TextChoices):
        CONSENT = "consent", "Consent"
        STATIONERY = "stationery", "Stationery"
        CERTIFICATE = "certificate", "Certificate"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=200)
    doc_type = models.CharField(max_length=32, choices=DocumentType.choices)
    bucket = models.CharField(max_length=32, default="none")
    languages = models.JSONField(default=list, blank=True)
    requires_signature = models.BooleanField(default=False)
    applicable_entity_types = models.JSONField(default=list, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_system = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    body_ref = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_document_templates"
        ordering = ["display_order", "id"]
        unique_together = [["tenant_id", "code"]]
        indexes = [
            models.Index(fields=["tenant_id", "doc_type", "bucket"]),
            models.Index(fields=["tenant_id", "is_system"]),
        ]

    def __str__(self):
        return self.name


class ClinicalDocumentInstance(models.Model):
    """Generated/printed/signed document instance for an encounter."""

    class Status(models.TextChoices):
        GENERATED = "generated", "Generated"
        PRINTED = "printed", "Printed"
        SIGNED = "signed", "Signed"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    template = models.ForeignKey(ClinicalDocumentTemplate, on_delete=models.PROTECT, related_name="instances")
    encounter_type = models.CharField(max_length=32, db_index=True)
    encounter_id = models.PositiveIntegerField(db_index=True)
    language = models.CharField(max_length=8, default="en")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.GENERATED)
    generated_pdf_url = models.URLField(max_length=1024, blank=True, default="")
    printed_by_user_id = models.UUIDField(null=True, blank=True)
    printed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_document_instances"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "encounter_type", "encounter_id"]),
            models.Index(fields=["tenant_id", "template", "status"]),
        ]


class ClinicalPrintTemplate(models.Model):
    """HTML template for form/document printing."""

    class TargetType(models.TextChoices):
        FORM = "form", "Form"
        DOCUMENT = "document", "Document"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=32, choices=TargetType.choices)
    target_code = models.CharField(max_length=64, db_index=True)
    layout = models.CharField(max_length=32, default="letterhead")
    language = models.CharField(max_length=8, default="en")
    html = models.TextField(blank=True, default="")
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_print_templates"
        ordering = ["target_type", "target_code", "language", "layout"]
        unique_together = [["tenant_id", "code"]]
        indexes = [
            models.Index(fields=["tenant_id", "target_type", "target_code"]),
            models.Index(fields=["tenant_id", "language", "layout"]),
        ]


class MrdChecklistLine(models.Model):
    """Seed/config line for an encounter MRD checklist."""

    class SourceType(models.TextChoices):
        FORM = "form", "Form"
        DOCUMENT = "document", "Document"
        NONE = "none", "None"

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=255)
    bucket = models.CharField(max_length=32, default="gen")
    source_type = models.CharField(max_length=32, choices=SourceType.choices, default=SourceType.NONE)
    source_code = models.CharField(max_length=64, blank=True, default="")
    applicable_entity_types = models.JSONField(default=list, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_mrd_checklist_lines"
        ordering = ["bucket", "display_order", "id"]
        unique_together = [["tenant_id", "code"]]
        indexes = [
            models.Index(fields=["tenant_id", "bucket", "display_order"]),
            models.Index(fields=["tenant_id", "source_type", "source_code"]),
        ]


class ClinicalFormTemplate(models.Model):
    """A named, reusable set of field values for a form (e.g. a prescription template).

    Templates capture a snapshot of a form's ``{field_key: value}`` map so a
    clinician can save the current form as a template and reload it later.
    """

    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField(db_index=True)
    form = models.ForeignKey(
        ClinicalForm,
        on_delete=models.CASCADE,
        related_name="value_templates",
        db_index=True,
    )
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=500, blank=True, default="")
    values = models.JSONField(default=dict, blank=True, help_text="Map of field_key -> value.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by_user_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "clinical_form_templates"
        ordering = ["name", "id"]
        unique_together = [["tenant_id", "form", "name"]]
        indexes = [
            models.Index(fields=["tenant_id", "form"]),
        ]

    def __str__(self):
        return f"{self.form.code} / {self.name}"


ClinicalSection = ClinicalFormSection
ClinicalField = ClinicalFormField
