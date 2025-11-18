# opd/views.py
from django.db.models import Q, Count, Sum, Avg, F
from django.utils import timezone
from django.db import transaction
from datetime import date, timedelta

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.parsers import MultiPartParser, FormParser

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiExample
)

from .models import (
    Visit, OPDBill, ProcedureMaster, ProcedurePackage,
    ProcedureBill, ProcedureBillItem, ClinicalNote,
    VisitFinding, VisitAttachment,
    ClinicalNoteTemplateGroup, ClinicalNoteTemplate,
    ClinicalNoteTemplateField, ClinicalNoteTemplateFieldOption,
    ClinicalNoteTemplateResponse, ClinicalNoteTemplateFieldResponse
)
from .serializers import (
    VisitListSerializer, VisitDetailSerializer, VisitCreateUpdateSerializer,
    OPDBillListSerializer, OPDBillDetailSerializer, OPDBillCreateUpdateSerializer,
    ProcedureMasterListSerializer, ProcedureMasterDetailSerializer,
    ProcedureMasterCreateUpdateSerializer,
    ProcedurePackageListSerializer, ProcedurePackageDetailSerializer,
    ProcedurePackageCreateUpdateSerializer,
    ProcedureBillListSerializer, ProcedureBillDetailSerializer,
    ProcedureBillCreateUpdateSerializer,
    ClinicalNoteListSerializer, ClinicalNoteDetailSerializer,
    ClinicalNoteCreateUpdateSerializer,
    VisitFindingListSerializer, VisitFindingDetailSerializer,
    VisitFindingCreateUpdateSerializer,
    VisitAttachmentListSerializer, VisitAttachmentDetailSerializer,
    VisitAttachmentCreateUpdateSerializer,
    ClinicalNoteTemplateGroupSerializer,
    ClinicalNoteTemplateListSerializer, ClinicalNoteTemplateDetailSerializer,
    ClinicalNoteTemplateCreateUpdateSerializer,
    ClinicalNoteTemplateFieldListSerializer, ClinicalNoteTemplateFieldDetailSerializer,
    ClinicalNoteTemplateFieldCreateUpdateSerializer,
    ClinicalNoteTemplateResponseListSerializer, ClinicalNoteTemplateResponseDetailSerializer,
    ClinicalNoteTemplateResponseCreateUpdateSerializer
)


# ============================================================================
# PERMISSION CLASSES (Using Django Built-in Permissions)
# ============================================================================

class ActionPermissions(BasePermission):
    """
    Maps DRF actions to Django model permissions.
    Uses Django's built-in permission system (no custom permission classes).
    """
    APP_LABEL = 'opd'
    
    # Define action to permission mapping
    def get_permission_map(self, model_name):
        """Get permission map for a specific model"""
        return {
            'list': [f'{self.APP_LABEL}.view_{model_name}'],
            'retrieve': [f'{self.APP_LABEL}.view_{model_name}'],
            'create': [f'{self.APP_LABEL}.add_{model_name}'],
            'update': [f'{self.APP_LABEL}.change_{model_name}'],
            'partial_update': [f'{self.APP_LABEL}.change_{model_name}'],
            'destroy': [f'{self.APP_LABEL}.delete_{model_name}'],
        }
    
    def has_permission(self, request, view):
        """Check if user has required permissions"""
        user = request.user
        if not user or not user.is_authenticated:
            return False
        
        # Get model name from view
        model_name = getattr(view, 'permission_model_name', None)
        if not model_name:
            return True  # Allow if no model specified
        
        # Get required permissions for this action
        permission_map = self.get_permission_map(model_name)
        required_perms = permission_map.get(view.action, [])
        
        # Check if user has all required permissions
        return user.has_perms(required_perms) if required_perms else True


