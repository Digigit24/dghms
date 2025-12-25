# apps/nakshatra_api/urls.py

from django.urls import path
from .views import nakshatra_form_submit_api

urlpatterns = [
    path('nakshatra/submit/', nakshatra_form_submit_api, name='nakshatra_form_submit'),
]
