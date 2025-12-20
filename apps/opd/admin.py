# opd/admin.py
from django.contrib import admin
from django.utils.html import format_html
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import (
    Visit, OPDBill, ProcedureMaster, ProcedurePackage,
    ProcedureBill, ProcedureBillItem, ClinicalNote,
    VisitFinding, VisitAttachment,
    ClinicalNoteTemplateGroup, ClinicalNoteTemplate,
    ClinicalNoteTemplateField, ClinicalNoteTemplateFieldOption,
    ClinicalNoteTemplateResponse, ClinicalNoteTemplateFieldResponse,
    ClinicalNoteResponseTemplate
)


class VisitAdmin(TenantModelAdmin):
    """Admin interface for Visit model."""

    list_display = [
        'visit_number',
        'patient',
        'doctor',
        'visit_date',
        'visit_type',
        'status',
        'payment_status_badge',
        'total_amount',
    ]
    list_filter = [
        'status',
        'payment_status',
        'visit_type',
        'visit_date',
        'is_follow_up',
    ]
    search_fields = [
        'visit_number',
        'patient__first_name',
        'patient__last_name',
        'doctor__first_name',
        'doctor__last_name',
    ]
    readonly_fields = [
        'visit_number',
        'entry_time',
        'visit_date',
        'created_at',
        'updated_at',
        'tenant_id',
    ]
    autocomplete_fields = ['patient', 'doctor', 'appointment', 'referred_by']

    fieldsets = (
        ('Visit Information', {
            'fields': (
                'visit_number',
                'visit_date',
                'entry_time',
                'visit_type',
                'is_follow_up',
            )
        }),
        ('Patient & Doctor', {
            'fields': (
                'patient',
                'doctor',
                'appointment',
                'referred_by',
            )
        }),
        ('Queue Management', {
            'fields': (
                'status',
                'queue_position',
                'consultation_start_time',
                'consultation_end_time',
            )
        }),
        ('Payment Information', {
            'fields': (
                'payment_status',
                'total_amount',
                'paid_amount',
                'balance_amount',
            )
        }),
        ('Audit', {
            'fields': (
                'created_by_id',
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )
    
    def payment_status_badge(self, obj):
        """Display payment status with color badge."""
        colors = {
            'paid': 'green',
            'partial': 'orange',
            'unpaid': 'red',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.payment_status, 'gray'),
            obj.get_payment_status_display()
        )
    payment_status_badge.short_description = 'Payment Status'


class OPDBillAdmin(TenantModelAdmin):
    """Admin interface for OPDBill model."""

    list_display = [
        'bill_number',
        'visit',
        'doctor',
        'bill_date',
        'total_amount',
        'payable_amount',
        'payment_status_badge',
    ]
    list_filter = [
        'payment_status',
        'opd_type',
        'charge_type',
        'payment_mode',
        'bill_date',
    ]
    search_fields = [
        'bill_number',
        'visit__visit_number',
        'doctor__first_name',
        'doctor__last_name',
    ]
    readonly_fields = [
        'bill_number',
        'bill_date',
        'payable_amount',
        'balance_amount',
        'payment_status',
        'created_at',
        'updated_at',
        'tenant_id',
    ]
    autocomplete_fields = ['visit', 'doctor']

    fieldsets = (
        ('Bill Information', {
            'fields': (
                'bill_number',
                'bill_date',
                'visit',
                'doctor',
            )
        }),
        ('Bill Classification', {
            'fields': (
                'opd_type',
                'opd_subtype',
                'charge_type',
            )
        }),
        ('Medical Details', {
            'fields': (
                'diagnosis',
                'remarks',
            )
        }),
        ('Financial Details', {
            'fields': (
                'total_amount',
                'discount_percent',
                'discount_amount',
                'payable_amount',
            )
        }),
        ('Payment Information', {
            'fields': (
                'payment_mode',
                'payment_details',
                'received_amount',
                'balance_amount',
                'payment_status',
            )
        }),
        ('Audit', {
            'fields': (
                'billed_by_id',
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )
    
    def payment_status_badge(self, obj):
        """Display payment status with color badge."""
        colors = {
            'paid': 'green',
            'partial': 'orange',
            'unpaid': 'red',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.payment_status, 'gray'),
            obj.get_payment_status_display()
        )
    payment_status_badge.short_description = 'Payment Status'


class ProcedureMasterAdmin(TenantModelAdmin):
    """Admin interface for ProcedureMaster model."""

    list_display = [
        'code',
        'name',
        'category',
        'default_charge',
        'is_active_badge',
    ]
    list_filter = [
        'category',
        'is_active',
        'created_at',
    ]
    search_fields = [
        'code',
        'name',
        'description',
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'tenant_id',
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'name',
                'code',
                'category',
                'description',
            )
        }),
        ('Pricing', {
            'fields': (
                'default_charge',
            )
        }),
        ('Status', {
            'fields': (
                'is_active',
            )
        }),
        ('Timestamps', {
            'fields': (
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )
    
    def is_active_badge(self, obj):
        """Display active status with badge."""
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            'green' if obj.is_active else 'red',
            'Active' if obj.is_active else 'Inactive'
        )
    is_active_badge.short_description = 'Status'


class ProcedurePackageAdmin(TenantModelAdmin):
    """Admin interface for ProcedurePackage model."""

    list_display = [
        'code',
        'name',
        'total_charge',
        'discounted_charge',
        'savings_display',
        'is_active_badge',
    ]
    list_filter = [
        'is_active',
        'created_at',
    ]
    search_fields = [
        'code',
        'name',
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'tenant_id',
    ]
    filter_horizontal = ['procedures']

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'name',
                'code',
            )
        }),
        ('Procedures', {
            'fields': (
                'procedures',
            )
        }),
        ('Pricing', {
            'fields': (
                'total_charge',
                'discounted_charge',
            )
        }),
        ('Status', {
            'fields': (
                'is_active',
            )
        }),
        ('Timestamps', {
            'fields': (
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )
    
    def savings_display(self, obj):
        """Display savings amount and percentage."""
        return format_html(
            '₹{} ({}%)',
            obj.savings_amount,
            round(obj.discount_percent, 2)
        )
    savings_display.short_description = 'Savings'
    
    def is_active_badge(self, obj):
        """Display active status with badge."""
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            'green' if obj.is_active else 'red',
            'Active' if obj.is_active else 'Inactive'
        )
    is_active_badge.short_description = 'Status'


class ProcedureBillItemInline(admin.TabularInline):
    """Inline admin for ProcedureBillItem."""
    
    model = ProcedureBillItem
    extra = 1
    fields = [
        'procedure',
        'particular_name',
        'quantity',
        'unit_charge',
        'amount',
        'note',
        'item_order',
    ]
    readonly_fields = ['amount']
    autocomplete_fields = ['procedure']


class ProcedureBillAdmin(TenantModelAdmin):
    """Admin interface for ProcedureBill model."""

    list_display = [
        'bill_number',
        'visit',
        'doctor',
        'bill_date',
        'total_amount',
        'payable_amount',
        'payment_status_badge',
    ]
    list_filter = [
        'payment_status',
        'bill_type',
        'payment_mode',
        'bill_date',
    ]
    search_fields = [
        'bill_number',
        'visit__visit_number',
        'doctor__first_name',
        'doctor__last_name',
    ]
    readonly_fields = [
        'bill_number',
        'bill_date',
        'total_amount',
        'payable_amount',
        'balance_amount',
        'payment_status',
        'created_at',
        'updated_at',
        'tenant_id',
    ]
    autocomplete_fields = ['visit', 'doctor']
    inlines = [ProcedureBillItemInline]

    fieldsets = (
        ('Bill Information', {
            'fields': (
                'bill_number',
                'bill_date',
                'visit',
                'doctor',
            )
        }),
        ('Bill Classification', {
            'fields': (
                'bill_type',
                'category',
            )
        }),
        ('Financial Details', {
            'fields': (
                'total_amount',
                'discount_percent',
                'discount_amount',
                'payable_amount',
            )
        }),
        ('Payment Information', {
            'fields': (
                'payment_mode',
                'payment_details',
                'received_amount',
                'balance_amount',
                'payment_status',
            )
        }),
        ('Audit', {
            'fields': (
                'billed_by_id',
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )
    
    def payment_status_badge(self, obj):
        """Display payment status with color badge."""
        colors = {
            'paid': 'green',
            'partial': 'orange',
            'unpaid': 'red',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.payment_status, 'gray'),
            obj.get_payment_status_display()
        )
    payment_status_badge.short_description = 'Payment Status'


class ClinicalNoteAdmin(TenantModelAdmin):
    """Admin interface for ClinicalNote model."""

    list_display = [
        'visit',
        'note_date',
        'diagnosis_short',
        'next_followup_date',
    ]
    list_filter = [
        'note_date',
        'next_followup_date',
    ]
    search_fields = [
        'visit__visit_number',
        'diagnosis',
        'present_complaints',
    ]
    readonly_fields = [
        'note_date',
        'created_at',
        'updated_at',
        'tenant_id',
    ]
    autocomplete_fields = ['visit', 'referred_doctor']

    fieldsets = (
        ('Visit Information', {
            'fields': (
                'visit',
                'ehr_number',
                'note_date',
            )
        }),
        ('Clinical Assessment', {
            'fields': (
                'present_complaints',
                'observation',
                'diagnosis',
            )
        }),
        ('Treatment', {
            'fields': (
                'investigation',
                'treatment_plan',
                'medicines_prescribed',
                'doctor_advice',
            )
        }),
        ('Surgery/Referral', {
            'fields': (
                'suggested_surgery_name',
                'suggested_surgery_reason',
                'referred_doctor',
            )
        }),
        ('Follow-up', {
            'fields': (
                'next_followup_date',
            )
        }),
        ('Audit', {
            'fields': (
                'created_by_id',
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )
    
    def diagnosis_short(self, obj):
        """Display truncated diagnosis."""
        if obj.diagnosis:
            return obj.diagnosis[:50] + ('...' if len(obj.diagnosis) > 50 else '')
        return '-'
    diagnosis_short.short_description = 'Diagnosis'


class VisitFindingAdmin(TenantModelAdmin):
    """Admin interface for VisitFinding model."""

    list_display = [
        'visit',
        'finding_date',
        'finding_type',
        'temperature',
        'pulse',
        'bp_display',
        'bmi',
        'bmi_category_display',
    ]
    list_filter = [
        'finding_type',
        'finding_date',
    ]
    search_fields = [
        'visit__visit_number',
    ]
    readonly_fields = [
        'bmi',
        'finding_date',
        'created_at',
        'updated_at',
        'tenant_id',
    ]
    autocomplete_fields = ['visit']

    fieldsets = (
        ('Visit Information', {
            'fields': (
                'visit',
                'finding_date',
                'finding_type',
            )
        }),
        ('Vital Signs', {
            'fields': (
                'temperature',
                'pulse',
                'bp_systolic',
                'bp_diastolic',
                'respiratory_rate',
                'spo2',
            )
        }),
        ('Anthropometry', {
            'fields': (
                'weight',
                'height',
                'bmi',
            )
        }),
        ('Systemic Examination', {
            'fields': (
                'tongue',
                'throat',
                'cns',
                'rs',
                'cvs',
                'pa',
            )
        }),
        ('Audit', {
            'fields': (
                'recorded_by_id',
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )
    
    def bp_display(self, obj):
        """Display formatted blood pressure."""
        return obj.blood_pressure or '-'
    bp_display.short_description = 'BP'
    
    def bmi_category_display(self, obj):
        """Display BMI category with color."""
        category = obj.bmi_category
        if not category:
            return '-'
        
        colors = {
            'Underweight': 'orange',
            'Normal': 'green',
            'Overweight': 'orange',
            'Obese': 'red',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(category, 'gray'),
            category
        )
    bmi_category_display.short_description = 'BMI Category'


class VisitAttachmentAdmin(TenantModelAdmin):
    """Admin interface for VisitAttachment model."""

    list_display = [
        'visit',
        'file_name',
        'file_type',
        'file_size_display',
        'uploaded_at',
    ]
    list_filter = [
        'file_type',
        'uploaded_at',
    ]
    search_fields = [
        'visit__visit_number',
        'file_name',
        'description',
    ]
    readonly_fields = [
        'uploaded_at',
        'tenant_id',
    ]
    autocomplete_fields = ['visit']

    fieldsets = (
        ('Attachment Information', {
            'fields': (
                'visit',
                'file',
                'file_name',
                'file_type',
                'description',
            )
        }),
        ('Audit', {
            'fields': (
                'uploaded_by_id',
                'tenant_id',
                'uploaded_at',
            )
        }),
    )
    
    def file_size_display(self, obj):
        """Display file size."""
        return obj.get_file_size() or '-'
    file_size_display.short_description = 'File Size'


# ============================================================================
# CLINICAL NOTE TEMPLATE ADMIN INTERFACES
# ============================================================================

class ClinicalNoteTemplateGroupAdmin(TenantModelAdmin):
    """Admin interface for ClinicalNoteTemplateGroup model."""

    list_display = [
        'name',
        'description_short',
        'template_count',
        'is_active_badge',
        'display_order',
        'created_at',
    ]
    list_filter = [
        'is_active',
        'created_at',
    ]
    search_fields = [
        'name',
        'description',
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'tenant_id',
        'template_count',
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'name',
                'description',
            )
        }),
        ('Display Settings', {
            'fields': (
                'display_order',
                'is_active',
            )
        }),
        ('Statistics', {
            'fields': (
                'template_count',
            )
        }),
        ('Timestamps', {
            'fields': (
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )

    def description_short(self, obj):
        """Display truncated description."""
        if obj.description:
            return obj.description[:50] + ('...' if len(obj.description) > 50 else '')
        return '-'
    description_short.short_description = 'Description'

    def template_count(self, obj):
        """Count of templates in this group."""
        return obj.templates.count()
    template_count.short_description = 'Templates'

    def is_active_badge(self, obj):
        """Display active status with badge."""
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            'green' if obj.is_active else 'red',
            'Active' if obj.is_active else 'Inactive'
        )
    is_active_badge.short_description = 'Status'


class ClinicalNoteTemplateFieldOptionInline(admin.TabularInline):
    """Inline admin for ClinicalNoteTemplateFieldOption."""

    model = ClinicalNoteTemplateFieldOption
    extra = 1
    fields = [
        'option_value',
        'option_label',
        'display_order',
        'is_active',
        'metadata',
    ]
    ordering = ['display_order', 'option_label']


class ClinicalNoteTemplateFieldAdmin(TenantModelAdmin):
    """Admin interface for ClinicalNoteTemplateField model."""

    list_display = [
        'field_label',
        'template',
        'field_type',
        'is_required_badge',
        'display_order',
        'column_width',
        'is_active_badge',
    ]
    list_filter = [
        'field_type',
        'is_required',
        'is_active',
        'template',
    ]
    search_fields = [
        'field_name',
        'field_label',
        'template__name',
        'template__code',
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'tenant_id',
    ]
    autocomplete_fields = ['template']
    inlines = [ClinicalNoteTemplateFieldOptionInline]

    fieldsets = (
        ('Field Definition', {
            'fields': (
                'template',
                'field_name',
                'field_label',
                'field_type',
            )
        }),
        ('Field Configuration', {
            'fields': (
                'help_text',
                'placeholder',
                'default_value',
            )
        }),
        ('Validation Rules', {
            'fields': (
                'is_required',
                'min_value',
                'max_value',
                'min_length',
                'max_length',
            )
        }),
        ('Display Configuration', {
            'fields': (
                'display_order',
                'column_width',
                'show_condition',
            )
        }),
        ('Status', {
            'fields': (
                'is_active',
            )
        }),
        ('Timestamps', {
            'fields': (
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )

    def is_required_badge(self, obj):
        """Display required status with badge."""
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            'red' if obj.is_required else 'gray',
            'Required' if obj.is_required else 'Optional'
        )
    is_required_badge.short_description = 'Required'

    def is_active_badge(self, obj):
        """Display active status with badge."""
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            'green' if obj.is_active else 'red',
            'Active' if obj.is_active else 'Inactive'
        )
    is_active_badge.short_description = 'Status'


class ClinicalNoteTemplateFieldInline(admin.TabularInline):
    """Inline admin for ClinicalNoteTemplateField."""

    model = ClinicalNoteTemplateField
    extra = 0
    fields = [
        'field_name',
        'field_label',
        'field_type',
        'is_required',
        'display_order',
        'is_active',
    ]
    readonly_fields = []
    ordering = ['display_order', 'id']
    show_change_link = True


class ClinicalNoteTemplateAdmin(TenantModelAdmin):
    """Admin interface for ClinicalNoteTemplate model."""

    list_display = [
        'code',
        'name',
        'group',
        'field_count',
        'response_count',
        'is_active_badge',
        'display_order',
        'created_at',
    ]
    list_filter = [
        'is_active',
        'group',
        'created_at',
    ]
    search_fields = [
        'code',
        'name',
        'description',
        'group__name',
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'tenant_id',
        'field_count',
        'response_count',
    ]
    autocomplete_fields = ['group']
    inlines = [ClinicalNoteTemplateFieldInline]

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'name',
                'code',
                'group',
                'description',
            )
        }),
        ('Display Settings', {
            'fields': (
                'display_order',
                'is_active',
            )
        }),
        ('Statistics', {
            'fields': (
                'field_count',
                'response_count',
            )
        }),
        ('Timestamps', {
            'fields': (
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )

    def field_count(self, obj):
        """Count of fields in this template."""
        return obj.fields.count()
    field_count.short_description = 'Fields'

    def response_count(self, obj):
        """Count of responses to this template."""
        return obj.responses.count()
    response_count.short_description = 'Responses'

    def is_active_badge(self, obj):
        """Display active status with badge."""
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            'green' if obj.is_active else 'red',
            'Active' if obj.is_active else 'Inactive'
        )
    is_active_badge.short_description = 'Status'


class ClinicalNoteTemplateFieldOptionAdmin(TenantModelAdmin):
    """Admin interface for ClinicalNoteTemplateFieldOption model."""

    list_display = [
        'option_label',
        'option_value',
        'field',
        'field_type',
        'display_order',
        'is_active_badge',
    ]
    list_filter = [
        'is_active',
        'field__field_type',
        'field__template',
    ]
    search_fields = [
        'option_label',
        'option_value',
        'field__field_label',
        'field__template__name',
    ]
    readonly_fields = [
        'tenant_id',
        'field_type',
    ]
    autocomplete_fields = ['field']

    fieldsets = (
        ('Option Definition', {
            'fields': (
                'field',
                'option_value',
                'option_label',
            )
        }),
        ('Display Settings', {
            'fields': (
                'display_order',
                'is_active',
            )
        }),
        ('Additional Data', {
            'fields': (
                'metadata',
            )
        }),
        ('Information', {
            'fields': (
                'tenant_id',
                'field_type',
            )
        }),
    )

    def field_type(self, obj):
        """Display field type."""
        return obj.field.get_field_type_display()
    field_type.short_description = 'Field Type'

    def is_active_badge(self, obj):
        """Display active status with badge."""
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            'green' if obj.is_active else 'red',
            'Active' if obj.is_active else 'Inactive'
        )
    is_active_badge.short_description = 'Status'


class ClinicalNoteTemplateFieldResponseInline(admin.TabularInline):
    """Inline admin for ClinicalNoteTemplateFieldResponse."""

    model = ClinicalNoteTemplateFieldResponse
    extra = 0
    fields = [
        'field',
        'value_display',
        'updated_at',
    ]
    readonly_fields = [
        'field',
        'value_display',
        'updated_at',
    ]
    ordering = ['field__display_order']
    can_delete = False

    def value_display(self, obj):
        """Display the field value in a readable format."""
        return obj.get_display_value() or '-'
    value_display.short_description = 'Value'

    def has_add_permission(self, request, obj=None):
        """Disable adding responses through admin."""
        return False


class ClinicalNoteTemplateResponseAdmin(TenantModelAdmin):
    """Admin interface for ClinicalNoteTemplateResponse model (Read-Only)."""

    list_display = [
        'encounter_display_admin',
        'template',
        'response_sequence',
        'status_badge',
        'is_reviewed_badge',
        'response_date',
        'filled_by_id',
        'reviewed_by_id',
        'field_response_count',
    ]
    list_filter = [
        'status',
        'is_reviewed',
        'response_date',
        'template',
        'response_sequence',
        'content_type',
    ]
    search_fields = [
        'template__name',
        'template__code',
        'filled_by_id',
        'doctor_switched_reason',
    ]
    readonly_fields = [
        'content_type',
        'object_id',
        'encounter_display_admin',
        'template',
        'response_date',
        'status',
        'response_summary',
        'filled_by_id',
        'reviewed_by_id',
        'reviewed_at',
        'created_at',
        'updated_at',
        'tenant_id',
        'field_response_count',
        'response_sequence',
        'is_reviewed',
        'original_assigned_doctor_id',
        'doctor_switched_reason',
        'canvas_data',
    ]

    def encounter_display_admin(self, obj):
        """Display encounter information in admin."""
        if obj.encounter:
            if hasattr(obj.encounter, 'visit_number'):
                return f"OPD: {obj.encounter.visit_number}"
            elif hasattr(obj.encounter, 'admission_id'):
                return f"IPD: {obj.encounter.admission_id}"
        return "No Encounter"
    encounter_display_admin.short_description = 'Encounter'
    autocomplete_fields = []
    inlines = [ClinicalNoteTemplateFieldResponseInline]

    fieldsets = (
        ('Encounter Information', {
            'fields': (
                'content_type',
                'object_id',
                'encounter_display_admin',
            )
        }),
        ('Response Information', {
            'fields': (
                'template',
                'response_sequence',
                'response_date',
                'status',
                'is_reviewed',
            )
        }),
        ('Multiple Doctor Support', {  # NEW
            'fields': (
                'original_assigned_doctor_id',
                'doctor_switched_reason',
            ),
            'classes': ('collapse',)
        }),
        ('Canvas Data', {  # NEW
            'fields': (
                'canvas_data',
            ),
            'classes': ('collapse',)
        }),
        ('Response Data', {
            'fields': (
                'response_summary',
            )
        }),
        ('Statistics', {
            'fields': (
                'field_response_count',
            )
        }),
        ('Audit Trail', {
            'fields': (
                'filled_by_id',
                'reviewed_by_id',
                'reviewed_at',
            )
        }),
        ('Timestamps', {
            'fields': (
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )

    def field_response_count(self, obj):
        """Count of field responses."""
        return obj.field_responses.count()
    field_response_count.short_description = 'Field Responses'

    def status_badge(self, obj):
        """Display status with color badge."""
        colors = {
            'draft': 'gray',
            'completed': 'green',
            'reviewed': 'blue',
            'archived': 'orange',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.status, 'gray'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def is_reviewed_badge(self, obj):
        """Display reviewed status with badge."""
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            'blue' if obj.is_reviewed else 'gray',
            'Reviewed' if obj.is_reviewed else 'Pending'
        )
    is_reviewed_badge.short_description = 'Review Status'

    def has_add_permission(self, request):
        """Disable adding responses through admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deleting responses through admin."""
        return False


class ClinicalNoteTemplateFieldResponseAdmin(TenantModelAdmin):
    """Admin interface for ClinicalNoteTemplateFieldResponse model (Read-Only)."""

    list_display = [
        'response',
        'field',
        'field_type',
        'value_display',
        'updated_at',
    ]
    list_filter = [
        'field__field_type',
        'response__template',
        'updated_at',
    ]
    search_fields = [
        'response__visit__visit_number',
        'field__field_label',
        'field__field_name',
        'value_text',
    ]
    readonly_fields = [
        'response',
        'field',
        'field_type',
        'value_text',
        'value_number',
        'value_boolean',
        'value_date',
        'value_datetime',
        'value_time',
        'value_json',
        'value_file',
        'full_canvas_json',
        'canvas_thumbnail',
        'canvas_version_history',
        'value_display',
        'created_at',
        'updated_at',
        'tenant_id',
    ]
    autocomplete_fields = []
    filter_horizontal = []

    fieldsets = (
        ('Field Response Information', {
            'fields': (
                'response',
                'field',
                'field_type',
            )
        }),
        ('Value Storage', {
            'fields': (
                'value_text',
                'value_number',
                'value_boolean',
                'value_date',
                'value_datetime',
                'value_time',
                'value_json',
                'value_file',
                'selected_options',
            )
        }),
        ('Canvas Input', {
            'fields': (
                'full_canvas_json',
                'canvas_thumbnail',
                'canvas_version_history',
            ),
            'classes': ('collapse',)
        }),
        ('Display Value', {
            'fields': (
                'value_display',
            )
        }),
        ('Timestamps', {
            'fields': (
                'tenant_id',
                'created_at',
                'updated_at',
            )
        }),
    )

    def field_type(self, obj):
        """Display field type."""
        return obj.field.get_field_type_display()
    field_type.short_description = 'Field Type'

    def value_display(self, obj):
        """Display the field value in a readable format."""
        return obj.get_display_value() or '-'
    value_display.short_description = 'Value'

    def has_add_permission(self, request):
        """Disable adding field responses through admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deleting field responses through admin."""
        return False


# ============================================================================
# CLINICAL NOTE RESPONSE TEMPLATE ADMIN (Copy-Paste Templates)
# ============================================================================

class ClinicalNoteResponseTemplateAdmin(TenantModelAdmin):
    """Admin interface for ClinicalNoteResponseTemplate model."""

    list_display = [
        'name',
        'description_short',
        'usage_count',
        'is_active_badge',
        'created_by_id',
        'created_at',
    ]
    list_filter = [
        'is_active',
        'created_at',
        'updated_at',
    ]
    search_fields = [
        'name',
        'description',
        'created_by_id',
    ]
    readonly_fields = [
        'usage_count',
        'created_by_id',
        'source_response',
        'created_at',
        'updated_at',
        'tenant_id',
    ]

    fieldsets = (
        ('Template Information', {
            'fields': (
                'name',
                'description',
                'is_active',
            )
        }),
        ('Source', {
            'fields': (
                'source_response',
            ),
            'classes': ('collapse',)
        }),
        ('Template Data', {
            'fields': (
                'template_field_values',
            )
        }),
        ('Statistics', {
            'fields': (
                'usage_count',
            )
        }),
        ('Audit', {
            'fields': (
                'created_by_id',
                'tenant_id',
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )

    def description_short(self, obj):
        """Display truncated description."""
        if obj.description:
            return obj.description[:50] + ('...' if len(obj.description) > 50 else '')
        return '-'
    description_short.short_description = 'Description'

    def is_active_badge(self, obj):
        """Display active status with badge."""
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            'green' if obj.is_active else 'red',
            'Active' if obj.is_active else 'Inactive'
        )
    is_active_badge.short_description = 'Status'


# Enable autocomplete for Patient and Doctor models in other apps
# Add these to patients/admin.py and doctors/admin.py respectively

# In patients/admin.py:
# @admin.register(Patient)
# class PatientAdmin(admin.ModelAdmin):
#     search_fields = ['first_name', 'last_name', 'phone', 'email']

# In doctors/admin.py:
# @admin.register(Doctor)
# class DoctorAdmin(admin.ModelAdmin):
#     search_fields = ['first_name', 'last_name', 'phone', 'email', 'specialization']

# Register models with custom admin site
hms_admin_site.register(Visit, VisitAdmin)
hms_admin_site.register(OPDBill, OPDBillAdmin)
hms_admin_site.register(ProcedureMaster, ProcedureMasterAdmin)
hms_admin_site.register(ProcedurePackage, ProcedurePackageAdmin)
hms_admin_site.register(ProcedureBill, ProcedureBillAdmin)
hms_admin_site.register(ClinicalNote, ClinicalNoteAdmin)
hms_admin_site.register(VisitFinding, VisitFindingAdmin)
hms_admin_site.register(VisitAttachment, VisitAttachmentAdmin)

# Register Clinical Note Template models
hms_admin_site.register(ClinicalNoteTemplateGroup, ClinicalNoteTemplateGroupAdmin)
hms_admin_site.register(ClinicalNoteTemplate, ClinicalNoteTemplateAdmin)
hms_admin_site.register(ClinicalNoteTemplateField, ClinicalNoteTemplateFieldAdmin)
hms_admin_site.register(ClinicalNoteTemplateFieldOption, ClinicalNoteTemplateFieldOptionAdmin)
hms_admin_site.register(ClinicalNoteTemplateResponse, ClinicalNoteTemplateResponseAdmin)
hms_admin_site.register(ClinicalNoteTemplateFieldResponse, ClinicalNoteTemplateFieldResponseAdmin)
hms_admin_site.register(ClinicalNoteResponseTemplate, ClinicalNoteResponseTemplateAdmin)
