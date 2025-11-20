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
    login_template = 'admin/login.html'

    def has_permission(self, request):
        """
        Check if user has permission to access admin site
        Override to work with our custom TenantUser
        """
        # # Check if user is authenticated via session
        # if hasattr(request, 'session') and request.session.get('user_data'):
        #     return True

        # # Check if user object exists and is staff
        # if hasattr(request, 'user') and request.user.is_authenticated:
        #     return getattr(request.user, 'is_staff', False)

        return True

    def each_context(self, request):
        """
        Add custom context to all admin pages
        Includes tenant_id and user_id from session
        """
        context = super().each_context(request)

        # Add tenant and user information from session
        if hasattr(request, 'session'):
            user_data = request.session.get('user_data', {})
            context['admin_tenant_id'] = user_data.get('tenant_id', 'Not Available')
            context['admin_tenant_slug'] = user_data.get('tenant_slug', 'Not Available')
            context['admin_user_id'] = user_data.get('user_id', 'Not Available')
            context['admin_user_email'] = user_data.get('email', 'Not Available')
            context['admin_user_type'] = user_data.get('user_type', 'staff')

        return context

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

        try:
            return super().index(request, extra_context)
        except Exception as e:
            # If there's an error loading the admin index (likely due to UUID/integer field mismatch),
            # provide a simplified index page
            from django.template.response import TemplateResponse
            context = {
                'title': self.index_title,
                'site_title': self.site_title,
                'site_header': self.site_header,
                'site_url': self.site_url,
                'has_permission': self.has_permission(request),
                'available_apps': [],  # Empty for now to avoid the error
                'is_popup': False,
                'error_message': f'Admin index loading error: {str(e)}',
                **extra_context
            }
            return TemplateResponse(request, 'admin/index.html', context)

    def login(self, request, extra_context=None):
        """
        Custom login - redirect to our custom login page
        """
        from django.conf import settings

        if request.method == 'GET':
            # If already authenticated, redirect to admin index
            if self.has_permission(request):
                return redirect(reverse('admin:index'))

        # Use custom login template
        context = {
            'title': _('DigiHMS Admin Login'),
            'site_title': self.site_title,
            'site_header': self.site_header,
            'superadmin_url': getattr(settings, 'SUPERADMIN_URL', 'https://admin.celiyo.com'),
        }
        if extra_context:
            context.update(extra_context)

        return render(request, 'admin/login.html', context)


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
                # Convert string UUID to UUID object if needed
                import uuid
                if isinstance(tenant_id, str):
                    try:
                        tenant_id = uuid.UUID(tenant_id)
                    except ValueError:
                        # If conversion fails, skip filtering
                        pass
                qs = qs.filter(tenant_id=tenant_id)

        return qs

    def save_model(self, request, obj, form, change):
        """Automatically set tenant_id when creating objects"""
        if not change:  # Only for new objects
            tenant_id = None
            import logging
            import uuid
            logger = logging.getLogger(__name__)

            # Try to get tenant_id from session first
            if hasattr(request, 'session'):
                user_data = request.session.get('user_data', {})
                tenant_id = user_data.get('tenant_id')
                if tenant_id:
                    logger.info(f"[TenantModelAdmin] Got tenant_id from session: {tenant_id}")

            # Fallback: try to get tenant_id from authenticated user (JWT)
            if not tenant_id and hasattr(request, 'user') and request.user:
                if hasattr(request.user, 'tenant_id'):
                    tenant_id = request.user.tenant_id
                    logger.info(f"[TenantModelAdmin] Got tenant_id from user: {tenant_id}")

            # If model has tenant_id field and it's not already set
            if hasattr(obj, 'tenant_id'):
                # If tenant_id is already set in form, use it (manual entry)
                if obj.tenant_id:
                    logger.info(f"[TenantModelAdmin] tenant_id already set in form: {obj.tenant_id}")
                # Otherwise try to set it from session/user
                elif tenant_id:
                    # Convert string UUID to UUID object if needed
                    if isinstance(tenant_id, str):
                        try:
                            tenant_id = uuid.UUID(tenant_id)
                        except ValueError:
                            logger.error(f"[TenantModelAdmin] Failed to convert tenant_id to UUID: {tenant_id}")
                            tenant_id = None
                    if tenant_id:
                        obj.tenant_id = tenant_id
                        logger.info(f"[TenantModelAdmin] Set tenant_id on object: {tenant_id}")
                else:
                    logger.warning(f"[TenantModelAdmin] No tenant_id available! User: {request.user}, Session: {hasattr(request, 'session')}")

        super().save_model(request, obj, form, change)

    # Override permission methods to bypass Django's permission system
    def has_module_permission(self, request):
        """Allow access to the module"""
        return True

    def has_view_permission(self, request, obj=None):
        """Allow viewing objects"""
        return True

    def has_add_permission(self, request):
        """Allow adding new objects"""
        return True

    def has_change_permission(self, request, obj=None):
        """Allow changing objects"""
        return True

    def has_delete_permission(self, request, obj=None):
        """Allow deleting objects"""
        return True


# Create custom admin site instance
hms_admin_site = HMSAdminSite(name='hms_admin')
