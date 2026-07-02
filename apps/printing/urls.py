"""URL routes for the printing app.

Mounted under ``/api/print/`` in ``hms/urls.py``.
"""

from django.urls import path

from .views import PrintBatchView, PrintPreviewView, PrintRenderView

app_name = "printing"

urlpatterns = [
    path("preview/", PrintPreviewView.as_view(), name="preview"),
    path("render/", PrintRenderView.as_view(), name="render"),
    path("batch/", PrintBatchView.as_view(), name="batch"),
]
