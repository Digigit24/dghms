from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from common.drf_auth import HMSPermission, IsAuthenticated
from django.db.models import Q, Count, Avg
from django.utils import timezone
from django.db.models import F

# OpenAPI/Swagger documentation
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample,
    OpenApiResponse
)

from .models import Appointment, AppointmentType
from .serializers import (
    AppointmentListSerializer,
    AppointmentDetailSerializer,
    AppointmentCreateUpdateSerializer,
    AppointmentTypeSerializer
)

# -------------------------------------------------------------------
# HMS Permission Configuration for Appointments Module
# Uses JWT-based permissions from auth backend
# -------------------------------------------------------------------


# =========================
# Appointment Types
# =========================
@extend_schema_view(
    list=extend_schema(
        summary="List appointment types",
        description="Get list of medical appointment types",
        tags=['Appointment Types']
    ),
    create=extend_schema(
        summary="Create appointment type",
        description="Create a new medical appointment type (Admin only)",
        tags=['Appointment Types']
    ),
    retrieve=extend_schema(
        summary="Get appointment type details",
        description="Retrieve a specific appointment type",
        tags=['Appointment Types']
    ),
    update=extend_schema(
        summary="Update appointment type",
        description="Update an existing appointment type (Admin only)",
        tags=['Appointment Types']
    ),
    partial_update=extend_schema(
        summary="Partially update appointment type",
        description="Partially update an appointment type (Admin only)",
        tags=['Appointment Types']
    ),
    destroy=extend_schema(
        summary="Delete appointment type",
        description="Delete an appointment type (Admin only)",
        tags=['Appointment Types']
    )
)
class AppointmentTypeViewSet(viewsets.ModelViewSet):
    """
    Appointment Type management
    Uses JWT-based HMS permissions from the auth backend.
    """
    queryset = AppointmentType.objects.all()
    serializer_class = AppointmentTypeSerializer
    permission_classes = [HMSPermission]
    hms_module = 'hospital'  # Appointment types are part of hospital config

    # Custom action to permission mapping
    action_permission_map = {
        'list': 'view_config',
        'retrieve': 'view_config',
        'create': 'manage_appointment_types',
        'update': 'manage_appointment_types',
        'partial_update': 'manage_appointment_types',
        'destroy': 'manage_appointment_types',
    }


