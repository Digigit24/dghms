from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    Investigation, Requisition, DiagnosticOrder, LabReport, InvestigationRange,
    MedicineOrder, ProcedureOrder, PackageOrder
)
from .serializers import (
    InvestigationSerializer, RequisitionSerializer,
    DiagnosticOrderSerializer, LabReportSerializer, InvestigationRangeSerializer,
    MedicineOrderSerializer, ProcedureOrderSerializer, PackageOrderSerializer
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

    @action(detail=True, methods=['post'], url_path='add_medicine')
    def add_medicine(self, request, pk=None):
        """
        Add a medicine order to this requisition.
        Expected payload: {product_id: int, quantity: int, price: decimal (optional)}
        """
        requisition = self.get_object()

        # Validate requisition type
        if requisition.requisition_type != 'medicine':
            return Response(
                {'error': 'This requisition is not of type "medicine". Current type: ' + requisition.requisition_type},
                status=status.HTTP_400_BAD_REQUEST
            )

        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)
        price = request.data.get('price')

        if not product_id:
            return Response({'error': 'product_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.pharmacy.models import PharmacyProduct
            product = PharmacyProduct.objects.get(id=product_id, tenant_id=request.tenant_id)
        except PharmacyProduct.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

        # Create the medicine order
        medicine_order = MedicineOrder.objects.create(
            tenant_id=request.tenant_id,
            requisition=requisition,
            product=product,
            quantity=quantity,
            price=price if price else (product.selling_price or product.mrp)
        )

        serializer = MedicineOrderSerializer(medicine_order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='add_procedure')
    def add_procedure(self, request, pk=None):
        """
        Add a procedure order to this requisition.
        Expected payload: {procedure_id: int, quantity: int, price: decimal (optional)}
        """
        requisition = self.get_object()

        # Validate requisition type
        if requisition.requisition_type != 'procedure':
            return Response(
                {'error': 'This requisition is not of type "procedure". Current type: ' + requisition.requisition_type},
                status=status.HTTP_400_BAD_REQUEST
            )

        procedure_id = request.data.get('procedure_id')
        quantity = request.data.get('quantity', 1)
        price = request.data.get('price')

        if not procedure_id:
            return Response({'error': 'procedure_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.opd.models import ProcedureMaster
            procedure = ProcedureMaster.objects.get(id=procedure_id, tenant_id=request.tenant_id)
        except ProcedureMaster.DoesNotExist:
            return Response({'error': 'Procedure not found'}, status=status.HTTP_404_NOT_FOUND)

        # Create the procedure order
        procedure_order = ProcedureOrder.objects.create(
            tenant_id=request.tenant_id,
            requisition=requisition,
            procedure=procedure,
            quantity=quantity,
            price=price if price else procedure.default_charge
        )

        serializer = ProcedureOrderSerializer(procedure_order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='add_package')
    def add_package(self, request, pk=None):
        """
        Add a package order to this requisition.
        Expected payload: {package_id: int, quantity: int, price: decimal (optional)}
        """
        requisition = self.get_object()

        # Validate requisition type
        if requisition.requisition_type != 'package':
            return Response(
                {'error': 'This requisition is not of type "package". Current type: ' + requisition.requisition_type},
                status=status.HTTP_400_BAD_REQUEST
            )

        package_id = request.data.get('package_id')
        quantity = request.data.get('quantity', 1)
        price = request.data.get('price')

        if not package_id:
            return Response({'error': 'package_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.opd.models import ProcedurePackage
            package = ProcedurePackage.objects.get(id=package_id, tenant_id=request.tenant_id)
        except ProcedurePackage.DoesNotExist:
            return Response({'error': 'Package not found'}, status=status.HTTP_404_NOT_FOUND)

        # Create the package order
        package_order = PackageOrder.objects.create(
            tenant_id=request.tenant_id,
            requisition=requisition,
            package=package,
            quantity=quantity,
            price=price if price else package.discounted_charge
        )

        serializer = PackageOrderSerializer(package_order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

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