"""Expiry-alert threshold resolution shared by inventory workflows."""

from apps.hospital.models import Hospital


DEFAULT_EXPIRY_ALERT_DAYS = 90


def get_tenant_default_expiry_alert_days(tenant_id) -> int:
    config = (
        Hospital.objects.filter(tenant_id=tenant_id)
        .values_list("inventory_config", flat=True)
        .first()
        or {}
    )
    value = config.get("default_expiry_alert_days")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return DEFAULT_EXPIRY_ALERT_DAYS


def resolve_expiry_alert_days(item, tenant_default=None) -> int:
    """Resolve item -> category -> tenant -> hardcoded expiry lead time."""
    if item.expiry_alert_days is not None:
        return item.expiry_alert_days
    category = getattr(item, "category", None)
    if category is not None and category.expiry_alert_days is not None:
        return category.expiry_alert_days
    if tenant_default is None:
        tenant_default = get_tenant_default_expiry_alert_days(item.tenant_id)
    return tenant_default
