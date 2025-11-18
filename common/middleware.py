import jwt
import json
import logging
import threading
from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

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

        # TEMP: Force print to console to verify middleware is running
        print(f"[JWT MIDDLEWARE] Processing: {request.method} {request.path}")

        # Store request in thread-local storage for authentication backends
        set_current_request(request)

        # Skip validation for public paths
        if any(request.path.startswith(path) for path in self.PUBLIC_PATHS):
            print(f"[JWT MIDDLEWARE] Skipping public path: {request.path}")
            return None

        # Debug: Log all incoming request details
        print(f"[JWT MIDDLEWARE] Starting authentication for {request.path}")
        logger.debug("="*80)
        logger.debug(f"Incoming Request: {request.method} {request.path}")
        logger.debug(f"Request Headers:")
        for key, value in request.META.items():
            if key.startswith('HTTP_'):
                # Truncate token for security
                display_value = value[:50] + '...' if key == 'HTTP_AUTHORIZATION' and len(value) > 50 else value
                logger.debug(f"  {key}: {display_value}")

        # Get Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header:
            print(f"[JWT MIDDLEWARE] ❌ NO AUTHORIZATION HEADER - Path: {request.path}")
            logger.warning(f"Missing Authorization header - Path: {request.path}, Method: {request.method}")
            return JsonResponse(
                {'error': 'Authorization header required'},
                status=401
            )

        # Extract token from "Bearer <token>" format
        logger.debug(f"Authorization header present: {auth_header[:50]}...")
        try:
            scheme, token = auth_header.split(' ', 1)
            logger.debug(f"Auth scheme: {scheme}")
            logger.debug(f"Token length: {len(token)} characters")

            if scheme.lower() != 'bearer':
                logger.warning(f"Invalid auth scheme '{scheme}' - Path: {request.path}")
                return JsonResponse(
                    {'error': 'Invalid authorization scheme. Use Bearer token'},
                    status=401
                )
        except ValueError:
            logger.warning(f"Malformed Authorization header - Path: {request.path}")
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

            logger.debug(f"JWT Configuration:")
            logger.debug(f"  Algorithm: {algorithm}")
            logger.debug(f"  Leeway: {leeway}s")
            logger.debug(f"  Secret key configured: {'Yes' if secret_key else 'No'}")
            logger.debug(f"  Secret key length: {len(secret_key) if secret_key else 0} chars")

            if not secret_key:
                return JsonResponse(
                    {'error': 'JWT_SECRET_KEY not configured'},
                    status=500
                )

            # Decode JWT token
            logger.debug("Attempting to decode JWT token...")
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=[algorithm],
                leeway=leeway  # Tolerate clock skew between servers
            )
            logger.debug(f"JWT decoded successfully!")
            logger.debug(f"JWT Payload keys: {list(payload.keys())}")
            logger.debug(f"JWT Payload: {json.dumps(payload, indent=2)}")

        except jwt.ExpiredSignatureError as e:
            logger.warning(f"Expired JWT token - Path: {request.path}")
            logger.debug(f"Token expiry details: {str(e)}")
            return JsonResponse(
                {'error': 'Token has expired'},
                status=401
            )
        except jwt.InvalidTokenError as e:
            print(f"[JWT MIDDLEWARE] ❌ INVALID TOKEN: {str(e)}")
            print(f"[JWT MIDDLEWARE] Algorithm used: {algorithm}")
            print(f"[JWT MIDDLEWARE] Token preview: {token[:100]}...")
            logger.error(f"Invalid JWT token: {str(e)} - Path: {request.path}, Algorithm: {algorithm}")
            logger.debug(f"Full token error: {repr(e)}")
            logger.debug(f"Token (first 100 chars): {token[:100]}...")
            return JsonResponse(
                {'error': f'Invalid token: {str(e)}'},
                status=401
            )

        # Validate required fields in payload
        required_fields = [
            'user_id', 'email', 'tenant_id', 'tenant_slug',
            'is_super_admin', 'permissions', 'enabled_modules'
        ]

        logger.debug(f"Validating required fields: {required_fields}")
        for field in required_fields:
            if field not in payload:
                print(f"[JWT MIDDLEWARE] ❌ MISSING FIELD: '{field}'")
                print(f"[JWT MIDDLEWARE] Available fields: {list(payload.keys())}")
                print(f"[JWT MIDDLEWARE] Full payload: {json.dumps(payload, indent=2)}")
                logger.error(
                    f"Missing JWT field '{field}' - Path: {request.path}, "
                    f"Available fields: {list(payload.keys())}"
                )
                logger.debug(f"Full payload: {json.dumps(payload, indent=2)}")
                return JsonResponse(
                    {'error': f'Missing required field in token: {field}'},
                    status=401
                )
            else:
                logger.debug(f"  ✓ {field}: {payload[field]}")

        # Check if HMS module is enabled
        enabled_modules = payload.get('enabled_modules', [])
        if 'hms' not in enabled_modules:
            print(f"[JWT MIDDLEWARE] ❌ HMS MODULE NOT ENABLED")
            print(f"[JWT MIDDLEWARE] User: {payload.get('email')}")
            print(f"[JWT MIDDLEWARE] Enabled modules: {enabled_modules}")
            logger.warning(
                f"HMS module not enabled - Path: {request.path}, "
                f"User: {payload.get('email')}, Enabled modules: {enabled_modules}"
            )
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

        # CRITICAL: Create TenantUser and set request.user for DRF authentication
        from .auth_backends import TenantUser
        request.user = TenantUser(payload)
        request._cached_user = request.user  # Cache to prevent re-authentication

        print(f"[JWT MIDDLEWARE] ✅ AUTH SUCCESS - User: {request.email}, Tenant: {request.tenant_id}")
        logger.info(
            f"JWT auth successful - Path: {request.path}, User: {request.email}, "
            f"Tenant: {request.tenant_id}, Modules: {request.enabled_modules}"
        )
        logger.debug("="*80)

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