# ============================================================================
# VISIT VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List OPD Visits",
        description="Get paginated list of OPD visits with filtering and search",
        parameters=[
            OpenApiParameter(name='patient', type=int, description='Filter by patient ID'),
            OpenApiParameter(name='doctor', type=int, description='Filter by doctor ID'),
            OpenApiParameter(name='status', type=str, description='Filter by status'),
            OpenApiParameter(name='payment_status', type=str, description='Filter by payment status'),
            OpenApiParameter(name='visit_type', type=str, description='Filter by visit type'),
            OpenApiParameter(name='visit_date', type=str, description='Filter by visit date (YYYY-MM-DD)'),
            OpenApiParameter(name='search', type=str, description='Search by visit number or patient name'),
        ],
        tags=['OPD - Visits']
    ),
    retrieve=extend_schema(
        summary="Get Visit Details",
        description="Retrieve detailed information about a specific visit",
        tags=['OPD - Visits']
    ),
    create=extend_schema(
        summary="Create Visit",
        description="Create a new OPD visit (Receptionist, Doctor, Admin)",
        tags=['OPD - Visits']
    ),
    update=extend_schema(
        summary="Update Visit",
        description="Update visit details (Receptionist, Doctor, Admin)",
        tags=['OPD - Visits']
    ),
    partial_update=extend_schema(
        summary="Partial Update Visit",
        description="Partially update visit details",
        tags=['OPD - Visits']
    )
)
class VisitViewSet(viewsets.ModelViewSet):
    """
    OPD Visit Management
    
    Handles patient visits, queue management, and visit workflow.
    Uses Django model permissions for access control.
    """
    queryset = Visit.objects.select_related(
        'patient', 'doctor', 'appointment', 'referred_by', 'created_by'
    ).prefetch_related(
        'procedure_bills', 'findings', 'attachments'
    )
    permission_classes = [IsAuthenticated, ActionPermissions]
    permission_model_name = 'visit'
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['patient', 'doctor', 'status', 'payment_status', 'visit_type', 'visit_date']
    search_fields = ['visit_number', 'patient__first_name', 'patient__last_name']
    ordering_fields = ['visit_date', 'entry_time', 'queue_position', 'total_amount']
    ordering = ['-visit_date', '-entry_time']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return VisitListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return VisitCreateUpdateSerializer
        return VisitDetailSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions and role"""
        queryset = super().get_queryset()
        user = self.request.user
        
        # Patients can only see their own visits
        if user.groups.filter(name='Patient').exists():
            if hasattr(user, 'patient_profile'):
                queryset = queryset.filter(patient=user.patient_profile)
            else:
                queryset = queryset.none()
        
        # Doctors can see their assigned visits
        elif user.groups.filter(name='Doctor').exists():
            if hasattr(user, 'doctor_profile'):
                queryset = queryset.filter(doctor=user.doctor_profile)
        
        return queryset
    
    @extend_schema(
        summary="Get Today's Visits",
        description="Get all visits for today with queue information",
        tags=['OPD - Visits']
    )
    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's visits"""
        today = date.today()
        visits = self.get_queryset().filter(visit_date=today)
        
        serializer = VisitListSerializer(visits, many=True)
        return Response({
            'success': True,
            'count': visits.count(),
            'data': serializer.data
        })
    
    @extend_schema(
        summary="Get Queue Status",
        description="Get current queue status grouped by patient status",
        tags=['OPD - Visits']
    )
    @action(detail=False, methods=['get'])
    def queue(self, request):
        """Get current queue status grouped by status"""
        today = date.today()
        
        # Get all today's active visits
        queryset = self.get_queryset().filter(visit_date=today)
        
        # Group by status
        waiting = queryset.filter(status='waiting').order_by('entry_time')
        called = queryset.filter(status='called').order_by('entry_time')
        in_consultation = queryset.filter(status='in_consultation').order_by('entry_time')
        
        return Response({
            'success': True,
            'data': {
                'waiting': VisitListSerializer(waiting, many=True).data,
                'called': VisitListSerializer(called, many=True).data,
                'in_consultation': VisitListSerializer(in_consultation, many=True).data,
            }
        })
    
    @extend_schema(
        summary="Call Next Patient",
        description="Call the next patient in queue for a specific doctor",
        parameters=[
            OpenApiParameter(name='doctor_id', type=int, required=True)
        ],
        tags=['OPD - Visits']
    )
    @action(detail=False, methods=['post'])
    def call_next(self, request):
        """Call next patient in queue"""
        doctor_id = request.data.get('doctor_id')
        if not doctor_id:
            return Response(
                {'success': False, 'error': 'doctor_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get next waiting patient
        today = date.today()
        next_visit = self.get_queryset().filter(
            visit_date=today,
            status='waiting'
        ).order_by('entry_time').first()
        
        if not next_visit:
            return Response({
                'success': False,
                'message': 'No patients in queue'
            })
        
        # Update visit status
        next_visit.status = 'called'
        next_visit.doctor_id = doctor_id
        next_visit.consultation_start_time = timezone.now()
        next_visit.save()
        
        serializer = VisitDetailSerializer(next_visit)
        return Response({
            'success': True,
            'message': 'Patient called',
            'data': serializer.data
        })
    
    @extend_schema(
        summary="Complete Visit",
        description="Mark visit as completed",
        tags=['OPD - Visits']
    )
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Complete a visit"""
        visit = self.get_object()
        
        if visit.status == 'completed':
            return Response({
                'success': False,
                'message': 'Visit already completed'
            })
        
        visit.status = 'completed'
        visit.consultation_end_time = timezone.now()
        visit.save()
        
        # Update patient's last visit date
        visit.patient.last_visit_date = timezone.now()
        visit.patient.total_visits = F('total_visits') + 1
        visit.patient.save()
        
        serializer = VisitDetailSerializer(visit)
        return Response({
            'success': True,
            'message': 'Visit completed',
            'data': serializer.data
        })
    
    @extend_schema(
        summary="Get Visit Statistics",
        description="Get statistics for visits (daily, weekly, monthly)",
        parameters=[
            OpenApiParameter(name='period', type=str, description='day, week, month')
        ],
        tags=['OPD - Visits']
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get visit statistics"""
        period = request.query_params.get('period', 'day')
        today = date.today()
        
        if period == 'day':
            start_date = today
        elif period == 'week':
            start_date = today - timedelta(days=7)
        elif period == 'month':
            start_date = today - timedelta(days=30)
        else:
            start_date = today
        
        visits = self.get_queryset().filter(visit_date__gte=start_date)
        
        stats = {
            'total_visits': visits.count(),
            'by_status': visits.values('status').annotate(count=Count('id')),
            'by_type': visits.values('visit_type').annotate(count=Count('id')),
            'total_revenue': visits.aggregate(Sum('total_amount'))['total_amount__sum'] or 0,
            'paid_revenue': visits.filter(payment_status='paid').aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0,
            'pending_amount': visits.aggregate(Sum('balance_amount'))['balance_amount__sum'] or 0,
        }
        
        return Response({
            'success': True,
            'period': period,
            'data': stats
        })


# ============================================================================
# OPD BILL VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List OPD Bills",
        description="Get paginated list of OPD bills with filtering",
        tags=['OPD - Bills']
    ),
    retrieve=extend_schema(
        summary="Get Bill Details",
        description="Retrieve detailed OPD bill information",
        tags=['OPD - Bills']
    ),
    create=extend_schema(
        summary="Create OPD Bill",
        description="Create a new OPD consultation bill",
        tags=['OPD - Bills']
    )
)
class OPDBillViewSet(viewsets.ModelViewSet):
    """
    OPD Bill Management
    
    Handles OPD consultation billing.
    Uses Django model permissions for access control.
    """
    queryset = OPDBill.objects.select_related(
        'visit__patient', 'doctor', 'billed_by'
    )
    permission_classes = [IsAuthenticated, ActionPermissions]
    permission_model_name = 'opdbill'
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['doctor', 'payment_status', 'opd_type', 'charge_type']
    search_fields = ['bill_number', 'visit__visit_number', 'visit__patient__first_name']
    ordering_fields = ['bill_date', 'total_amount', 'payment_status']
    ordering = ['-bill_date']
    
    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return OPDBillListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return OPDBillCreateUpdateSerializer
        return OPDBillDetailSerializer
    
    @extend_schema(
        summary="Record Payment",
        description="Record a payment for an OPD bill",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'amount': {'type': 'number'},
                    'payment_mode': {'type': 'string'},
                    'payment_details': {'type': 'object'}
                }
            }
        },
        tags=['OPD - Bills']
    )
    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        """Record payment for a bill"""
        bill = self.get_object()
        
        amount = request.data.get('amount')
        payment_mode = request.data.get('payment_mode', 'cash')
        payment_details = request.data.get('payment_details', {})
        
        if not amount:
            return Response(
                {'success': False, 'error': 'Amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Record payment
        bill.record_payment(amount, payment_mode, payment_details)
        
        serializer = OPDBillDetailSerializer(bill)
        return Response({
            'success': True,
            'message': 'Payment recorded',
            'data': serializer.data
        })


# ============================================================================
# PROCEDURE MASTER VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Procedure Masters",
        description="Get list of available procedures and tests",
        tags=['OPD - Procedures']
    ),
    retrieve=extend_schema(
        summary="Get Procedure Details",
        description="Retrieve procedure master details",
        tags=['OPD - Procedures']
    ),
    create=extend_schema(
        summary="Create Procedure Master",
        description="Create a new procedure/test (Admin only)",
        tags=['OPD - Procedures']
    )
)
class ProcedureMasterViewSet(viewsets.ModelViewSet):
    """
    Procedure Master Management
    
    Manages procedure and test master data.
    Uses Django model permissions for access control.
    """
    queryset = ProcedureMaster.objects.all()
    permission_classes = [IsAuthenticated, ActionPermissions]
    permission_model_name = 'proceduremaster'
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'category', 'default_charge']
    ordering = ['category', 'name']
    
    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ProcedureMasterListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProcedureMasterCreateUpdateSerializer
        return ProcedureMasterDetailSerializer
    
    def get_queryset(self):
        """Filter active procedures by default"""
        queryset = super().get_queryset()
        
        # Show only active procedures unless explicitly requested
        show_inactive = self.request.query_params.get('show_inactive', 'false')
        if show_inactive.lower() != 'true':
            queryset = queryset.filter(is_active=True)
        
        return queryset


