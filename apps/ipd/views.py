# ipd/views.py
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from common.mixins import TenantViewSetMixin
from common.drf_auth import HMSPermission
from .models import Ward, Bed, Admission, BedTransfer, IPDBilling, IPDBillItem
from .serializers import (
    WardSerializer, BedSerializer, BedListSerializer,
    AdmissionSerializer, AdmissionListSerializer,
    BedTransferSerializer, IPDBillingSerializer, IPDBillingListSerializer,
    IPDBillItemSerializer
)


class WardViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for Ward management."""

    queryset = Ward.objects.all()
    serializer_class = WardSerializer
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'is_active', 'floor']
    search_fields = ['name', 'floor']
    ordering_fields = ['name', 'floor', 'created_at']
    ordering = ['floor', 'name']

    def perform_create(self, serializer):
        """Set tenant_id and created_by_user_id automatically."""
        serializer.save(tenant_id=self.request.tenant_id)


class BedViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for Bed management."""

    queryset = Bed.objects.select_related('ward')
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ward', 'bed_type', 'is_occupied', 'status', 'is_active']
    search_fields = ['bed_number', 'ward__name']
    ordering_fields = ['bed_number', 'daily_charge', 'created_at']
    ordering = ['ward', 'bed_number']

    def get_serializer_class(self):
        if self.action == 'list':
            return BedListSerializer
        return BedSerializer

    def perform_create(self, serializer):
        """Set tenant_id automatically."""
        serializer.save(tenant_id=self.request.tenant_id)

    @action(detail=False, methods=['get'])
    def available(self, request):
        """Get all available beds."""
        beds = self.get_queryset().filter(is_occupied=False, status='available', is_active=True)
        serializer = self.get_serializer(beds, many=True)
        return Response(serializer.data)


class AdmissionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for IPD Admission management."""

    queryset = Admission.objects.select_related('patient', 'ward', 'bed')
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'ward', 'doctor_id', 'patient']
    search_fields = ['admission_id', 'patient__first_name', 'patient__last_name']
    ordering_fields = ['admission_date', 'discharge_date', 'created_at']
    ordering = ['-admission_date']

    def get_serializer_class(self):
        if self.action == 'list':
            return AdmissionListSerializer
        return AdmissionSerializer

    def perform_create(self, serializer):
        """Set tenant_id and created_by_user_id automatically."""
        serializer.save(
            tenant_id=self.request.tenant_id,
            created_by_user_id=self.request.user_id
        )

    @action(detail=True, methods=['post'])
    def discharge(self, request, pk=None):
        """Discharge a patient."""
        admission = self.get_object()

        if admission.status != 'admitted':
            return Response(
                {'error': 'Patient is not currently admitted'},
                status=status.HTTP_400_BAD_REQUEST
            )

        discharge_type = request.data.get('discharge_type', 'Normal')
        discharge_summary = request.data.get('discharge_summary', '')

        admission.discharge(
            discharge_type=discharge_type,
            discharge_summary=discharge_summary,
            discharged_by_user_id=request.user_id
        )

        serializer = self.get_serializer(admission)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active admissions."""
        admissions = self.get_queryset().filter(status='admitted')
        serializer = self.get_serializer(admissions, many=True)
        return Response(serializer.data)


class BedTransferViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for Bed Transfer management."""

    queryset = BedTransfer.objects.select_related('admission', 'from_bed', 'to_bed')
    serializer_class = BedTransferSerializer
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['admission']
    ordering_fields = ['transfer_date', 'created_at']
    ordering = ['-transfer_date']

    def perform_create(self, serializer):
        """Set tenant_id and performed_by_user_id automatically."""
        serializer.save(
            tenant_id=self.request.tenant_id,
            performed_by_user_id=self.request.user_id
        )


class IPDBillingViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for IPD Billing management."""

    queryset = IPDBilling.objects.select_related('admission', 'admission__patient')
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'admission']
    search_fields = ['bill_number', 'admission__admission_id', 'admission__patient__first_name']
    ordering_fields = ['bill_date', 'total_amount', 'created_at']
    ordering = ['-bill_date']

    def get_serializer_class(self):
        if self.action == 'list':
            return IPDBillingListSerializer
        return IPDBillingSerializer

    def create(self, request, *args, **kwargs):
        """
        Create a new IPD Billing instance.
        The admission_id should be provided in the request data.
        """
        admission_id = request.data.get('admission')
        if not admission_id:
            return Response(
                {'error': 'Admission ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            admission = Admission.objects.get(id=admission_id, tenant_id=request.tenant_id)
        except Admission.DoesNotExist:
            return Response(
                {'error': 'Admission not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check permission for the specific admission object
        self.check_object_permissions(request, admission)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Pass tenant_id, user_id, and admission instance to the serializer's create method
        serializer.save(
            tenant_id=request.tenant_id,
            created_by_user_id=request.user_id,
            admission=admission
        )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['post'])
    def add_bed_charges(self, request, pk=None):
        """Calculate and add bed charges to the bill."""
        billing = self.get_object()
        billing.add_bed_charges()

        serializer = self.get_serializer(billing)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        """Add a payment to the bill."""
        billing = self.get_object()
        amount = request.data.get('amount')

        if not amount:
            return Response(
                {'error': 'Amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from decimal import Decimal
            amount = Decimal(str(amount))
            if amount <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return Response(
                {'error': 'Invalid amount'},
                status=status.HTTP_400_BAD_REQUEST
            )

        billing.paid_amount += amount
        billing.calculate_totals()
        billing.save()

        serializer = self.get_serializer(billing)
        return Response(serializer.data)


class IPDBillItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for IPD Bill Items management."""

    queryset = IPDBillItem.objects.select_related('billing')
    serializer_class = IPDBillItemSerializer
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['billing', 'source']
    ordering_fields = ['created_at']
    ordering = ['billing', 'source', 'id']

    def perform_create(self, serializer):
        """Set tenant_id automatically."""
        serializer.save(tenant_id=self.request.tenant_id)
