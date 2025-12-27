from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    OrderViewSet,
    FeeTypeViewSet,
    RazorpayConfigViewSet,
    RazorpayWebhookView
)

# Create a router and register our viewsets
router = DefaultRouter()
router.register(r'', OrderViewSet, basename='orders')
router.register(r'fee-types', FeeTypeViewSet, basename='fee-types')
router.register(r'razorpay-config', RazorpayConfigViewSet, basename='razorpay-config')

urlpatterns = [
    path('', include(router.urls)),
    # Razorpay webhook endpoint (no auth required, verified by signature)
    path('webhooks/razorpay/', RazorpayWebhookView.as_view(), name='razorpay-webhook'),
]