# ============================================================================
# PROCEDURE PACKAGE VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Procedure Packages",
        description="Get list of procedure packages with discounts",
        tags=['OPD - Procedures']
    ),
    retrieve=extend_schema(
        summary="Get Package Details",
        description="Retrieve package details with included procedures",
        tags=['OPD - Procedures']
    ),
    create=extend_schema(
        summary="Create Package",
        description="Create a new procedure package (Admin only)",
        tags=['OPD - Procedures']
    )
)
class ProcedurePackageViewSet(viewsets.ModelViewSet):
    """
    Procedure Package Management
    
    Manages bundled procedures with discounted pricing.
    Uses Django model permissions for access control.
    """
    queryset = ProcedurePackage.objects.prefetch_related('procedures')
    permission_classes = [IsAuthenticated, ActionPermissions]
    permission_model_name = 'procedurepackage'
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'discounted_charge']
    ordering = ['name']
    
    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ProcedurePackageListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProcedurePackageCreateUpdateSerializer
        return ProcedurePackageDetailSerializer


# ============================================================================
# PROCEDURE BILL VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Procedure Bills",
        description="Get list of procedure/investigation bills",
        tags=['OPD - Bills']
    ),
    retrieve=extend_schema(
        summary="Get Procedure Bill Details",
        description="Retrieve procedure bill with line items",
        tags=['OPD - Bills']
    ),
    create=extend_schema(
        summary="Create Procedure Bill",
        description="Create a new procedure bill with items",
        tags=['OPD - Bills']
    )
)
class ProcedureBillViewSet(viewsets.ModelViewSet):
    """
    Procedure Bill Management
    
    Handles billing for procedures and investigations.
    Uses Django model permissions for access control.
    """
    queryset = ProcedureBill.objects.select_related(
        'visit__patient', 'doctor', 'billed_by'
    ).prefetch_related('items__procedure')
    permission_classes = [IsAuthenticated, ActionPermissions]
    permission_model_name = 'procedurebill'
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['doctor', 'payment_status', 'bill_type']
    search_fields = ['bill_number', 'visit__visit_number']
    ordering_fields = ['bill_date', 'total_amount']
    ordering = ['-bill_date']
    
    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ProcedureBillListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProcedureBillCreateUpdateSerializer
        return ProcedureBillDetailSerializer
    
    @extend_schema(
        summary="Record Payment",
        description="Record a payment for a procedure bill",
        tags=['OPD - Bills']
    )
    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        """Record payment for a procedure bill"""
        bill = self.get_object()
        
        amount = request.data.get('amount')
        payment_mode = request.data.get('payment_mode', 'cash')
        payment_details = request.data.get('payment_details', {})
        
        if not amount:
            return Response(
                {'success': False, 'error': 'Amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Record payment
        bill.record_payment(amount, payment_mode, payment_details)
        
        serializer = ProcedureBillDetailSerializer(bill)
        return Response({
            'success': True,
            'message': 'Payment recorded',
            'data': serializer.data
        })


# ============================================================================
# CLINICAL NOTE VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Clinical Notes",
        description="Get list of clinical notes",
        tags=['OPD - Clinical']
    ),
    retrieve=extend_schema(
        summary="Get Clinical Note",
        description="Retrieve detailed clinical documentation",
        tags=['OPD - Clinical']
    ),
    create=extend_schema(
        summary="Create Clinical Note",
        description="Create clinical documentation for a visit (Doctor, Admin)",
        tags=['OPD - Clinical']
    )
)
class ClinicalNoteViewSet(viewsets.ModelViewSet):
    """
    Clinical Note Management
    
    Manages clinical documentation and medical records.
    Uses Django model permissions for access control.
    """
    queryset = ClinicalNote.objects.select_related(
        'visit__patient', 'referred_doctor', 'created_by'
    )
    permission_classes = [IsAuthenticated, ActionPermissions]
    permission_model_name = 'clinicalnote'
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['visit__patient', 'referred_doctor']
    search_fields = ['visit__visit_number', 'diagnosis', 'present_complaints']
    ordering_fields = ['note_date']
    ordering = ['-note_date']
    
    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return ClinicalNoteListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ClinicalNoteCreateUpdateSerializer
        return ClinicalNoteDetailSerializer
    
    def get_queryset(self):
        """Filter by doctor if not admin"""
        queryset = super().get_queryset()
        user = self.request.user
        
        # Doctors can only see their own clinical notes
        if user.groups.filter(name='Doctor').exists():
            if hasattr(user, 'doctor_profile'):
                queryset = queryset.filter(
                    visit__doctor=user.doctor_profile
                )
        
        # Patients can see their own clinical notes
        elif user.groups.filter(name='Patient').exists():
            if hasattr(user, 'patient_profile'):
                queryset = queryset.filter(
                    visit__patient=user.patient_profile
                )
        
        return queryset


