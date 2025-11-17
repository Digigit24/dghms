from django.contrib import admin
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import PatientProfile, PatientVitals, PatientAllergy


class PatientVitalsInline(admin.TabularInline):
    model = PatientVitals
    extra = 0
    fields = [
        'temperature', 'blood_pressure_systolic', 'blood_pressure_diastolic',
        'heart_rate', 'oxygen_saturation', 'recorded_by_user_id', 'recorded_at'
    ]
    readonly_fields = ['recorded_at', 'tenant_id']
    can_delete = False


class PatientAllergyInline(admin.TabularInline):
    model = PatientAllergy
    extra = 0
    fields = ['allergy_type', 'allergen', 'severity', 'is_active']
    readonly_fields = ['tenant_id']


class PatientProfileAdmin(TenantModelAdmin):
    list_display = [
        'patient_id', 'full_name', 'age', 'gender', 'mobile_primary',
        'blood_group', 'city', 'status', 'total_visits',
        'registration_date'
    ]
    list_filter = [
        'status', 'gender', 'blood_group', 'marital_status',
        'city', 'state', 'registration_date'
    ]
    search_fields = [
        'patient_id', 'first_name', 'last_name', 'middle_name',
        'mobile_primary', 'email'
    ]
    readonly_fields = [
        'patient_id', 'age', 'bmi', 'registration_date',
        'created_at', 'updated_at', 'tenant_id'
    ]
    inlines = [PatientVitalsInline, PatientAllergyInline]
    ordering = ['-registration_date']
    date_hierarchy = 'registration_date'

    fieldsets = (
        ('Tenant & Identification', {
            'fields': ('tenant_id', 'patient_id', 'user_id', 'status')
        }),
        ('Personal Information', {
            'fields': (
                'first_name', 'middle_name', 'last_name',
                'date_of_birth', 'age', 'gender'
            )
        }),
        ('Contact Information', {
            'fields': (
                'mobile_primary', 'mobile_secondary', 'email'
            )
        }),
        ('Address', {
            'fields': (
                'address_line1', 'address_line2',
                'city', 'state', 'country', 'pincode'
            )
        }),
        ('Medical Information', {
            'fields': (
                'blood_group', 'height', 'weight', 'bmi'
            )
        }),
        ('Social Information', {
            'fields': ('marital_status', 'occupation')
        }),
        ('Emergency Contact', {
            'fields': (
                'emergency_contact_name', 'emergency_contact_phone',
                'emergency_contact_relation'
            )
        }),
        ('Insurance Information', {
            'fields': (
                'insurance_provider', 'insurance_policy_number',
                'insurance_expiry_date'
            ),
            'classes': ('collapse',)
        }),
        ('Hospital Information', {
            'fields': (
                'registration_date', 'last_visit_date', 'total_visits'
            )
        }),
        ('Metadata', {
            'fields': ('created_by_user_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Full Name'
    full_name.admin_order_field = 'first_name'


class PatientVitalsAdmin(TenantModelAdmin):
    list_display = [
        'patient', 'temperature', 'get_blood_pressure',
        'heart_rate', 'oxygen_saturation', 'recorded_by_user_id',
        'recorded_at'
    ]
    list_filter = ['recorded_at']
    search_fields = [
        'patient__patient_id', 'patient__first_name',
        'patient__last_name'
    ]
    readonly_fields = ['recorded_at', 'tenant_id']
    ordering = ['-recorded_at']
    date_hierarchy = 'recorded_at'

    fieldsets = (
        ('Tenant & Patient Information', {
            'fields': ('tenant_id', 'patient', 'recorded_by_user_id')
        }),
        ('Vital Signs', {
            'fields': (
                'temperature', 'blood_pressure_systolic',
                'blood_pressure_diastolic', 'heart_rate',
                'respiratory_rate', 'oxygen_saturation',
                'blood_glucose'
            )
        }),
        ('Additional Information', {
            'fields': ('notes', 'recorded_at')
        }),
    )

    def get_blood_pressure(self, obj):
        return obj.blood_pressure or '-'
    get_blood_pressure.short_description = 'Blood Pressure'


class PatientAllergyAdmin(TenantModelAdmin):
    list_display = [
        'patient', 'allergy_type', 'allergen', 'severity',
        'is_active', 'created_at'
    ]
    list_filter = [
        'allergy_type', 'severity', 'is_active', 'created_at'
    ]
    search_fields = [
        'patient__patient_id', 'patient__first_name',
        'patient__last_name', 'allergen'
    ]
    readonly_fields = ['created_at', 'updated_at', 'tenant_id']
    ordering = ['-severity', 'allergen']

    fieldsets = (
        ('Tenant & Patient Information', {
            'fields': ('tenant_id', 'patient', 'recorded_by_user_id')
        }),
        ('Allergy Details', {
            'fields': (
                'allergy_type', 'allergen', 'severity',
                'symptoms', 'treatment', 'is_active'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# Register models with custom admin site
hms_admin_site.register(PatientProfile, PatientProfileAdmin)
hms_admin_site.register(PatientVitals, PatientVitalsAdmin)
hms_admin_site.register(PatientAllergy, PatientAllergyAdmin)
