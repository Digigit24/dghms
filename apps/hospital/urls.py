from django.urls import path
from .views import HospitalConfigView, HospitalNavStyleView, HospitalLetterheadView

app_name = 'hospital'

urlpatterns = [
    path('config/', HospitalConfigView.as_view(), name='config'),
    path('config/nav-style/', HospitalNavStyleView.as_view(), name='nav-style'),
    path('config/letterhead/', HospitalLetterheadView.as_view(), name='letterhead'),
]
