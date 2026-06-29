from rest_framework.routers import DefaultRouter

from .views import TenantWebhookViewSet

router = DefaultRouter()
router.register(r"webhooks", TenantWebhookViewSet, basename="tenant-webhook")

urlpatterns = router.urls

