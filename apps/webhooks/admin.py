from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import TenantWebhook, WebhookDelivery


class TenantWebhookAdmin(TenantModelAdmin):
    list_display = ["name", "url", "is_active", "tenant_id", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "url"]
    readonly_fields = ["tenant_id", "created_at", "updated_at", "created_by_user_id"]


class WebhookDeliveryAdmin(TenantModelAdmin):
    list_display = ["event_name", "webhook", "status", "attempt_count", "tenant_id", "created_at"]
    list_filter = ["status", "event_name"]
    readonly_fields = ["tenant_id", "webhook", "event_name", "payload", "created_at", "updated_at", "created_by_user_id"]


hms_admin_site.register(TenantWebhook, TenantWebhookAdmin)
hms_admin_site.register(WebhookDelivery, WebhookDeliveryAdmin)
