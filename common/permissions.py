"""Permission helpers and DRF permission classes for DigiHMS.

All permission checks are based on the JWT payload attached to the request
by ``common.middleware.JWTAuthenticationMiddleware``. No Django permissions
are used.
"""

from functools import wraps

from django.contrib.auth.models import AnonymousUser
from rest_framework import permissions

from .responses import error_response
from . import error_codes


class HMSPermissions:
    """HMS-specific permission constants."""

    # Patient permissions
    PATIENTS_VIEW = "hms.patients.view"
    PATIENTS_CREATE = "hms.patients.create"
    PATIENTS_EDIT = "hms.patients.edit"
    PATIENTS_DELETE = "hms.patients.delete"

    # Doctor permissions
    DOCTORS_VIEW = "hms.doctors.view"
    DOCTORS_CREATE = "hms.doctors.create"
    DOCTORS_EDIT = "hms.doctors.edit"
    DOCTORS_DELETE = "hms.doctors.delete"

    # Appointment permissions
    APPOINTMENTS_VIEW = "hms.appointments.view"
    APPOINTMENTS_CREATE = "hms.appointments.create"
    APPOINTMENTS_EDIT = "hms.appointments.edit"
    APPOINTMENTS_DELETE = "hms.appointments.delete"

    # OPD permissions
    OPD_VIEW = "hms.opd.view"
    OPD_CREATE = "hms.opd.create"
    OPD_EDIT = "hms.opd.edit"

    # Pharmacy permissions
    PHARMACY_VIEW = "hms.pharmacy.view"
    PHARMACY_CREATE = "hms.pharmacy.create"
    PHARMACY_EDIT = "hms.pharmacy.edit"

    # Payment permissions
    PAYMENTS_VIEW = "hms.payments.view"
    PAYMENTS_CREATE = "hms.payments.create"

    # Order permissions
    ORDERS_VIEW = "hms.orders.view"
    ORDERS_CREATE = "hms.orders.create"

    # Clinical permissions
    CLINICAL_VIEW = "hms.clinical.view"
    CLINICAL_CREATE = "hms.clinical.create"
    CLINICAL_EDIT = "hms.clinical.edit"
    CLINICAL_DELETE = "hms.clinical.delete"

    # Webhook permissions
    WEBHOOKS_VIEW = "hms.webhooks.view"
    WEBHOOKS_CREATE = "hms.webhooks.create"
    WEBHOOKS_EDIT = "hms.webhooks.edit"
    WEBHOOKS_DELETE = "hms.webhooks.delete"


def check_permission(request, permission_key, resource_owner_id=None, resource_team_id=None):
    """Check if the request has ``permission_key``.

    Supports boolean and scope-based values (``"all"``, ``"team"``, ``"own"``).
    Super-admins bypass all permission checks — they have implicit access to everything.
    """
    # Super-admins have all permissions by default; skip explicit checks.
    if getattr(request, "is_super_admin", False):
        return True

    if not hasattr(request, "permissions"):
        return False

    permissions_dict = request.permissions
    permission_value = _resolve_permission(permissions_dict, permission_key)

    if permission_value is None:
        return False

    if isinstance(permission_value, bool):
        return permission_value

    if isinstance(permission_value, str):
        if permission_value == "all":
            return True
        if permission_value == "team":
            # Placeholder: future team scoping.
            return True
        if permission_value == "own":
            if resource_owner_id is None:
                return True
            return str(resource_owner_id) == str(request.user_id)

    return False


def _resolve_permission(permissions_dict, permission_key):
    """Resolve a permission value from flat or nested permission payloads."""
    if not isinstance(permissions_dict, dict):
        return None

    if permission_key in permissions_dict:
        return permissions_dict[permission_key]

    # Support legacy nested structure: hms -> patients -> view
    parts = permission_key.split(".")
    if len(parts) == 3:
        namespace, module, action = parts
        nested = permissions_dict.get(namespace, {})
        if isinstance(nested, dict):
            module_perms = nested.get(module, {})
            if isinstance(module_perms, dict):
                return module_perms.get(action)

    return None


