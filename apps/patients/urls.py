from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PatientProfileViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'profiles', PatientProfileViewSet, basename='patient')

import logging as _log
_log.getLogger(__name__).warning('[PATIENTS URLS] Loading urls.py v2 with explicit export paths')

_export_view           = PatientProfileViewSet.as_view({'get': 'export'})
_available_cols_view   = PatientProfileViewSet.as_view({'get': 'available_columns'})

urlpatterns = [
    # Explicit paths for export endpoints (must come before router include)
    path('profiles/export/',            _export_view,         name='patient-export'),
    path('profiles/available_columns/', _available_cols_view, name='patient-available-columns'),
    path('', include(router.urls)),
]

# Available URLs:
# GET    /api/patients/profiles/              - List all patients
# POST   /api/patients/profiles/              - Create new patient
# GET    /api/patients/profiles/{id}/         - Get patient details
# PUT    /api/patients/profiles/{id}/         - Update patient (full)
# PATCH  /api/patients/profiles/{id}/         - Update patient (partial)
# DELETE /api/patients/profiles/{id}/         - Delete patient
#
# Custom Actions:
# POST   /api/patients/profiles/register/                     - Register new patient
# GET    /api/patients/profiles/statistics/                   - Get patient statistics
# POST   /api/patients/profiles/{id}/record_vitals/          - Record vitals
# GET    /api/patients/profiles/{id}/vitals/                 - Get vitals
# POST   /api/patients/profiles/{id}/add_allergy/            - Add allergy
# GET    /api/patients/profiles/{id}/allergies/              - Get allergies
# PUT    /api/patients/profiles/{id}/allergies/{allergy_id}/ - Update allergy
# DELETE /api/patients/profiles/{id}/allergies/{allergy_id}/ - Delete allergy
# POST   /api/patients/profiles/{id}/update_visit/           - Update visit info
# POST   /api/patients/profiles/{id}/activate/               - Activate patient
# POST   /api/patients/profiles/{id}/mark_deceased/          - Mark as deceased
# GET    /api/patients/profiles/available_columns/           - List exportable column keys & labels
# GET    /api/patients/profiles/export/                      - Bulk export (CSV/XLSX, flexible columns)