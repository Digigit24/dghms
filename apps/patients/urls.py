from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PatientProfileViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'profiles', PatientProfileViewSet, basename='patient')

urlpatterns = [
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