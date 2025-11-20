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

    def save_model(self, request, obj, form, change):
        """Automatically set tenant_id for inline vitals"""
        if not change and hasattr(request, 'session'):
            user_data = request.session.get('user_data', {})
            tenant_id = user_data.get('tenant_id')
            if tenant_id and hasattr(obj, 'tenant_id') and not obj.tenant_id:
                import uuid
                if isinstance(tenant_id, str):
                    try:
                        tenant_id = uuid.UUID(tenant_id)
                    except ValueError:
                        tenant_id = None
                if tenant_id:
                    obj.tenant_id = tenant_id
        return super().save_model(request, obj, form, change)


class PatientAllergyInline(admin.TabularInline):
    model = PatientAllergy
    extra = 0
    fields = ['allergy_type', 'allergen', 'severity', 'is_active']
    readonly_fields = ['tenant_id']

    def save_model(self, request, obj, form, change):
        """Automatically set tenant_id for inline allergies"""
        if not change and hasattr(request, 'session'):
            user_data = request.session.get('user_data', {})
            tenant_id = user_data.get('tenant_id')
            if tenant_id and hasattr(obj, 'tenant_id') and not obj.tenant_id:
                import uuid
                if isinstance(tenant_id, str):
                    try:
                        tenant_id = uuid.UUID(tenant_id)
                    except ValueError:
                        tenant_id = None
                if tenant_id:
                    obj.tenant_id = tenant_id
        return super().save_model(request, obj, form, change)


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
        'created_at', 'updated_at'
    ]
    inlines = [PatientVitalsInline, PatientAllergyInline]
    ordering = ['-registration_date']
    date_hierarchy = 'registration_date'

    def get_readonly_fields(self, request, obj=None):
        """Make tenant_id readonly only when editing existing objects"""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj:  # Editing existing object
            if 'tenant_id' not in readonly:
                readonly.append('tenant_id')
        return readonly

    def get_form(self, request, obj=None, **kwargs):
        """Customize form to add help text for tenant_id"""
        form = super().get_form(request, obj, **kwargs)

        # Add help text for tenant_id when creating new objects
        if not obj and 'tenant_id' in form.base_fields:
            # Try to get tenant_id from session or user
            tenant_id = None
            if hasattr(request, 'session'):
                user_data = request.session.get('user_data', {})
                tenant_id = user_data.get('tenant_id')
            if not tenant_id and hasattr(request, 'user') and hasattr(request.user, 'tenant_id'):
                tenant_id = request.user.tenant_id

            if tenant_id:
                form.base_fields['tenant_id'].help_text = f'Auto-detected tenant ID: {tenant_id}'
                # Pre-fill the tenant_id field
                form.base_fields['tenant_id'].initial = tenant_id
            else:
                form.base_fields['tenant_id'].help_text = 'Enter your tenant UUID. If you do not know it, contact your administrator.'

        return form

    fieldsets = (
        ('Tenant & Identification', {
            'fields': ('tenant_id', 'patient_id', 'user_id', 'status'),
            'description': 'Tenant ID is required. Enter your tenant UUID or it will be auto-filled from your session.'
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

    def save_formset(self, request, form, formset, change):
        """Override to set tenant_id on inline objects"""
        instances = formset.save(commit=False)

        # Get tenant_id from session first
        tenant_id = None
        if hasattr(request, 'session'):
            user_data = request.session.get('user_data', {})
            tenant_id = user_data.get('tenant_id')

        # Fallback: try to get tenant_id from authenticated user (JWT)
        if not tenant_id and hasattr(request, 'user') and request.user:
            if hasattr(request.user, 'tenant_id'):
                tenant_id = request.user.tenant_id

        # Convert string UUID to UUID object if needed
        if tenant_id:
            import uuid
            if isinstance(tenant_id, str):
                try:
                    tenant_id = uuid.UUID(tenant_id)
                except ValueError:
                    tenant_id = None

        # Set tenant_id on each inline instance
        for instance in instances:
            if tenant_id and hasattr(instance, 'tenant_id') and not instance.tenant_id:
                instance.tenant_id = tenant_id
            instance.save()

        formset.save_m2m()

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
    readonly_fields = ['recorded_at']
    ordering = ['-recorded_at']
    date_hierarchy = 'recorded_at'

    def get_readonly_fields(self, request, obj=None):
        """Make tenant_id readonly only when editing"""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and 'tenant_id' not in readonly:
            readonly.append('tenant_id')
        return readonly

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
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-severity', 'allergen']

    def get_readonly_fields(self, request, obj=None):
        """Make tenant_id readonly only when editing"""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and 'tenant_id' not in readonly:
            readonly.append('tenant_id')
        return readonly

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
