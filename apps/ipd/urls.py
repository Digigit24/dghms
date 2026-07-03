# ipd/urls.py
from rest_framework.routers import DefaultRouter
from .views import (
    WardViewSet, BedViewSet, AdmissionViewSet,
    BedTransferViewSet, IPDBillingViewSet, IPDBillItemViewSet,
    IPDBillTemplateViewSet,
)

router = DefaultRouter()
router.register(r'wards', WardViewSet, basename='ward')
router.register(r'beds', BedViewSet, basename='bed')
router.register(r'admissions', AdmissionViewSet, basename='admission')
router.register(r'bed-transfers', BedTransferViewSet, basename='bed-transfer')
router.register(r'billings', IPDBillingViewSet, basename='ipd-billing')
router.register(r'bill-items', IPDBillItemViewSet, basename='ipd-bill-item')
router.register(r'bill-templates', IPDBillTemplateViewSet, basename='ipd-bill-template')

urlpatterns = router.urls
