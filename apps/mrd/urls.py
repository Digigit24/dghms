from django.urls import path
from .views import MrdDossierView, MrdExportDetailView, MrdExportDownloadView, MrdExportView, MrdWorklistView

urlpatterns = [
    path('worklist/', MrdWorklistView.as_view()),
    path('patients/<int:patient_id>/dossier/', MrdDossierView.as_view()),
    path('exports/', MrdExportView.as_view()),
    path('exports/<uuid:export_id>/', MrdExportDetailView.as_view()),
    path('exports/<uuid:export_id>/download/', MrdExportDownloadView.as_view()),
]
