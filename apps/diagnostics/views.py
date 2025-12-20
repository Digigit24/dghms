from rest_framework import viewsets
from .models import Investigation, Requisition, DiagnosticOrder, LabReport, InvestigationRange
from .serializers import (
    InvestigationSerializer, RequisitionSerializer, 
    DiagnosticOrderSerializer, LabReportSerializer, InvestigationRangeSerializer
)
from common.drf_auth import HMSPermission

class InvestigationViewSet(viewsets.ModelViewSet):
    queryset = Investigation.objects.all()
    serializer_class = InvestigationSerializer
    permission_classes = [HMSPermission]
    hms_module = 'diagnostics'

    def get_queryset(self):
        queryset = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return queryset.filter(tenant_id=self.request.tenant_id)
        return queryset

class RequisitionViewSet(viewsets.ModelViewSet):
    queryset = Requisition.objects.all()
    serializer_class = RequisitionSerializer
    permission_classes = [HMSPermission]
    hms_module = 'diagnostics'

    def get_queryset(self):
        queryset = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return queryset.filter(tenant_id=self.request.tenant_id)
        return queryset

class DiagnosticOrderViewSet(viewsets.ModelViewSet):
    queryset = DiagnosticOrder.objects.all()
    serializer_class = DiagnosticOrderSerializer
    permission_classes = [HMSPermission]
    hms_module = 'diagnostics'

    def get_queryset(self):
        queryset = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return queryset.filter(tenant_id=self.request.tenant_id)
        return queryset

class LabReportViewSet(viewsets.ModelViewSet):
    queryset = LabReport.objects.all()
    serializer_class = LabReportSerializer
    permission_classes = [HMSPermission]
    hms_module = 'diagnostics'

    def get_queryset(self):
        queryset = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return queryset.filter(tenant_id=self.request.tenant_id)
        return queryset

class InvestigationRangeViewSet(viewsets.ModelViewSet):
    queryset = InvestigationRange.objects.all()
    serializer_class = InvestigationRangeSerializer
    permission_classes = [HMSPermission]
    hms_module = 'diagnostics'

    def get_queryset(self):
        queryset = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return queryset.filter(tenant_id=self.request.tenant_id)
        return queryset