# apps/nakshatra_api/admin.py

from django.contrib import admin
from .models import NakshatraLead


@admin.register(NakshatraLead)
class NakshatraLeadAdmin(admin.ModelAdmin):
    """
    Admin interface for Nakshatra Leads.

    Provides viewing and management of leads submitted through the Nakshatra API.
    """

    list_display = [
        'id',
        'full_name',
        'email',
        'phone',
        'services',
        'appointment_date',
        'custom_api_status',
        'meta_capi_status',
        'is_successfully_processed',
        'created_at',
    ]

    list_filter = [
        'custom_api_status',
        'meta_capi_status',
        'services',
        'created_at',
    ]

    search_fields = [
        'first_name',
        'last_name',
        'email',
        'phone',
        'services',
        'client_event_id',
    ]

    readonly_fields = [
        'id',
        'first_name',
        'last_name',
        'email',
        'phone',
        'services',
        'appointment_date',
        'client_event_id',
        'ip_address',
        'user_agent',
        'custom_api_status',
        'custom_api_response',
        'meta_capi_status',
        'meta_capi_response',
        'created_at',
        'updated_at',
        'full_name',
        'is_successfully_processed',
    ]

    fieldsets = (
        ('Lead Information', {
            'fields': (
                'id',
                'first_name',
                'last_name',
                'full_name',
                'email',
                'phone',
                'services',
                'appointment_date',
            )
        }),
        ('Tracking Information', {
            'fields': (
                'client_event_id',
                'ip_address',
                'user_agent',
            )
        }),
        ('Custom API Integration', {
            'fields': (
                'custom_api_status',
                'custom_api_response',
            )
        }),
        ('Meta CAPI Integration', {
            'fields': (
                'meta_capi_status',
                'meta_capi_response',
            )
        }),
        ('System Information', {
            'fields': (
                'is_successfully_processed',
                'created_at',
                'updated_at',
            )
        }),
    )

    ordering = ['-created_at']

    def has_add_permission(self, request):
        """Disable manual creation - leads are only created via API"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Allow deletion of leads"""
        return True

    def has_change_permission(self, request, obj=None):
        """Disable editing - leads are read-only"""
        return False
