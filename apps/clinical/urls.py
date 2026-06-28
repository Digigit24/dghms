"""URL configuration for the clinical app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .ai_views import ClinicalFormAIWizardViewSet
from .views import (
    ClinicalFormFieldViewSet,
    ClinicalFormSectionViewSet,
    ClinicalFormViewSet,
    ClinicalPicklistItemViewSet,
    ClinicalPicklistViewSet,
    ClinicalRecordViewSet,
    SavedFormSnapshotViewSet,
    UserFormPreferenceViewSet,
)

router = DefaultRouter()
router.register(r"forms", ClinicalFormViewSet, basename="clinicalform")
router.register(r"sections", ClinicalFormSectionViewSet, basename="clinicalformsection")
router.register(r"fields", ClinicalFormFieldViewSet, basename="clinicalformfield")
router.register(r"picklists", ClinicalPicklistViewSet, basename="clinicalpicklist")
router.register(r"picklist-items", ClinicalPicklistItemViewSet, basename="clinicalpicklistitem")
router.register(r"records", ClinicalRecordViewSet, basename="clinicalrecord")
router.register(r"preferences", UserFormPreferenceViewSet, basename="userformpreference")
router.register(r"snapshots", SavedFormSnapshotViewSet, basename="savedformsnapshot")
router.register(r"ai", ClinicalFormAIWizardViewSet, basename="clinicalformaiwizard")

urlpatterns = [
    path("", include(router.urls)),
]
