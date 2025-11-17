from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from common.admin_site import hms_admin_site

User = get_user_model()


class DoctorProfileInline(admin.StackedInline):
    """Inline admin for Doctor Profile"""
    from apps.doctors.models import DoctorProfile
    model = DoctorProfile
    can_delete = False
    verbose_name_plural = 'Doctor Profile'
    fk_name = 'user'
    
    fieldsets = (
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
        ('Consultation Details', {
            'fields': (
                'consultation_fee', 'consultation_duration',
                'is_available_online', 'is_available_offline'
            )
        }),
        ('Status & Ratings', {
            'fields': (
                'status', 'average_rating', 'total_reviews', 'total_consultations'
            )
        }),
        ('Additional', {
            'fields': ('signature', 'languages_spoken')
        }),
    )
    
    readonly_fields = ['average_rating', 'total_reviews', 'total_consultations']
    
    def has_add_permission(self, request, obj=None):
        if obj and obj.groups.filter(name='Doctor').exists():
            return not hasattr(obj, 'doctor_profile')
        return False
    
    def has_change_permission(self, request, obj=None):
        if obj:
            return obj.groups.filter(name='Doctor').exists()
        return False


class PatientProfileInline(admin.StackedInline):
    """Inline admin for Patient Profile"""
    from apps.patients.models import PatientProfile
    model = PatientProfile
    can_delete = False
    verbose_name_plural = 'Patient Profile'
    fk_name = 'user'
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'patient_id', 'first_name', 'middle_name', 'last_name',
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
                'address_line1', 'address_line2', 'city',
                'state', 'country', 'pincode'
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
        ('Insurance', {
            'fields': (
                'insurance_provider', 'insurance_policy_number',
                'insurance_expiry_date'
            )
        }),
        ('Hospital Records', {
            'fields': (
                'registration_date', 'last_visit_date',
                'total_visits', 'status'
            )
        }),
    )
    
    readonly_fields = ['patient_id', 'age', 'bmi', 'registration_date']
    
    def has_add_permission(self, request, obj=None):
        if obj and obj.groups.filter(name='Patient').exists():
            return not hasattr(obj, 'patient_profile')
        return False
    
    def has_change_permission(self, request, obj=None):
        if obj:
            return obj.groups.filter(name='Patient').exists()
        return False


class UserAdmin(BaseUserAdmin):
    """Custom User Admin with Profile Inlines"""
    
    list_display = [
        'email', 'username', 'full_name_display', 'role',
        'profile_status', 'is_active', 'is_staff', 'created_at'
    ]
    list_filter = [
        'is_active', 'is_staff', 'is_superuser',
        'groups', 'created_at', 'is_verified'
    ]
    search_fields = [
        'email', 'username', 'first_name',
        'last_name', 'employee_id', 'phone'
    ]
    ordering = ['-created_at']
    
    def get_inline_instances(self, request, obj=None):
        """Show appropriate profile inline based on user's role"""
        inline_instances = []
        
        if obj:
            # Show doctor profile inline for doctors
            if obj.groups.filter(name='Doctor').exists():
                inline_instances.append(DoctorProfileInline(self.model, self.admin_site))
            
            # Show patient profile inline for patients
            elif obj.groups.filter(name='Patient').exists():
                inline_instances.append(PatientProfileInline(self.model, self.admin_site))
        
        return inline_instances
    
    fieldsets = (
        ('Authentication', {
            'fields': ('email', 'username', 'password')
        }),
        ('Personal Info', {
            'fields': (
                'first_name', 'last_name', 'date_of_birth',
                'gender', 'phone', 'alternate_phone',
                'profile_picture', 'bio'
            )
        }),
        ('Address', {
            'fields': (
                'address_line1', 'address_line2',
                'city', 'state', 'country', 'pincode'
            ),
            'classes': ('collapse',)
        }),
        ('Hospital Info', {
            'fields': (
                'employee_id', 'department', 'joining_date'
            ),
            'classes': ('collapse',)
        }),
        ('Permissions & Groups', {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'is_verified', 'groups', 'user_permissions'
            ),
            'description': 'Select appropriate group (role) for this user. Doctor/Patient groups will show profile section below.'
        }),
        ('Important Dates', {
            'fields': ('last_login', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    add_fieldsets = (
        ('User Account', {
            'classes': ('wide',),
            'fields': (
                'email', 'username', 'password1', 'password2',
                'first_name', 'last_name'
            ),
        }),
        ('Role & Status', {
            'classes': ('wide',),
            'fields': (
                'groups', 'is_staff', 'is_active'
            ),
            'description': 'After creating user, edit to add Doctor/Patient profile if needed.'
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at', 'last_login']
    
    def role(self, obj):
        """Display user's primary role with colored badge"""
        role_name = obj.role
        color_map = {
            'Administrator': '#e74c3c',
            'Doctor': '#3498db',
            'Nurse': '#9b59b6',
            'Receptionist': '#1abc9c',
            'Pharmacist': '#f39c12',
            'Lab Technician': '#34495e',
            'Patient': '#27ae60',
            'No Role': '#95a5a6'
        }
        color = color_map.get(role_name, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color, role_name
        )
    role.short_description = 'Role'
    
    def full_name_display(self, obj):
        """Display full name"""
        return obj.get_full_name() or '-'
    full_name_display.short_description = 'Full Name'
    
    def profile_status(self, obj):
        """Show profile completion status"""
        icons = []
        if hasattr(obj, 'doctor_profile'):
            icons.append('👨‍⚕️ Doctor Profile')
        if hasattr(obj, 'patient_profile'):
            icons.append('🏥 Patient Profile')
        
        if icons:
            return format_html('<br>'.join(icons))
        return format_html('<span style="color: #95a5a6;">No Profile</span>')
    profile_status.short_description = 'Profile'
    
    def save_model(self, request, obj, form, change):
        """Auto-create profile when group is assigned"""
        super().save_model(request, obj, form, change)
        
        # Check if Doctor group is assigned and no profile exists
        if obj.groups.filter(name='Doctor').exists() and not hasattr(obj, 'doctor_profile'):
            from apps.doctors.models import DoctorProfile
            DoctorProfile.objects.create(user=obj)
        
        # Check if Patient group is assigned and no profile exists
        if obj.groups.filter(name='Patient').exists() and not hasattr(obj, 'patient_profile'):
            from apps.patients.models import PatientProfile
            # Create basic patient profile with user's data
            PatientProfile.objects.create(
                user=obj,
                first_name=obj.first_name or 'Unknown',
                last_name=obj.last_name or 'Unknown',
                date_of_birth=obj.date_of_birth or '2000-01-01',
                gender=obj.gender or 'other',
                mobile_primary=obj.phone or '0000000000',
                address_line1=obj.address_line1 or 'Not provided',
                city=obj.city or 'Unknown',
                state=obj.state or 'Unknown',
                pincode=obj.pincode or '000000',
                emergency_contact_name='Not provided',
                emergency_contact_phone='0000000000',
                emergency_contact_relation='Unknown',
                created_by=request.user
            )

# Register User model with custom admin site
hms_admin_site.register(User, UserAdmin)
