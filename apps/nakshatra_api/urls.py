# apps/nakshatra_api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import nakshatra_form_submit_api, NakshatraLeadViewSet

# Create router for ViewSet
router = DefaultRouter()
router.register(r'nakshatra/leads', NakshatraLeadViewSet, basename='nakshatra-leads')

urlpatterns = [
    # Form submission endpoint (public, no auth)
    path('nakshatra/submit/', nakshatra_form_submit_api, name='nakshatra_form_submit'),

    # ViewSet endpoints (list, retrieve, stats)
    path('', include(router.urls)),
]
