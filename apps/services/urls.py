from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ServiceCategoryViewSet,
    DiagnosticTestViewSet,
    NursingCarePackageViewSet,
    HomeHealthcareServiceViewSet
)

router = DefaultRouter()
router.register(r'categories', ServiceCategoryViewSet)
router.register(r'diagnostic-tests', DiagnosticTestViewSet)
router.register(r'nursing-packages', NursingCarePackageViewSet)
router.register(r'home-healthcare', HomeHealthcareServiceViewSet)

urlpatterns = [
    path('', include(router.urls))
]
