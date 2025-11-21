# opd/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    VisitViewSet,
    OPDBillViewSet,
    ProcedureMasterViewSet,
    ProcedurePackageViewSet,
    ProcedureBillViewSet,
    ClinicalNoteViewSet,
    VisitFindingViewSet,
    VisitAttachmentViewSet,
    ClinicalNoteTemplateGroupViewSet,
    ClinicalNoteTemplateViewSet,
    ClinicalNoteTemplateFieldViewSet,
    ClinicalNoteTemplateFieldOptionViewSet,
    ClinicalNoteTemplateResponseViewSet,
    ClinicalNoteTemplateFieldResponseViewSet
)

app_name = 'opd'

# Create router and register viewsets
router = DefaultRouter()
router.register(r'visits', VisitViewSet, basename='visit')
router.register(r'opd-bills', OPDBillViewSet, basename='opd-bill')
router.register(r'procedure-masters', ProcedureMasterViewSet, basename='procedure-master')
router.register(r'procedure-packages', ProcedurePackageViewSet, basename='procedure-package')
router.register(r'procedure-bills', ProcedureBillViewSet, basename='procedure-bill')
router.register(r'clinical-notes', ClinicalNoteViewSet, basename='clinical-note')
router.register(r'visit-findings', VisitFindingViewSet, basename='visit-finding')
router.register(r'visit-attachments', VisitAttachmentViewSet, basename='visit-attachment')

# Clinical Note Template Routes
router.register(r'template-groups', ClinicalNoteTemplateGroupViewSet, basename='template-group')
router.register(r'templates', ClinicalNoteTemplateViewSet, basename='template')
router.register(r'template-fields', ClinicalNoteTemplateFieldViewSet, basename='template-field')
router.register(r'template-field-options', ClinicalNoteTemplateFieldOptionViewSet, basename='template-field-option')
router.register(r'template-responses', ClinicalNoteTemplateResponseViewSet, basename='template-response')
router.register(r'template-field-responses', ClinicalNoteTemplateFieldResponseViewSet, basename='template-field-response')

urlpatterns = [
    path('', include(router.urls)),
]