# =========================
# Appointments
# =========================
@extend_schema_view(
    list=extend_schema(
        summary="List appointments",
        description="Get list of appointments with extensive filtering",
        parameters=[
            OpenApiParameter(name='doctor_id', type=int, description='Filter by doctor'),
            OpenApiParameter(name='patient_id', type=int, description='Filter by patient'),
            OpenApiParameter(name='date_from', type=str, description='Appointments from date (YYYY-MM-DD)'),
            OpenApiParameter(name='date_to', type=str, description='Appointments to date (YYYY-MM-DD)'),
            OpenApiParameter(name='status', type=str, description='Comma-separated status values'),
            OpenApiParameter(name='priority', type=str, description='Comma-separated priority values'),
            
            OpenApiParameter(name='search', type=str, description='Search across complaint, symptoms, notes'),
        ],
        tags=['Appointments']
    ),
    create=extend_schema(
        summary="Create appointment",
        description="Book a new medical appointment",
        request=AppointmentCreateUpdateSerializer,
        tags=['Appointments']
    ),
    retrieve=extend_schema(
        summary="Get appointment details",
        description="Retrieve full details of a specific appointment",
        tags=['Appointments']
    ),
    update=extend_schema(
        summary="Update appointment",
        description="Update an existing appointment's details",
        tags=['Appointments']
    ),
    partial_update=extend_schema(
        summary="Partially update appointment",
        description="Partially update an existing appointment's details",
        tags=['Appointments']
    ),
    destroy=extend_schema(
        summary="Cancel appointment",
        description="Soft cancel an appointment",
        tags=['Appointments']
    )
)
class AppointmentViewSet(viewsets.ModelViewSet):
    """
    Comprehensive Appointment Management
    Uses JWT-based HMS permissions from the auth backend.
    """
    queryset = Appointment.objects.select_related(
        'patient', 'doctor', 'appointment_type',
        'created_by', 'cancelled_by', 'approved_by'
    ).prefetch_related('follow_ups')
    permission_classes = [HMSPermission]
    hms_module = 'appointments'  # Maps to permissions.hms.appointments in JWT

    # Custom action to permission mapping
    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'create',
        'update': 'edit',
        'partial_update': 'edit',
        'destroy': 'delete',
        'confirm': 'confirm',
        'cancel': 'cancel',
        'reschedule': 'reschedule',
        'check_in': 'check_in',
        'stats': 'view',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'doctor', 'patient', 'status',
        'priority',
        'appointment_date', 'is_follow_up'
    ]
    search_fields = ['chief_complaint', 'symptoms', 'notes', 'appointment_id']
    ordering_fields = [
        'appointment_date', 'appointment_time',
        'created_at', 'updated_at',
        'priority', 'status'
    ]
    ordering = ['-appointment_date', '-appointment_time']

    def get_serializer_class(self):
        """Return appropriate serializer"""
        if self.action == 'list':
            return AppointmentListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return AppointmentCreateUpdateSerializer
        return AppointmentDetailSerializer

    def get_queryset(self):
        """Custom queryset filtering"""
        queryset = super().get_queryset()

        # Users in patient/doctor role can only see their own appointments
        user = self.request.user
        if user.is_authenticated:
            if user.groups.filter(name='Patient').exists():
                queryset = queryset.filter(patient__user=user)
            elif user.groups.filter(name='Doctor').exists():
                queryset = queryset.filter(doctor__user=user)

        # Date range filtering
        params = self.request.query_params
        date_from = params.get('date_from')
        date_to = params.get('date_to')
        if date_from:
            queryset = queryset.filter(appointment_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(appointment_date__lte=date_to)

        # doctor_id / patient_id (since you documented them)
        doctor_id = params.get('doctor_id')
        patient_id = params.get('patient_id')
        if doctor_id:
            queryset = queryset.filter(doctor_id=doctor_id)
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)

        return queryset

    def destroy(self, request, *args, **kwargs):
        """Custom destroy to soft cancel"""
        instance = self.get_object()

        # Set cancellation details
        instance.status = Appointment.StatusChoices.CANCELLED
        instance.cancelled_at = timezone.now()
        instance.cancelled_by = request.user

        # Optional: Require/record cancellation reason
        cancellation_reason = request.data.get('cancellation_reason')
        if cancellation_reason:
            instance.cancellation_reason = cancellation_reason

        instance.save()

        serializer = self.get_serializer(instance)
        return Response({
            'success': True,
            'message': 'Appointment cancelled successfully',
            'data': serializer.data
        })

    @extend_schema(
        summary="Check-in to appointment",
        description="Mark appointment as checked-in",
        request=None,
        responses={200: AppointmentDetailSerializer},
        tags=['Appointments']
    )
    @action(detail=True, methods=['post'])
    def check_in(self, request, pk=None):
        """Check-in to an appointment"""
        appointment = self.get_object()

        if appointment.status in ['completed', 'cancelled', 'no_show']:
            return Response({
                'success': False,
                'error': f'Cannot check in {appointment.status} appointment'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if appointment.visit:
            return Response({
                'success': False,
                'error': 'Patient already checked in'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create Visit
        visit = Visit.objects.create(
            patient=appointment.patient,
            doctor=appointment.doctor,
            appointment=appointment,
            visit_type='follow_up' if appointment.is_follow_up else 'new',
            status='waiting',
            created_by=request.user
        )
        
        # Update appointment
        appointment.visit = visit
        appointment.check_in_time = timezone.now()
        appointment.status = 'checked_in'
        appointment.save()
        
        # Serialize response
        from apps.opd.serializers import VisitDetailSerializer
        visit_serializer = VisitDetailSerializer(visit)
        appt_serializer = self.get_serializer(appointment)
        
        return Response({
            'success': True,
            'message': 'Patient checked in successfully',
            'appointment': appt_serializer.data,
            'visit': visit_serializer.data
        })

    @extend_schema(
        summary="Start appointment consultation",
        description="Mark appointment as in progress",
        request=None,
        responses={200: AppointmentDetailSerializer},
        tags=['Appointments']
    )
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start the consultation"""
        appointment = self.get_object()

        # Update status and start time
        appointment.status = Appointment.StatusChoices.IN_PROGRESS
        appointment.actual_start_time = timezone.now().time()
        appointment.save()

        serializer = self.get_serializer(appointment)
        return Response({
            'success': True,
            'message': 'Consultation started successfully',
            'data': serializer.data
        })

    @extend_schema(
        summary="Complete appointment consultation",
        description="Mark appointment as completed",
        request=None,
        responses={200: AppointmentDetailSerializer},
        tags=['Appointments']
    )
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Complete the consultation"""
        appointment = self.get_object()

        # Update status and end time
        appointment.status = Appointment.StatusChoices.COMPLETED
        appointment.actual_end_time = timezone.now().time()
        appointment.save()

        serializer = self.get_serializer(appointment)
        return Response({
            'success': True,
            'message': 'Consultation completed successfully',
            'data': serializer.data
        })
    

    @extend_schema(
        summary="Get Today's Appointments",
        description="Get all appointments scheduled for today",
        tags=['Appointments']
    )
    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's appointments"""
        from datetime import date
        today = date.today()
        
        appointments = self.get_queryset().filter(
            appointment_date=today
        ).order_by('appointment_time')
        
        serializer = self.get_serializer(appointments, many=True)
        return Response({
            'success': True,
            'count': appointments.count(),
            'data': serializer.data
        })
    
    

    @extend_schema(
        summary="Get appointment statistics",
        description="Get statistical overview of appointments (Admin only)",
        responses={200: OpenApiResponse(description="Appointment statistics")},
        tags=['Appointments']
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get appointment statistics (Admin only)"""
        if not _in_any_group(request.user, ['Administrator']):
            return Response(
                {'success': False, 'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Total appointments
        total = Appointment.objects.count()

        # Appointments by status
        status_counts = Appointment.objects.values('status').annotate(count=Count('id'))
        status_breakdown = {item['status']: item['count'] for item in status_counts}

        # Appointments by priority
        priority_counts = Appointment.objects.values('priority').annotate(count=Count('id'))
        priority_breakdown = {item['priority']: item['count'] for item in priority_counts}

        # Average consultation fee
        avg_fee = Appointment.objects.aggregate(avg_fee=Avg('consultation_fee'))['avg_fee'] or 0

        # Paid vs Unpaid
        

        return Response({
            'success': True,
            'data': {
                'total_appointments': total,
                'status_breakdown': status_breakdown,
                'priority_breakdown': priority_breakdown,
                'average_consultation_fee': round(float(avg_fee), 2),
                
            }
        })