# ============================================================================
# VISIT FINDING VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Visit Findings",
        description="Get list of physical examination findings",
        tags=['OPD - Clinical']
    ),
    retrieve=extend_schema(
        summary="Get Finding Details",
        description="Retrieve detailed examination findings",
        tags=['OPD - Clinical']
    ),
    create=extend_schema(
        summary="Record Findings",
        description="Record physical examination findings (Nurse, Doctor, Admin)",
        tags=['OPD - Clinical']
    )
)
class VisitFindingViewSet(viewsets.ModelViewSet):
    """
    Visit Finding Management
    
    Manages physical examination and vital signs.
    Uses Django model permissions for access control.
    """
    queryset = VisitFinding.objects.select_related(
        'visit__patient', 'recorded_by'
    )
    permission_classes = [IsAuthenticated, ActionPermissions]
    permission_model_name = 'visitfinding'
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['visit', 'finding_type']
    search_fields = ['visit__visit_number', 'visit__patient__first_name']
    ordering_fields = ['finding_date']
    ordering = ['-finding_date']
    
    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return VisitFindingListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return VisitFindingCreateUpdateSerializer
        return VisitFindingDetailSerializer


# ============================================================================
# VISIT ATTACHMENT VIEWSET
# ============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List Visit Attachments",
        description="Get list of medical documents and files",
        tags=['OPD - Attachments']
    ),
    retrieve=extend_schema(
        summary="Get Attachment Details",
        description="Retrieve attachment details",
        tags=['OPD - Attachments']
    ),
    create=extend_schema(
        summary="Upload Attachment",
        description="Upload medical document or file",
        tags=['OPD - Attachments']
    )
)
class VisitAttachmentViewSet(viewsets.ModelViewSet):
    """
    Visit Attachment Management

    Manages medical documents and file uploads.
    Uses Django model permissions for access control.
    """
    queryset = VisitAttachment.objects.select_related(
        'visit__patient', 'uploaded_by'
    )
    permission_classes = [IsAuthenticated, ActionPermissions]
    permission_model_name = 'visitattachment'
    parser_classes = [MultiPartParser, FormParser]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['visit', 'file_type']
    search_fields = ['visit__visit_number', 'file_name', 'description']
    ordering_fields = ['uploaded_at']
    ordering = ['-uploaded_at']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return VisitAttachmentListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return VisitAttachmentCreateUpdateSerializer
        return VisitAttachmentDetailSerializer


