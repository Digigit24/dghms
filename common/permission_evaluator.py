"""Single permission evaluator for DigiHMS.

Flat catalog keys are primary.  Nested payloads and legacy admin keys below are
temporary migration readers and may be removed after the permissions migration.
"""
import logging

try:  # Keeps the evaluator unit-testable without a configured Django install.
    from django.core.exceptions import FieldDoesNotExist
except ModuleNotFoundError:  # pragma: no cover - production always has Django
    class FieldDoesNotExist(Exception):
        pass

logger = logging.getLogger(__name__)

# A scoped grant is only meaningful for resources with a stable owner column.
# Resources absent from this map reject ``own`` rather than guessing.
OWNERSHIP_FIELDS = {
    "hms.patients": ("user_id", "created_by_user_id"),
    "hms.doctors": ("user_id",),
    "hms.appointments": ("doctor_id", "created_by_user_id"),
    "hms.opd": ("doctor_id", "created_by_user_id"),
    "hms.ipd": ("doctor_id", "created_by_user_id"),
    "hms.clinical": ("doctor_id", "recorded_by_user_id", "created_by_user_id"),
    "hms.webhooks": ("created_by_user_id",),
}


def _request_value(subject, name, default=None):
    return getattr(subject, name, getattr(getattr(subject, "user", None), name, default))


def _permissions(subject):
    return _request_value(subject, "permissions", {}) or {}


def _actor_id(subject):
    return _request_value(subject, "user_id", _request_value(subject, "id", None))


def _log(event, subject, key, **extra):
    logger.warning(event, extra={"permission_event": event, "permission_key": key,
                                 "permission_user_id": str(_actor_id(subject)),
                                 "permission_roles": _request_value(subject, "roles", []), **extra})


def read_permission_value(subject, key):
    """Return a raw grant using canonical then TEMPORARY migration readers."""
    permissions = _permissions(subject)
    if not isinstance(permissions, dict):
        return None
    if key in permissions:  # canonical flat key
        return permissions[key]
    if key == "admin.full_access.enabled" and "admin.full_access" in permissions:
        # TEMPORARY migration reader for the historical flat admin flag.
        return permissions["admin.full_access"]
    if key.startswith("hms."):
        _, resource, action = key.split(".", 2)
        legacy_admin_key = f"admin.{resource}.{action}"
        if legacy_admin_key in permissions:  # TEMPORARY pre-HMS reader
            return permissions[legacy_admin_key]
        nested = permissions.get("hms", {})
        if isinstance(nested, dict) and isinstance(nested.get(resource), dict):
            return nested[resource].get(action)  # TEMPORARY nested reader
    return None


def normalize_grant(subject, key):
    value = read_permission_value(subject, key)
    if value is True:
        return "all"
    if value is False or value is None:
        return None
    if value in ("own", "all"):
        return value
    if value == "team":
        _log("permission_legacy_team_normalized", subject, key, normalized_to="all")
        return "all"
    if isinstance(value, str):
        _log("permission_unknown_value_rejected", subject, key, rejected_value=value)
    return None


def _resource_key(key):
    return ".".join(key.split(".")[:2])


def _owner_value(obj, key):
    for field in OWNERSHIP_FIELDS.get(_resource_key(key), ()):
        if hasattr(obj, field):
            return getattr(obj, field), field
    return None, None


def has_permission(subject, key, obj=None, owner_id=None):
    """Evaluate one grant.  Own grants fail closed without resolvable ownership."""
    if _request_value(subject, "is_super_admin", False):
        return True
    if key.startswith(("admin.", "hms.")) and normalize_grant(subject, "admin.full_access.enabled") == "all":
        return True
    grant = normalize_grant(subject, key)
    if grant == "all":
        return True
    if grant != "own":
        return False
    if owner_id is None and obj is not None:
        owner_id, field = _owner_value(obj, key)
    else:
        field = "explicit_owner_id" if owner_id is not None else None
    if owner_id is None or not field:
        _log("permission_own_owner_unresolved", subject, key)
        return False
    return str(owner_id) == str(_actor_id(subject))


def _tenant_queryset(queryset, subject):
    tenant_id = _request_value(subject, "tenant_id")
    if tenant_id is None:
        return queryset.none()
    try:
        return queryset.filter(tenant_id=tenant_id)
    except (FieldDoesNotExist, AttributeError):
        _log("permission_tenant_field_unresolved", subject, "<queryset>")
        return queryset.none()


def get_queryset_for_permission(subject, key, queryset):
    """Tenant-filter FIRST, then apply the permitted scope."""
    tenant_queryset = _tenant_queryset(queryset, subject)
    if _request_value(subject, "is_super_admin", False):
        return tenant_queryset
    if key.startswith(("admin.", "hms.")) and normalize_grant(subject, "admin.full_access.enabled") == "all":
        return tenant_queryset
    grant = normalize_grant(subject, key)
    if grant == "all":
        return tenant_queryset
    if grant != "own":
        return queryset.none()
    fields = OWNERSHIP_FIELDS.get(_resource_key(key), ())
    model = getattr(queryset, "model", None)
    for field in fields:
        try:
            if model is None:
                # QuerySet-like test doubles and custom managers may not expose model.
                return tenant_queryset.filter(**{field: _actor_id(subject)})
            model._meta.get_field(field)
            return tenant_queryset.filter(**{field: _actor_id(subject)})
        except (FieldDoesNotExist, AttributeError):
            continue
    _log("permission_own_owner_field_unresolved", subject, key)
    return queryset.none()
