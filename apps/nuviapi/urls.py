# apps/nuviapi/urls.py

from django.urls import path
from .views import nuvi_form_submit_api

app_name = 'nuviapi'

urlpatterns = [
    path('nuviformsubmit', nuvi_form_submit_api, name='nuvi_form_submit'),
]