# ============================================================================
# CLINICAL NOTE TEMPLATE VIEWSETS
# ============================================================================


@extend_schema_view(
    list=extend_schema(
        summary="List Template Groups",
        description="Get list of clinical note template groups",
        tags=['Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Group Details",
        description="Retrieve template group details",
        tags=['Clinical Templates']
    )
)
class ClinicalNoteTemplateGroupViewSet(viewsets.ModelViewSet):
    """Template Group Management."""

    queryset = ClinicalNoteTemplateGroup.objects.prefetch_related('templates')
    serializer_class = ClinicalNoteTemplateGroupSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['display_order', 'name']
    ordering = ['display_order', 'name']


@extend_schema_view(
    list=extend_schema(
        summary="List Template Fields",
        description="Get list of template fields",
        tags=['Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Field Details",
        description="Retrieve field details with options",
        tags=['Clinical Templates']
    )
)
class ClinicalNoteTemplateFieldViewSet(viewsets.ModelViewSet):
    """Template Field Management."""

    queryset = ClinicalNoteTemplateField.objects.select_related('template').prefetch_related('options')
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['template', 'field_type', 'is_required', 'is_active']
    search_fields = ['field_name', 'field_label']
    ordering_fields = ['display_order', 'field_label']
    ordering = ['template', 'display_order']

    def get_serializer_class(self):
        """Return appropriate serializer."""
        if self.action == 'list':
            return ClinicalNoteTemplateFieldListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ClinicalNoteTemplateFieldCreateUpdateSerializer
        return ClinicalNoteTemplateFieldDetailSerializer


@extend_schema_view(
    list=extend_schema(
        summary="List Clinical Note Templates",
        description="Get list of available clinical note templates",
        tags=['Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Template Details",
        description="Retrieve template with all fields and options",
        tags=['Clinical Templates']
    )
)
class ClinicalNoteTemplateViewSet(viewsets.ModelViewSet):
    """Clinical Note Template Management."""

    queryset = ClinicalNoteTemplate.objects.select_related('group').prefetch_related(
        'fields__options',
        'specialties'
    )
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['group', 'is_active']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['display_order', 'name']
    ordering = ['display_order', 'name']

    def get_serializer_class(self):
        """Return appropriate serializer."""
        if self.action == 'list':
            return ClinicalNoteTemplateListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ClinicalNoteTemplateCreateUpdateSerializer
        return ClinicalNoteTemplateDetailSerializer

    @extend_schema(
        summary="Get Template by Specialty",
        description="Get templates relevant to a specific specialty",
        parameters=[
            OpenApiParameter(name='specialty_id', type=int, required=True)
        ],
        tags=['Clinical Templates']
    )
    @action(detail=False, methods=['get'])
    def by_specialty(self, request):
        """Get templates by specialty."""
        specialty_id = request.query_params.get('specialty_id')

        if not specialty_id:
            return Response(
                {'success': False, 'error': 'specialty_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        templates = self.get_queryset().filter(
            specialties__id=specialty_id,
            is_active=True
        )

        serializer = ClinicalNoteTemplateListSerializer(templates, many=True)
        return Response({
            'success': True,
            'count': templates.count(),
            'data': serializer.data
        })


@extend_schema_view(
    list=extend_schema(
        summary="List Template Responses",
        description="Get list of filled clinical note templates",
        tags=['Clinical Templates']
    ),
    retrieve=extend_schema(
        summary="Get Response Details",
        description="Retrieve complete template response with all field values",
        tags=['Clinical Templates']
    ),
    create=extend_schema(
        summary="Create Template Response",
        description="Fill in a clinical note template for a visit",
        tags=['Clinical Templates']
    )
)
class ClinicalNoteTemplateResponseViewSet(viewsets.ModelViewSet):
    """Template Response Management."""

    queryset = ClinicalNoteTemplateResponse.objects.select_related(
        'visit__patient',
        'template'
    ).prefetch_related(
        'field_responses__field__options',
        'field_responses__selected_options'
    )
    permission_classes = [IsAuthenticated, ActionPermissions]
    permission_model_name = 'clinicalnotetemplate response'

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['visit', 'template', 'status']
    search_fields = ['visit__visit_number', 'visit__patient__first_name']
    ordering_fields = ['response_date', 'status']
    ordering = ['-response_date']

    def get_serializer_class(self):
        """Return appropriate serializer."""
        if self.action == 'list':
            return ClinicalNoteTemplateResponseListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ClinicalNoteTemplateResponseCreateUpdateSerializer
        return ClinicalNoteTemplateResponseDetailSerializer

    def get_queryset(self):
        """Filter by user role."""
        queryset = super().get_queryset()
        user = self.request.user

        # Doctors can see their patients' responses
        if user.groups.filter(name='Doctor').exists():
            if hasattr(user, 'doctor_profile'):
                queryset = queryset.filter(
                    visit__doctor=user.doctor_profile
                )

        # Patients can see their own responses
        elif user.groups.filter(name='Patient').exists():
            if hasattr(user, 'patient_profile'):
                queryset = queryset.filter(
                    visit__patient=user.patient_profile
                )

        return queryset

    @extend_schema(
        summary="Mark as Reviewed",
        description="Mark a template response as reviewed",
        tags=['Clinical Templates']
    )
    @action(detail=True, methods=['post'])
    def mark_reviewed(self, request, pk=None):
        """Mark response as reviewed."""
        response = self.get_object()

        response.status = 'reviewed'
        response.reviewed_by_id = request.user.id
        response.reviewed_at = timezone.now()
        response.save()

        serializer = ClinicalNoteTemplateResponseDetailSerializer(response)
        return Response({
            'success': True,
            'message': 'Response marked as reviewed',
            'data': serializer.data
        })

    @extend_schema(
        summary="Get Visit Templates",
        description="Get all template responses for a specific visit",
        tags=['Clinical Templates']
    )
    @action(detail=False, methods=['get'])
    def by_visit(self, request):
        """Get all template responses for a visit."""
        visit_id = request.query_params.get('visit_id')

        if not visit_id:
            return Response(
                {'success': False, 'error': 'visit_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        responses = self.get_queryset().filter(visit_id=visit_id)
        serializer = ClinicalNoteTemplateResponseListSerializer(responses, many=True)

        return Response({
            'success': True,
            'count': responses.count(),
            'data': serializer.data
        })