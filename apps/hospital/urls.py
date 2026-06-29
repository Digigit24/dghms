from django.urls import path
from .views import HospitalConfigView

app_name = 'hospital'

urlpatterns = [
    path('config/', HospitalConfigView.as_view(), name='config'),
]
