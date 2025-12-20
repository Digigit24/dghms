from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InvestigationViewSet, RequisitionViewSet, 
    DiagnosticOrderViewSet, LabReportViewSet, InvestigationRangeViewSet
)

router = DefaultRouter()
router.register(r'investigations', InvestigationViewSet)
router.register(r'requisitions', RequisitionViewSet)
router.register(r'orders', DiagnosticOrderViewSet)
router.register(r'reports', LabReportViewSet)
router.register(r'ranges', InvestigationRangeViewSet)

urlpatterns = [
    path('', include(router.urls)),
]