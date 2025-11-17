from django.contrib import admin
from django.utils.html import format_html
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import Hospital


class HospitalAdmin(TenantModelAdmin):
    """Hospital configuration admin"""

    list_display = [
        'name', 'type', 'city', 'phone', 'email',
        'has_emergency', 'has_pharmacy', 'has_laboratory'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'type', 'tagline', 'logo')
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'alternate_phone', 'website')
        }),
        ('Address', {
            'fields': ('address', 'city', 'state', 'country', 'pincode')
        }),
        ('Services & Settings', {
            'fields': (
                'working_hours', 'has_emergency',
                'has_pharmacy', 'has_laboratory'
            )
        }),
        ('Additional Details', {
            'fields': ('registration_number', 'established_date')
        }),
        ('Timestamps', {
            'fields': ('tenant_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['tenant_id', 'created_at', 'updated_at']
    
    def has_add_permission(self, request):
        """Prevent adding more than one hospital"""
        if Hospital.objects.exists():
            return False
        return super().has_add_permission(request)
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of hospital configuration"""
        return False
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Customize change form"""
        extra_context = extra_context or {}
        extra_context['show_save_and_add_another'] = False
        extra_context['show_save_and_continue'] = False
        return super().changeform_view(
            request, object_id, form_url, extra_context=extra_context
        )


# Register models with custom admin site
hms_admin_site.register(Hospital, HospitalAdmin)