def permission_required(permission_key):
    """Decorator for function-based views."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not check_permission(request, permission_key):
                return error_response(
                    code=error_codes.PERMISSION_DENIED,
                    message="Permission denied.",
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def get_queryset_for_permission(queryset, request, view_permission_key, owner_field="owner_user_id"):
    """Filter a queryset by tenant and permission scope.

    Super-admins receive the full tenant-scoped queryset without scope filtering.
    """
    if not hasattr(request, "tenant_id"):
        return queryset.none()

    # Super-admins bypass scope restrictions — return the full tenant queryset.
    if getattr(request, "is_super_admin", False):
        return queryset.filter(tenant_id=request.tenant_id)

    if not hasattr(request, "permissions"):
        return queryset.none()

    permission_value = _resolve_permission(request.permissions, view_permission_key)
    base_queryset = queryset.filter(tenant_id=request.tenant_id)

    if permission_value is None:
        return queryset.none()

    if isinstance(permission_value, bool):
        return base_queryset if permission_value else queryset.none()

    if isinstance(permission_value, str):
        if permission_value == "all":
            return base_queryset
        if permission_value == "team":
            return base_queryset
        if permission_value == "own":
            filter_kwargs = {owner_field: request.user_id}
            return base_queryset.filter(**filter_kwargs)

    return queryset.none()


# ---------------------------------------------------------------------------
# DRF permission classes
# ---------------------------------------------------------------------------


class IsTenantAuthenticated(permissions.BasePermission):
    """Allow access only when the request carries a valid JWT tenant."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or isinstance(user, AnonymousUser):
            return False
        return (
            hasattr(request, "tenant_id")
            and request.tenant_id is not None
            and hasattr(request, "user_id")
            and request.user_id is not None
        )


class IsSuperAdmin(permissions.BasePermission):
    """Allow access only to super-admin users."""

    def has_permission(self, request, view):
        return bool(getattr(request, "is_super_admin", False))


class IsRole(permissions.BasePermission):
    """Allow access only if the user has one of the configured roles.

    Usage::

        class MyView(APIView):
            permission_classes = [IsTenantAuthenticated, IsRole]
            required_roles = ["doctor", "nurse"]
    """

    required_roles = []

    def has_permission(self, request, view):
        required = getattr(view, "required_roles", self.required_roles)
        if not required:
            return True
        user_roles = getattr(request, "roles", []) or []
        return any(role in user_roles for role in required)


class HasCeliyoPermission(permissions.BasePermission):
    """DRF permission class that checks a specific HMS permission key.

    Usage::

        class MyView(APIView):
            permission_classes = [IsTenantAuthenticated, HasCeliyoPermission]
            required_permission = HMSPermissions.CLINICAL_VIEW
    """

    required_permission = None

    def has_permission(self, request, view):
        perm = getattr(view, "required_permission", self.required_permission)
        if perm is None:
            return False
        return check_permission(request, perm)


# ---------------------------------------------------------------------------
# Legacy mixin (kept for backward compatibility)
# ---------------------------------------------------------------------------


class PermissionRequiredMixin:
    """Mixin for ViewSets to add permission checking via ``permission_map``."""

    permission_map = {
        "list": None,
        "retrieve": None,
        "create": None,
        "update": None,
        "partial_update": None,
        "destroy": None,
    }

    def check_permissions(self, request):
        super().check_permissions(request)
        permission_key = self.permission_map.get(self.action)
        if permission_key and not check_permission(request, permission_key):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You don't have permission to perform this action")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if self.action in ["update", "partial_update", "destroy"]:
            permission_key = self.permission_map.get(self.action)
            if permission_key:
                owner_id = getattr(obj, "owner_user_id", None)
                if not check_permission(request, permission_key, owner_id):
                    from rest_framework.exceptions import PermissionDenied

                    raise PermissionDenied("You don't have permission to modify this resource")


def has_module_access(request, module_name):
    """Check if the user's JWT lists ``module_name`` in enabled_modules."""
    if not hasattr(request, "enabled_modules"):
        return False
    return module_name in request.enabled_modules
