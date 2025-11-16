from django.contrib import admin
from django.utils.html import format_html
from common.admin_site import TenantModelAdmin
from .models import Appointment, AppointmentType

@admin.register(AppointmentType)
class AppointmentTypeAdmin(TenantModelAdmin):
    """Admin configuration for Appointment Types"""
    list_display = [
        'name',
        'description',
        'duration_default',
        'base_consultation_fee'
    ]

    search_fields = ['name', 'description']
    list_filter = ['duration_default']
    readonly_fields = ['tenant_id']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'duration_default', 'base_consultation_fee')
        }),
        ('Tenant Information', {
            'fields': ('tenant_id',),
            'classes': ('collapse',)
        }),
    )

class FollowUpAppointmentInline(admin.TabularInline):
    """Inline admin for Follow-up Appointments"""
    model = Appointment
    fk_name = 'original_appointment'
    extra = 0
    readonly_fields = ['appointment_id', 'created_at', 'updated_at']
    
    def has_add_permission(self, request, obj=None):
        """Restrict adding follow-ups directly"""
        return request.user.is_superuser
    
    # Add this method to prevent cursor issues
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('patient', 'doctor', 'appointment_type')

@admin.register(Appointment)
class AppointmentAdmin(TenantModelAdmin):
    """Comprehensive Appointment Management in Admin"""
    list_display = [
        'appointment_id',
        'patient_display',
        'doctor_display',
        'appointment_date',
        'appointment_time',
        'status_badge',
        'priority',
        'consultation_fee'
    ]

    list_filter = [
        'status',
        'priority',
        'appointment_date',
        'is_follow_up',
        'doctor',  # Changed from doctor__user__username
    ]

    search_fields = [
        'appointment_id',
        'patient__first_name',
        'patient__last_name',
        'doctor__user__first_name',
        'doctor__user__last_name',
        'chief_complaint'
    ]

    inlines = [FollowUpAppointmentInline]

    readonly_fields = [
        'appointment_id',
        'checked_in_at',
        'actual_start_time',
        'actual_end_time',
        'waiting_time_minutes',
        'created_at',
        'updated_at',
        'cancelled_at',
        'approved_at',
        'tenant_id',
    ]

    # Add autocomplete for foreign keys to prevent loading all records
    autocomplete_fields = ['patient', 'doctor', 'original_appointment']

    fieldsets = (
        ('Appointment Details', {
            'fields': (
                'appointment_id',
                'patient',
                'doctor',
                'appointment_type',
                'appointment_date',
                'appointment_time',
                'end_time',
                'duration_minutes'
            )
        }),
        ('Medical Information', {
            'fields': (
                'chief_complaint',
                'symptoms',
                'notes'
            )
        }),
        ('Status & Priority', {
            'fields': (
                'status',
                'priority',
                'is_follow_up',
                'original_appointment'
            )
        }),
        ('Financial Details', {
            'fields': (
                'consultation_fee',
            )
        }),
        ('Timestamps', {
            'fields': (
                'checked_in_at',
                'actual_start_time',
                'actual_end_time',
                'waiting_time_minutes',
                'cancelled_at',
                'approved_at',
                'created_at',
                'updated_at',
                'created_by_user_id',
                'cancelled_by_id',
                'approved_by_id',
                'tenant_id',
            ),
            'classes': ('collapse',)
        }),
    )
    
    def patient_display(self, obj):
        """Display patient information"""
        if not obj.patient:
            return "No Patient"
        return f"{obj.patient.first_name} {obj.patient.last_name} ({obj.patient.mobile_primary})"
    patient_display.short_description = "Patient"
    
    def doctor_display(self, obj):
        """Display doctor information"""
        if not obj.doctor or not obj.doctor.user:
            return "No Doctor"
        return f"Dr. {obj.doctor.user.get_full_name()}"
    doctor_display.short_description = "Doctor"
    
    def status_badge(self, obj):
        """Colorful status representation"""
        color_map = {
            'scheduled': 'orange',
            'confirmed': 'blue',
            'checked_in': 'purple',
            'in_progress': 'yellow',
            'completed': 'green',
            'cancelled': 'red',
            'no_show': 'gray',
            'rescheduled': 'pink'
        }
        color = color_map.get(obj.status, 'gray')
        return format_html(
            '<span style="color:{}; font-weight:bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Status"
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        # Use select_related for foreign keys to reduce queries
        return qs.select_related(
            'patient',
            'doctor__user',  # Include user relation
            'appointment_type'
        )
    
    # IMPORTANT: Override formfield_for_foreignkey to prevent cursor issues
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "patient":
            # Limit queryset to prevent loading too many records
            kwargs["queryset"] = db_field.related_model.objects.select_related('user').all()
        elif db_field.name == "doctor":
            kwargs["queryset"] = db_field.related_model.objects.select_related('user').all()
        elif db_field.name == "original_appointment":
            kwargs["queryset"] = Appointment.objects.select_related('patient', 'doctor').all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)