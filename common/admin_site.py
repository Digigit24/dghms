from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages


class HMSAdminSite(AdminSite):
    """
    Custom admin site that works with SuperAdmin authentication
    """
    site_title = _('DigiHMS Administration')
    site_header = _('DigiHMS Admin')
    index_title = _('Welcome to Hospital Management System')

    def has_permission(self, request):
        """
        Check if user has permission to access admin site
        Override to work with our custom TenantUser
        """
        # Check if user is authenticated via session
        if hasattr(request, 'session') and request.session.get('user_data'):
            return True

        # Check if user object exists and is staff
        if hasattr(request, 'user') and request.user.is_authenticated:
            return getattr(request.user, 'is_staff', False)

        return False

    def index(self, request, extra_context=None):
        """
        Custom admin index page with tenant information
        """
        extra_context = extra_context or {}

        # Add tenant information from session
        if hasattr(request, 'session'):
            user_data = request.session.get('user_data', {})
            extra_context['tenant_id'] = user_data.get('tenant_id')
            extra_context['tenant_slug'] = user_data.get('tenant_slug')
            extra_context['user_email'] = user_data.get('email')
            extra_context['user_type'] = user_data.get('user_type', 'staff')

        return super().index(request, extra_context)

    def login(self, request, extra_context=None):
        """
        Custom login - redirect to our custom login page
        """
        if request.method == 'GET':
            # If already authenticated, redirect to admin index
            if self.has_permission(request):
                return redirect(reverse('admin:index'))

        # Use custom login template
        return render(request, 'admin/login.html', {
            'title': _('DigiHMS Admin Login'),
            'site_title': self.site_title,
            'site_header': self.site_header,
        })


class TenantModelAdmin(admin.ModelAdmin):
    """
    Base ModelAdmin class that automatically handles tenant filtering
    """

    def get_queryset(self, request):
        """Filter queryset by tenant_id from session"""
        qs = super().get_queryset(request)

        # Get tenant_id from session
        if hasattr(request, 'session'):
            user_data = request.session.get('user_data', {})
            tenant_id = user_data.get('tenant_id')

            # If model has tenant_id field, filter by it
            if tenant_id and hasattr(qs.model, 'tenant_id'):
                qs = qs.filter(tenant_id=tenant_id)

        return qs

    def save_model(self, request, obj, form, change):
        """Automatically set tenant_id when creating objects"""
        if not change:  # Only for new objects
            # Get tenant_id from session
            if hasattr(request, 'session'):
                user_data = request.session.get('user_data', {})
                tenant_id = user_data.get('tenant_id')

                # If model has tenant_id field and it's not set, set it
                if tenant_id and hasattr(obj, 'tenant_id') and not obj.tenant_id:
                    obj.tenant_id = tenant_id

        super().save_model(request, obj, form, change)


# Create custom admin site instance
hms_admin_site = HMSAdminSite(name='hms_admin')
