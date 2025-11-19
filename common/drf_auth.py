"""
Django REST Framework authentication and permission classes for JWT-based HMS authentication.

This module provides DRF-compatible authentication and permission classes that work with
the JWT middleware to provide consistent authentication across all API endpoints.
"""

from rest_framework import authentication, permissions
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from django.contrib.auth.models import AnonymousUser
import logging

logger = logging.getLogger(__name__)


class JWTAuthentication(authentication.BaseAuthentication):
    """
    DRF authentication class that uses the TenantUser set by JWTAuthenticationMiddleware.

    This class works in conjunction with the JWTAuthenticationMiddleware which validates
    the JWT token and sets request.user. This DRF authentication class simply returns
    that user, making it compatible with DRF's permission system.
    """

    def authenticate(self, request):
        """
        Returns a `User` object if the request contains a valid JWT token.

        The actual JWT validation is done by JWTAuthenticationMiddleware.
        This method just returns the user that was set by the middleware.
        """
        # Access the underlying Django request (not DRF's wrapped request)
        # to avoid recursion when accessing request.user
        django_request = request._request if hasattr(request, '_request') else request

        # Check if user was set by JWT middleware on the Django request
        if hasattr(django_request, 'user') and django_request.user is not None:
            # Check if it's not an anonymous user
            if not isinstance(django_request.user, AnonymousUser):
                # Return (user, auth) tuple required by DRF
                return (django_request.user, None)

        # No authenticated user found
        return None

    def authenticate_header(self, request):
        """
        Return a string to be used as the value of the `WWW-Authenticate`
        header in a `401 Unauthenticated` response.
        """
        return 'Bearer realm="api"'


