# opd/admin.py
from django.contrib import admin
from django.utils.html import format_html
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import (
    Visit, OPDBill, ProcedureMaster, ProcedurePackage,
    ProcedureBill, ProcedureBillItem, ClinicalNote,
    VisitFinding, VisitAttachment
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
