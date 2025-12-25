from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ProductCategoryViewSet,
    PharmacyProductViewSet,
    CartViewSet,
    PharmacyOrderViewSet,
    RazorpayCreateOrderView
)

router = DefaultRouter()
router.register(r'categories', ProductCategoryViewSet)
router.register(r'products', PharmacyProductViewSet)
router.register(r'cart', CartViewSet)
router.register(r'orders', PharmacyOrderViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('razorpay/create-order/', RazorpayCreateOrderView.as_view(), name='razorpay-create-order'),
]