import jwt
import json
import threading
from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

# Thread-local storage for tenant_id and request (for future database routing)
_thread_locals = threading.local()


def get_current_tenant_id():
    """Get the current tenant_id from thread-local storage"""
    return getattr(_thread_locals, 'tenant_id', None)


def set_current_tenant_id(tenant_id):
    """Set the current tenant_id in thread-local storage"""
    _thread_locals.tenant_id = tenant_id


def get_current_request():
    """Get the current request from thread-local storage"""
    return getattr(_thread_locals, 'request', None)


def set_current_request(request):
    """Set the current request in thread-local storage"""
    _thread_locals.request = request


class JWTAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware to validate JWT tokens from SuperAdmin and set request attributes
    """

    # Public paths that don't require authentication
    PUBLIC_PATHS = [
        '/',  # Root URL (redirects to admin)
        '/api/docs/',
        '/api/schema/',
        '/admin',   # Allow all admin paths - custom admin site handles auth
        '/auth/',   # Allow all auth endpoints
        '/static/',  # Allow static files (CSS, JS, images)
        '/media/',   # Allow media files
        '/health/',
        '/api/schema.json',
        '/api/schema.yaml',
    ]

    def process_request(self, request):
        """Process incoming request and validate JWT token"""

        # Store request in thread-local storage for authentication backends
        set_current_request(request)

        # Skip validation for public paths
        if any(request.path.startswith(path) for path in self.PUBLIC_PATHS):
            return None

        # Get Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header:
            return JsonResponse(
                {'error': 'Authorization header required'},
                status=401
            )

        # Extract token from "Bearer <token>" format
        try:
            scheme, token = auth_header.split(' ', 1)
            if scheme.lower() != 'bearer':
                return JsonResponse(
                    {'error': 'Invalid authorization scheme. Use Bearer token'},
                    status=401
                )
        except ValueError:
            return JsonResponse(
                {'error': 'Invalid authorization header format'},
                status=401
            )

        # Decode and validate JWT token
        try:
            # Get JWT settings from Django settings
            secret_key = getattr(settings, 'JWT_SECRET_KEY', None)
            algorithm = getattr(settings, 'JWT_ALGORITHM', 'HS256')
            leeway = getattr(settings, 'JWT_LEEWAY', 30)

            if not secret_key:
                return JsonResponse(
                    {'error': 'JWT_SECRET_KEY not configured'},
                    status=500
                )

            # Decode JWT token
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[algorithm],
                leeway=leeway  # Tolerate clock skew between servers
            )

        except jwt.ExpiredSignatureError:
            return JsonResponse(
                {'error': 'Token has expired'},
                status=401
            )
        except jwt.InvalidTokenError as e:
            return JsonResponse(
                {'error': f'Invalid token: {str(e)}'},
                status=401
            )

        # Validate required fields in payload
        required_fields = [
            'user_id', 'email', 'tenant_id', 'tenant_slug',
            'is_super_admin', 'permissions', 'enabled_modules'
        ]

        for field in required_fields:
            if field not in payload:
                return JsonResponse(
                    {'error': f'Missing required field in token: {field}'},
                    status=401
                )

        # Check if HMS module is enabled
        enabled_modules = payload.get('enabled_modules', [])
        if 'hms' not in enabled_modules:
            return JsonResponse(
                {'error': 'HMS module not enabled for this user'},
                status=403
            )

        # Set request attributes from JWT payload
        request.user_id = payload['user_id']
        request.email = payload['email']
        request.tenant_id = payload['tenant_id']
        request.tenant_slug = payload['tenant_slug']
        request.is_super_admin = payload['is_super_admin']
        request.permissions = payload['permissions']
        request.enabled_modules = payload['enabled_modules']

        # Set user type and patient flag
        request.user_type = payload.get('user_type', 'staff')
        request.is_patient = payload.get('is_patient', False)

        # Check for additional tenant headers as fallback/override
        tenant_token_header = request.META.get('HTTP_TENANTTOKEN')
        x_tenant_id_header = request.META.get('HTTP_X_TENANT_ID')
        x_tenant_slug_header = request.META.get('HTTP_X_TENANT_SLUG')

        # If tenanttoken header is provided, use it to override tenant_id
        if tenant_token_header:
            request.tenant_id = tenant_token_header

        # If x-tenant-id header is provided, use it to override tenant_id
        if x_tenant_id_header:
            request.tenant_id = x_tenant_id_header

        # If x-tenant-slug header is provided, use it to override tenant_slug
        if x_tenant_slug_header:
            request.tenant_slug = x_tenant_slug_header

        # Store tenant_id in thread-local storage for database routing
        set_current_tenant_id(request.tenant_id)

        return None


class CustomAuthenticationMiddleware(MiddlewareMixin):
    """
    Custom authentication middleware that replaces Django's AuthenticationMiddleware
    Uses session-based TenantUser instead of Django's User model
    """
    
    def process_request(self, request):
        """Set request.user based on session data instead of Django's auth system"""
        from .auth_backends import TenantUser
        from django.contrib.auth.models import AnonymousUser
        from django.contrib.auth import SESSION_KEY
        
        # Clear any Django auth session keys that might cause conflicts
        if hasattr(request, 'session'):
            # Remove Django's auth session keys to prevent conflicts
            if SESSION_KEY in request.session:
                del request.session[SESSION_KEY]
            if '_auth_user_backend' in request.session:
                del request.session['_auth_user_backend']
            if '_auth_user_hash' in request.session:
                del request.session['_auth_user_hash']
        
        # Check if we have user data in session
        if hasattr(request, 'session') and request.session.get('user_data'):
            user_data = request.session.get('user_data')
            request.user = TenantUser(user_data)
            # Set _cached_user to prevent Django from trying to load user from database
            request._cached_user = request.user
        else:
            # Create anonymous user
            request.user = AnonymousUser()
            request._cached_user = request.user
        
        return None
