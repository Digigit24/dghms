from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ProductCategoryViewSet,
    PharmacyProductViewSet,
    CartViewSet,
    PharmacyOrderViewSet
)
from .prescription_views import PrescriptionViewSet

router = DefaultRouter()
router.register(r'categories', ProductCategoryViewSet)
router.register(r'products', PharmacyProductViewSet)
router.register(r'cart', CartViewSet)
router.register(r'orders', PharmacyOrderViewSet)
router.register(r'prescriptions', PrescriptionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
