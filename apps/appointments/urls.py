from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AppointmentViewSet, AppointmentTypeViewSet

# Create a router and register our viewsets
router = DefaultRouter()
router.register(r'types', AppointmentTypeViewSet, basename='appointment-type')
router.register(r'', AppointmentViewSet, basename='appointment')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
]
