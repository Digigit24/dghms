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
    filterset_fields = ['payment_status', 'admission']
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
            billed_by_id=request.user_id,
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

    @action(detail=True, methods=['post'])
    def sync_clinical_charges(self, request, pk=None):
        """
        Sync all clinical charges (orders) to billing items.
        This action:
        1. Identifies all unbilled items for the admission.
        2. Creates IPDBillItem entries for them.
        3. Updates the source Orders to link them to these new Bill Items.
        4. Runs add_bed_charges() to ensure bed charges are up to date.
        """
        from django.db import transaction
        from django.contrib.contenttypes.models import ContentType
        from apps.diagnostics.models import (
            Requisition, DiagnosticOrder, MedicineOrder,
            ProcedureOrder, PackageOrder
        )
        from apps.panchakarma.models import PanchakarmaOrder

        billing = self.get_object()
        admission = billing.admission

        if admission.tenant_id != request.tenant_id:
            raise PermissionDenied("Access denied")

        created_items = []
        updated_orders = []

        with transaction.atomic():
            admission_ct = ContentType.objects.get_for_model(admission)
            requisitions = Requisition.objects.filter(
                tenant_id=request.tenant_id,
                content_type=admission_ct,
                object_id=admission.pk
            )

            # Process DiagnosticOrders
            diagnostic_orders = DiagnosticOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True  # Correct GFK null check
            ).select_related('investigation', 'requisition')

            for order in diagnostic_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    billing=billing,
                    item_name=order.investigation.name,
                    source='Lab' if order.investigation.category == 'laboratory' else 'Radiology',
                    quantity=1,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Test: {order.investigation.code}"
                )
                created_items.append(item)
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                updated_orders.append(order)

            # Process MedicineOrders
            medicine_orders = MedicineOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('product', 'requisition')

            for order in medicine_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    billing=billing,
                    item_name=order.product.product_name,
                    source='Pharmacy',
                    quantity=order.quantity,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Medicine - Qty: {order.quantity}"
                )
                created_items.append(item)
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                updated_orders.append(order)

            # Process ProcedureOrders
            procedure_orders = ProcedureOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('procedure', 'requisition')

            for order in procedure_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    billing=billing,
                    item_name=order.procedure.name,
                    source='Procedure',
                    quantity=order.quantity,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Procedure - Qty: {order.quantity}"
                )
                created_items.append(item)
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                updated_orders.append(order)

            # Process PackageOrders
            package_orders = PackageOrder.objects.filter(
                tenant_id=request.tenant_id,
                requisition__in=requisitions,
                bill_item_content_type__isnull=True
            ).select_related('package', 'requisition')

            for order in package_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    billing=billing,
                    item_name=order.package.name,
                    source='Package',
                    quantity=order.quantity,
                    unit_price=order.price,
                    system_calculated_price=order.price,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes=f"Package - Qty: {order.quantity}"
                )
                created_items.append(item)
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                updated_orders.append(order)

            # Process PanchakarmaOrders
            panchakarma_orders = PanchakarmaOrder.objects.filter(
                tenant_id=request.tenant_id,
                content_type=admission_ct,
                object_id=admission.pk,
                bill_item_content_type__isnull=True
            ).select_related('therapy')

            for order in panchakarma_orders:
                item = IPDBillItem.objects.create(
                    tenant_id=request.tenant_id,
                    billing=billing,
                    item_name=order.therapy.name,
                    source='Therapy',
                    quantity=1,
                    unit_price=order.therapy.base_charge,
                    system_calculated_price=order.therapy.base_charge,
                    origin_content_type=ContentType.objects.get_for_model(order),
                    origin_object_id=order.pk,
                    notes="Therapy session"
                )
                created_items.append(item)
                order.bill_item_link = item
                order.save(update_fields=['bill_item_content_type', 'bill_item_object_id'])
                updated_orders.append(order)

            # Update bed charges
            billing.add_bed_charges()

        return Response({
            'success': True,
            'message': f'Synced {len(created_items)} clinical charges to billing',
            'created_items': len(created_items),
            'updated_orders': len(updated_orders),
            'items': IPDBillItemSerializer(created_items, many=True).data
        })


class IPDBillItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for IPD Bill Items management."""

    queryset = IPDBillItem.objects.select_related('bill')
    serializer_class = IPDBillItemSerializer
    hms_module = 'ipd'
    permission_classes = [HMSPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['bill', 'source']
    ordering_fields = ['created_at']
    ordering = ['bill', 'source', 'id']

    def perform_create(self, serializer):
        """Set tenant_id automatically."""
        serializer.save(tenant_id=self.request.tenant_id)
