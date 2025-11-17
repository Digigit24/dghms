from django.contrib import admin
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import Specialty, DoctorProfile, DoctorAvailability


class SpecialtyAdmin(TenantModelAdmin):
    """Admin for Medical Specialties"""
    list_display = ['name', 'code', 'department', 'is_active', 'doctors_count', 'created_at']
    list_filter = ['is_active', 'department', 'created_at']
    search_fields = ['name', 'code', 'description']
    readonly_fields = ['created_at', 'updated_at', 'tenant_id']
    ordering = ['name']

    fieldsets = (
        ('Tenant', {
            'fields': ('tenant_id',)
        }),
        ('Basic Information', {
            'fields': ('name', 'code', 'department')
        }),
        ('Details', {
            'fields': ('description', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def doctors_count(self, obj):
        """Count of active doctors in this specialty"""
        return obj.doctors.filter(status='active').count()
    doctors_count.short_description = 'Active Doctors'


class DoctorAvailabilityInline(admin.TabularInline):
    """Inline admin for Doctor Availability"""
    model = DoctorAvailability
    extra = 1
    fields = ['day_of_week', 'start_time', 'end_time', 'is_available', 'max_appointments']
    readonly_fields = ['tenant_id']


class DoctorProfileAdmin(TenantModelAdmin):
    """Admin for Doctor Profiles"""
    list_display = [
        'user_id', 'medical_license_number', 'status',
        'consultation_fee', 'years_of_experience', 'average_rating',
        'get_license_valid', 'created_at'
    ]
    list_filter = [
        'status', 'is_available_online', 'is_available_offline',
        'specialties', 'created_at'
    ]
    search_fields = [
        'user_id', 'medical_license_number', 'qualifications'
    ]
    readonly_fields = [
        'average_rating', 'total_reviews', 'total_consultations',
        'created_at', 'updated_at', 'tenant_id'
    ]
    filter_horizontal = ['specialties']
    inlines = [DoctorAvailabilityInline]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Tenant & User Information', {
            'fields': ('tenant_id', 'user_id'),
            'description': 'User ID from SuperAdmin (required for login)'
        }),
        ('License Information', {
            'fields': (
                'medical_license_number', 'license_issuing_authority',
                'license_issue_date', 'license_expiry_date'
            )
        }),
        ('Professional Information', {
            'fields': (
                'qualifications', 'specialties', 'years_of_experience'
            )
        }),
        ('Consultation Settings', {
            'fields': (
                'consultation_fee', 'follow_up_fee', 'consultation_duration',
                'is_available_online', 'is_available_offline'
            )
        }),
        ('Ratings & Statistics', {
            'fields': (
                'average_rating', 'total_reviews', 'total_consultations'
            ),
            'classes': ('collapse',),
            'description': 'Read-only statistics updated by the system'
        }),
        ('Additional Information', {
            'fields': ('signature', 'languages_spoken', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_license_valid(self, obj):
        """Display license validity status"""
        return obj.is_license_valid
    get_license_valid.boolean = True
    get_license_valid.short_description = 'License Valid'


class DoctorAvailabilityAdmin(TenantModelAdmin):
    """Admin for Doctor Availability"""
    list_display = [
        'doctor', 'day_of_week', 'start_time', 'end_time',
        'is_available', 'max_appointments', 'created_at'
    ]
    list_filter = ['day_of_week', 'is_available', 'doctor__status', 'created_at']
    search_fields = [
        'doctor__user_id', 'doctor__medical_license_number'
    ]
    readonly_fields = ['created_at', 'updated_at', 'tenant_id']
    ordering = ['doctor', 'day_of_week', 'start_time']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Tenant & Doctor', {
            'fields': ('tenant_id', 'doctor')
        }),
        ('Schedule', {
            'fields': (
                'day_of_week', 'start_time', 'end_time',
                'is_available', 'max_appointments'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# Register models with custom admin site
hms_admin_site.register(Specialty, SpecialtyAdmin)
hms_admin_site.register(DoctorProfile, DoctorProfileAdmin)
hms_admin_site.register(DoctorAvailability, DoctorAvailabilityAdmin)