class HMSPermission(permissions.BasePermission):
    """
    Base permission class that checks HMS permissions from JWT payload.

    This class checks permissions from the nested JSON structure in the JWT token:
    {
        "permissions": {
            "hms": {
                "patients": {
                    "view": "all",
                    "create": true,
                    "edit": "own",
                    ...
                },
                ...
            }
        }
    }

    Usage in views:
    - Define `hms_module` (e.g., 'patients', 'doctors', 'appointments')
    - Optionally override `get_hms_permission_module()` for dynamic module names
    - Permissions are automatically mapped from DRF actions to HMS permissions
    """

    # Default action to permission mapping
    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'create',
        'update': 'edit',
        'partial_update': 'edit',
        'destroy': 'delete',
    }

    def has_permission(self, request, view):
        """
        Check if the user has permission to perform the requested action.
        """
        # Check if user is authenticated
        if not request.user or isinstance(request.user, AnonymousUser):
            return False

        # Super admins have all permissions
        if hasattr(request.user, 'is_super_admin') and request.user.is_super_admin:
            return True

        # Get the HMS module from the view
        hms_module = self.get_hms_permission_module(view)
        if not hms_module:
            logger.warning(f"No HMS module defined for view {view.__class__.__name__}")
            return False

        # Get the action (e.g., 'list', 'create', 'update')
        action = getattr(view, 'action', None)
        if not action:
            # For non-ViewSet views, try to determine action from method
            method = request.method.lower()
            action_map = {
                'get': 'list',
                'post': 'create',
                'put': 'update',
                'patch': 'partial_update',
                'delete': 'destroy',
            }
            action = action_map.get(method)

        if not action:
            logger.warning(f"Could not determine action for view {view.__class__.__name__}")
            return False

        # Get the permission name from action
        permission_name = self.get_permission_name(action, view)
        if not permission_name:
            logger.warning(f"No permission mapping for action '{action}'")
            return False

        # Check the permission
        return self.check_hms_permission(request, hms_module, permission_name)

    def has_object_permission(self, request, view, obj):
        """
        Check if the user has permission to perform the requested action on a specific object.

        This handles scope-based permissions like 'own' and 'team'.
        """
        # Check if user is authenticated
        if not request.user or isinstance(request.user, AnonymousUser):
            return False

        # Super admins have all permissions
        if hasattr(request.user, 'is_super_admin') and request.user.is_super_admin:
            return True

        # Get the HMS module and permission
        hms_module = self.get_hms_permission_module(view)
        action = getattr(view, 'action', None)
        permission_name = self.get_permission_name(action, view)

        if not hms_module or not permission_name:
            return False

        # Get permission value
        permission_value = self.get_permission_value(request, hms_module, permission_name)

        # Handle scope-based permissions
        if isinstance(permission_value, str):
            if permission_value == "all":
                return True
            elif permission_value == "team":
                # TODO: Implement team-based filtering
                return True
            elif permission_value == "own":
                # Check if object belongs to the user
                return self.check_ownership(request, obj)

        # Boolean permission
        return bool(permission_value)

    def get_hms_permission_module(self, view):
        """
        Get the HMS module name for the view.
        Override this in subclasses or set `hms_module` attribute on the view.
        """
        return getattr(view, 'hms_module', None)

    def get_permission_name(self, action, view):
        """
        Map DRF action to HMS permission name.
        Can be overridden in view with `action_permission_map`.
        """
        # Check if view has custom mapping
        if hasattr(view, 'action_permission_map'):
            return view.action_permission_map.get(action)

        # Use default mapping
        return self.action_permission_map.get(action)

    def check_hms_permission(self, request, module, permission_name):
        """
        Check if user has a specific HMS permission.

        Args:
            request: Django request with authenticated user
            module: HMS module name (e.g., 'patients', 'doctors')
            permission_name: Permission name (e.g., 'view', 'create', 'edit')

        Returns:
            bool: True if permission granted
        """
        permission_value = self.get_permission_value(request, module, permission_name)

        # Handle boolean permissions
        if isinstance(permission_value, bool):
            return permission_value

        # Handle scope-based permissions (all, team, own)
        if isinstance(permission_value, str):
            if permission_value in ["all", "team", "own"]:
                return True

        return False

    def get_permission_value(self, request, module, permission_name):
        """
        Get the permission value from the user's JWT permissions.

        Returns the permission value or None if not found.
        """
        if not hasattr(request.user, 'permissions'):
            return None

        # Navigate through nested permissions structure
        # permissions -> hms -> module -> permission_name
        user_permissions = request.user.permissions
        hms_perms = user_permissions.get('hms', {})
        module_perms = hms_perms.get(module, {})

        return module_perms.get(permission_name)

    def check_ownership(self, request, obj):
        """
        Check if the object belongs to the current user.

        Override this in subclasses to customize ownership logic.
        Default: checks if obj has 'user_id' or 'owner_user_id' field matching request.user.
        """
        user_id = getattr(request.user, '_original_id', None) or getattr(request.user, 'id', None)

        # Try common ownership field names
        for field_name in ['user_id', 'owner_user_id', 'created_by_id', 'patient_id', 'doctor_id']:
            if hasattr(obj, field_name):
                obj_user_id = getattr(obj, field_name)
                return str(obj_user_id) == str(user_id)

        # Default: allow access (can be restricted by setting on view)
        logger.warning(f"Could not determine ownership for {obj.__class__.__name__}")
        return True


class IsAuthenticated(permissions.BasePermission):
    """
    Simple permission class that only checks if user is authenticated via JWT.
    Use this when you don't need HMS module-specific permission checking.
    """

    def has_permission(self, request, view):
        """Check if user is authenticated."""
        if not request.user or isinstance(request.user, AnonymousUser):
            return False

        if not hasattr(request.user, 'is_authenticated'):
            return False

        return request.user.is_authenticated

    def authenticate_header(self, request):
        """Return authentication header for 401 responses."""
        return 'Bearer realm="api"'


class AllowAny(permissions.BasePermission):
    """
    Permission class that allows unrestricted access.
    Use sparingly and only for truly public endpoints.
    """

    def has_permission(self, request, view):
        """Allow any access."""
        return True
