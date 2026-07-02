"""URL configuration for the clinical app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .ai_views import ClinicalFormAIWizardViewSet
from .views import (
    ClinicalDocumentInstanceViewSet,
    ClinicalDocumentTemplateViewSet,
    ClinicalFormFieldViewSet,
    ClinicalFormGroupItemViewSet,
    ClinicalFormGroupViewSet,
    ClinicalFormSectionViewSet,
    ClinicalFormTemplateViewSet,
    ClinicalFormViewSet,
    ClinicalPicklistGroupMembershipViewSet,
    ClinicalPicklistGroupViewSet,
    ClinicalPicklistItemViewSet,
    ClinicalPicklistViewSet,
    ClinicalPrintTemplateViewSet,
    ClinicalRecordViewSet,
    FormSectionPlacementViewSet,
    MrdChecklistLineViewSet,
    SavedFormSnapshotViewSet,
    UserFormPreferenceViewSet,
)

router = DefaultRouter()
router.register(r"forms", ClinicalFormViewSet, basename="clinicalform")
router.register(r"sections", ClinicalFormSectionViewSet, basename="clinicalformsection")
router.register(r"placements", FormSectionPlacementViewSet, basename="formsectionplacement")
router.register(r"fields", ClinicalFormFieldViewSet, basename="clinicalformfield")
router.register(r"groups", ClinicalFormGroupViewSet, basename="clinicalformgroup")
router.register(r"group-items", ClinicalFormGroupItemViewSet, basename="clinicalformgroupitem")
router.register(r"picklists", ClinicalPicklistViewSet, basename="clinicalpicklist")
router.register(r"picklist-items", ClinicalPicklistItemViewSet, basename="clinicalpicklistitem")
router.register(r"picklist-groups", ClinicalPicklistGroupViewSet, basename="clinicalpicklistgroup")
router.register(r"picklist-group-memberships", ClinicalPicklistGroupMembershipViewSet, basename="clinicalpicklistgroupmembership")
router.register(r"records", ClinicalRecordViewSet, basename="clinicalrecord")
router.register(r"documents/templates", ClinicalDocumentTemplateViewSet, basename="clinicaldocumenttemplate")
router.register(r"documents/instances", ClinicalDocumentInstanceViewSet, basename="clinicaldocumentinstance")
router.register(r"print-templates", ClinicalPrintTemplateViewSet, basename="clinicalprinttemplate")
router.register(r"mrd-lines", MrdChecklistLineViewSet, basename="mrdchecklistline")
router.register(r"preferences", UserFormPreferenceViewSet, basename="userformpreference")
router.register(r"snapshots", SavedFormSnapshotViewSet, basename="savedformsnapshot")
router.register(r"form-templates", ClinicalFormTemplateViewSet, basename="clinicalformtemplate")
router.register(r"ai-wizard", ClinicalFormAIWizardViewSet, basename="clinicalformaiwizard")

urlpatterns = [
    path(
        "encounters/<str:encounter_type>/<int:encounter_id>/forms/",
        ClinicalFormViewSet.as_view({"get": "encounter_forms"}),
        name="clinical-encounter-forms",
    ),
    path(
        "encounters/<str:encounter_type>/<int:encounter_id>/mrd-checklist/",
        ClinicalFormViewSet.as_view({"get": "mrd_checklist"}),
        name="clinical-encounter-mrd-checklist",
    ),
    path(
        "encounters/<str:encounter_type>/<int:encounter_id>/pull/",
        ClinicalFormViewSet.as_view({"get": "pull"}),
        name="clinical-encounter-pull",
    ),
    path("", include(router.urls)),
]
