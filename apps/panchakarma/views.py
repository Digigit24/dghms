from rest_framework import viewsets
from .models import Therapy, PanchakarmaOrder, PanchakarmaSession
from .serializers import TherapySerializer, PanchakarmaOrderSerializer, PanchakarmaSessionSerializer
from common.drf_auth import HMSPermission

class TherapyViewSet(viewsets.ModelViewSet):
    queryset = Therapy.objects.all()
    serializer_class = TherapySerializer
    permission_classes = [HMSPermission]
    hms_module = 'panchakarma'

    def get_queryset(self):
        queryset = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return queryset.filter(tenant_id=self.request.tenant_id)
        return queryset

class PanchakarmaOrderViewSet(viewsets.ModelViewSet):
    queryset = PanchakarmaOrder.objects.all()
    serializer_class = PanchakarmaOrderSerializer
    permission_classes = [HMSPermission]
    hms_module = 'panchakarma'

    def get_queryset(self):
        queryset = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return queryset.filter(tenant_id=self.request.tenant_id)
        return queryset

class PanchakarmaSessionViewSet(viewsets.ModelViewSet):
    queryset = PanchakarmaSession.objects.all()
    serializer_class = PanchakarmaSessionSerializer
    permission_classes = [HMSPermission]
    hms_module = 'panchakarma'

    def get_queryset(self):
        queryset = super().get_queryset()
        if hasattr(self.request, 'tenant_id'):
            return queryset.filter(tenant_id=self.request.tenant_id)
        return queryset
