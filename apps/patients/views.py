from django.db.models import Q, Avg, Sum
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.models import Group

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from common.drf_auth import HMSPermission, IsAuthenticated, AllowAny
from common.mixins import TenantViewSetMixin

from drf_spectacular.utils import (
    extend_schema, extend_schema_view,
    OpenApiParameter, OpenApiExample, OpenApiResponse
)

from .models import PatientProfile, PatientVitals, PatientAllergy
from .serializers import (
    PatientProfileListSerializer,
    PatientProfileDetailSerializer,
    PatientProfileCreateUpdateSerializer,
    PatientRegistrationSerializer,  # NEW
    PatientVitalsSerializer,
    PatientVitalsCreateUpdateSerializer,
    PatientAllergySerializer,
    PatientAllergyCreateUpdateSerializer,
    PatientStatisticsSerializer
)

# --------------------------------------------------------------------------------------
# HMS Permission Configuration for Patients Module
# Maps custom actions to HMS permission names from JWT payload
# --------------------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List patients",
        description="Get list of patient profiles with filtering, search and ordering.",
        parameters=[
            OpenApiParameter(name='status', type=str, description='Filter by status'),
            OpenApiParameter(name='gender', type=str, description='Filter by gender'),
            OpenApiParameter(name='blood_group', type=str, description='Filter by blood group'),
            OpenApiParameter(name='city', type=str, description='Filter by city'),
            OpenApiParameter(name='age_min', type=int, description='Minimum age'),
            OpenApiParameter(name='age_max', type=int, description='Maximum age'),
            OpenApiParameter(name='has_insurance', type=bool, description='Filter by insurance status'),
            OpenApiParameter(name='date_from', type=str, description='Registration date from (YYYY-MM-DD)'),
            OpenApiParameter(name='date_to', type=str, description='Registration date to (YYYY-MM-DD)'),
            OpenApiParameter(name='search', type=str, description='Search by name, patient ID, or phone'),
        ],
        tags=['Patients']
    ),
    retrieve=extend_schema(
        summary="Get patient details",
        description="Retrieve a complete patient profile with vitals and allergies.",
        tags=['Patients']
    ),
    create=extend_schema(
        summary="Register patient",
        description="Create a new patient profile (walk-in or registered user).",
        examples=[
            OpenApiExample(
                'Patient Registration Example',
                value={
                    'first_name': 'John',
                    'last_name': 'Doe',
                    'date_of_birth': '1990-01-15',
                    'gender': 'male',
                    'mobile_primary': '+919876543210',
                    'email': 'john.doe@example.com',
                    'address_line1': '123 Main Street',
                    'city': 'Mumbai',
                    'state': 'Maharashtra',
                    'country': 'India',
                    'pincode': '400001',
                    'blood_group': 'O+',
                    'height': 175.5,
                    'weight': 70.0,
                    'emergency_contact_name': 'Jane Doe',
                    'emergency_contact_phone': '+919876543211',
                    'emergency_contact_relation': 'Spouse'
                },
                request_only=True,
            ),
        ],
        tags=['Patients']
    ),
    update=extend_schema(
        summary="Update patient profile",
        description="Update patient profile information.",
        tags=['Patients']
    ),
    partial_update=extend_schema(
        summary="Partial update patient profile",
        description="Partially update patient profile.",
        tags=['Patients']
    ),
    destroy=extend_schema(
        summary="Deactivate patient profile",
        description="Soft delete - set status to inactive (Admin only).",
        tags=['Patients']
    ),
)
class PatientProfileViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Patient Profile Management: registration, profile CRUD, vitals, allergies, visits.
    Uses JWT-based HMS permissions from the auth backend.
    """
    queryset = PatientProfile.objects.all()
    permission_classes = [HMSPermission]
    hms_module = 'patients'  # Maps to permissions.hms.patients in JWT

    # Custom action to permission mapping
    action_permission_map = {
        'list': 'view',
        'retrieve': 'view',
        'create': 'create',
        'update': 'edit',
        'partial_update': 'edit',
        'destroy': 'delete',
        'record_vitals': 'view_vitals',
        'vitals': 'view_vitals',
        'add_allergy': 'manage_allergies',
        'allergies': 'view',
        'update_allergy': 'manage_allergies',
        'delete_allergy': 'manage_allergies',
        'update_visit': 'edit',
        'statistics': 'view',
        'activate': 'edit',
        'mark_deceased': 'edit',
        'export': 'export',
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'gender', 'blood_group', 'city', 'state']
    search_fields = ['patient_id', 'first_name', 'last_name', 'middle_name', 'mobile_primary', 'email']
    ordering_fields = ['registration_date', 'last_visit_date', 'age', 'total_visits', 'first_name', 'last_name']
    ordering = ['-registration_date']

    # ----- serializers -----
    def get_serializer_class(self):
        if self.action == 'list':
            return PatientProfileListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return PatientProfileCreateUpdateSerializer
        return PatientProfileDetailSerializer

    # ----- queryset scoping -----
    def get_queryset(self):
        # Get tenant-filtered queryset from TenantViewSetMixin
        qs = super().get_queryset().prefetch_related('vitals', 'allergies')
        user = self.request.user

        # Patients can only see their own profile
        if user.groups.filter(name='Patient').exists():
            if hasattr(user, 'patient_profile'):
                qs = qs.filter(id=user.patient_profile.id)
            else:
                return PatientProfile.objects.none()

        # age range
        age_min = self.request.query_params.get('age_min')
        age_max = self.request.query_params.get('age_max')
        if age_min:
            try: qs = qs.filter(age__gte=int(age_min))
            except ValueError: pass
        if age_max:
            try: qs = qs.filter(age__lte=int(age_max))
            except ValueError: pass

        # insurance
        has_insurance = self.request.query_params.get('has_insurance')
        if has_insurance:
            if has_insurance.lower() == 'true':
                qs = qs.filter(insurance_provider__isnull=False).exclude(insurance_provider='')
            else:
                qs = qs.filter(Q(insurance_provider__isnull=True) | Q(insurance_provider=''))

        # registration dates
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(registration_date__gte=date_from)
        if date_to:
            qs = qs.filter(registration_date__lte=date_to)

        return qs

    # ----- standard actions -----
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            s = self.get_serializer(page, many=True)
            return self.get_paginated_response(s.data)
        s = self.get_serializer(qs, many=True)
        return Response({'success': True, 'data': s.data})

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        # Patient self-view check
        if request.user.groups.filter(name='Patient').exists():
            if not hasattr(request.user, 'patient_profile') or obj.id != request.user.patient_profile.id:
                return Response({'success': False, 'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        s = self.get_serializer(obj)
        return Response({'success': True, 'data': s.data})

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data, context={'request': request})
        s.is_valid(raise_exception=True)
        patient = s.save()
        return Response(
            {'success': True, 'message': 'Patient registered successfully',
             'data': PatientProfileDetailSerializer(patient).data},
            status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        obj = self.get_object()
        # Patient self-edit check
        if request.user.groups.filter(name='Patient').exists():
            if not hasattr(request.user, 'patient_profile') or obj.id != request.user.patient_profile.id:
                return Response({'success': False, 'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        s = self.get_serializer(obj, data=request.data, partial=partial, context={'request': request})
        s.is_valid(raise_exception=True)
        patient = s.save()
        return Response({'success': True, 'message': 'Patient profile updated successfully',
                         'data': PatientProfileDetailSerializer(patient).data})

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.status = 'inactive'
        obj.save()
        return Response({'success': True, 'message': 'Patient profile deactivated successfully'},
                        status=status.HTTP_204_NO_CONTENT)

    # =========================================================================
    # NEW: DEDICATED REGISTRATION ENDPOINT
    # =========================================================================

    @extend_schema(
        summary="Register patient (with optional user account)",
        description="Register a new patient. Can create with user account (canLogin=true) or without (walk-in, canLogin=false).",
        request=PatientRegistrationSerializer,
        responses={
            201: OpenApiResponse(
                description="Patient registered successfully",
                response=PatientProfileDetailSerializer
            ),
            400: OpenApiResponse(description="Validation error")
        },
        examples=[
            OpenApiExample(
                'Patient Registration WITH User Account',
                value={
                    'can_login': True,
                    'email': 'patient@example.com',
                    'username': 'patient1',
                    'password': 'SecurePass123',
                    'password_confirm': 'SecurePass123',
                    'first_name': 'Jane',
                    'last_name': 'Smith',
                    'middle_name': 'Marie',
                    'date_of_birth': '1990-05-15',
                    'gender': 'female',
                    'mobile_primary': '+919876543210',
                    'mobile_secondary': '+919876543211',
                    'address_line1': '123 Main Street',
                    'address_line2': 'Apt 4B',
                    'city': 'Mumbai',
                    'state': 'Maharashtra',
                    'country': 'India',
                    'pincode': '400001',
                    'blood_group': 'O+',
                    'height': 165.5,
                    'weight': 58.0,
                    'marital_status': 'married',
                    'occupation': 'Software Engineer',
                    'emergency_contact_name': 'John Smith',
                    'emergency_contact_phone': '+919876543212',
                    'emergency_contact_relation': 'Spouse',
                    'insurance_provider': 'Star Health',
                    'insurance_policy_number': 'SH123456789',
                    'insurance_expiry_date': '2025-12-31'
                },
                request_only=True,
            ),
            OpenApiExample(
                'Walk-in Patient Registration WITHOUT User Account',
                value={
                    'can_login': False,
                    'first_name': 'Rajesh',
                    'last_name': 'Kumar',
                    'date_of_birth': '1985-03-20',
                    'gender': 'male',
                    'mobile_primary': '+919876543220',
                    'address_line1': '456 Park Road',
                    'city': 'Pune',
                    'state': 'Maharashtra',
                    'country': 'India',
                    'pincode': '411001',
                    'blood_group': 'B+',
                    'emergency_contact_name': 'Priya Kumar',
                    'emergency_contact_phone': '+919876543221',
                    'emergency_contact_relation': 'Wife'
                },
                request_only=True,
            ),
        ],
        tags=['Patient Registration'],
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def register(self, request):
        """
        Register a new patient with optional user account.
        - If can_login=true: Creates User + PatientProfile
        - If can_login=false: Creates PatientProfile only (walk-in)
        """
        serializer = PatientRegistrationSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            patient = serializer.save()
            
            response_data = {
                'success': True,
                'message': 'Patient registered successfully',
                'data': {
                    'patient': PatientProfileDetailSerializer(patient).data
                }
            }
            
            # If user was created, generate token
            if patient.user:
                from rest_framework.authtoken.models import Token
                token, created = Token.objects.get_or_create(user=patient.user)
                response_data['data']['token'] = token.key
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    # =========================
    # Custom Actions (Vitals)
    # =========================
    @extend_schema(
        summary="Record patient vitals",
        description="Record vital signs for a patient.",
        request=PatientVitalsCreateUpdateSerializer,
        responses={201: PatientVitalsSerializer, 400: OpenApiResponse(description="Validation error")},
        examples=[OpenApiExample('Vitals Example', value={
            'temperature': 98.6,
            'blood_pressure_systolic': 120,
            'blood_pressure_diastolic': 80,
            'heart_rate': 72,
            'respiratory_rate': 16,
            'oxygen_saturation': 98.5,
            'blood_glucose': 95.0,
            'notes': 'Normal vitals'
        }, request_only=True)],
        tags=['Vitals']
    )
    @action(detail=True, methods=['post'])
    def record_vitals(self, request, pk=None):
        patient = self.get_object()
        s = PatientVitalsCreateUpdateSerializer(data=request.data)
        if s.is_valid():
            s.save(patient=patient, recorded_by=request.user)
            return Response({'success': True, 'message': 'Vitals recorded successfully', 'data': s.data},
                            status=status.HTTP_201_CREATED)
        return Response({'success': False, 'errors': s.errors}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Get patient vitals history",
        description="Retrieve a patient's vital signs history.",
        parameters=[OpenApiParameter(name='limit', type=int, description='Number of records (default 10)')],
        responses={200: PatientVitalsSerializer(many=True)},
        tags=['Vitals']
    )
    @action(detail=True, methods=['get'])
    def vitals(self, request, pk=None):
        patient = self.get_object()
        limit = request.query_params.get('limit', 10)
        try:
            limit = int(limit)
        except ValueError:
            limit = 10
        items = patient.vitals.all()[:limit]
        s = PatientVitalsSerializer(items, many=True)
        return Response({'success': True, 'data': s.data})

    # =========================
    # Custom Actions (Allergies)
    # =========================
    @extend_schema(
        summary="Add patient allergy",
        description="Add a new allergy to a patient's record.",
        request=PatientAllergyCreateUpdateSerializer,
        responses={201: PatientAllergySerializer, 400: OpenApiResponse(description="Validation error")},
        examples=[OpenApiExample('Allergy Example', value={
            'allergy_type': 'drug',
            'allergen': 'Penicillin',
            'severity': 'severe',
            'symptoms': 'Skin rash, breathing difficulty',
            'treatment': 'Avoid penicillin-based medications',
            'is_active': True
        }, request_only=True)],
        tags=['Allergies']
    )
    @action(detail=True, methods=['post'])
    def add_allergy(self, request, pk=None):
        patient = self.get_object()
        s = PatientAllergyCreateUpdateSerializer(data=request.data)
        if s.is_valid():
            s.save(patient=patient, recorded_by=request.user)
            return Response({'success': True, 'message': 'Allergy added successfully', 'data': s.data},
                            status=status.HTTP_201_CREATED)
        return Response({'success': False, 'errors': s.errors}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Get patient allergies",
        description="Retrieve a patient's allergy records.",
        parameters=[OpenApiParameter(name='active_only', type=bool, description='Only active (default true)')],
        responses={200: PatientAllergySerializer(many=True)},
        tags=['Allergies']
    )
    @action(detail=True, methods=['get'])
    def allergies(self, request, pk=None):
        patient = self.get_object()
        active_only = request.query_params.get('active_only', 'true')
        qs = patient.allergies.all()
        if str(active_only).lower() == 'true':
            qs = qs.filter(is_active=True)
        s = PatientAllergySerializer(qs, many=True)
        return Response({'success': True, 'data': s.data})

    @extend_schema(
        summary="Update patient allergy",
        description="Update a specific allergy record.",
        request=PatientAllergyCreateUpdateSerializer,
        responses={200: PatientAllergySerializer, 404: OpenApiResponse(description="Allergy not found")},
        tags=['Allergies']
    )
    @action(detail=True, methods=['put', 'patch'], url_path='allergies/(?P<allergy_id>[^/.]+)')
    def update_allergy(self, request, pk=None, allergy_id=None):
        patient = self.get_object()
        try:
            allergy = patient.allergies.get(id=allergy_id)
        except PatientAllergy.DoesNotExist:
            return Response({'success': False, 'error': 'Allergy not found'}, status=status.HTTP_404_NOT_FOUND)

        partial = request.method == 'PATCH'
        s = PatientAllergyCreateUpdateSerializer(allergy, data=request.data, partial=partial)
        if s.is_valid():
            s.save()
            return Response({'success': True, 'message': 'Allergy updated successfully', 'data': s.data})
        return Response({'success': False, 'errors': s.errors}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Delete/deactivate patient allergy",
        description="Soft delete - set is_active to False.",
        responses={204: OpenApiResponse(description="Allergy deactivated"), 404: OpenApiResponse(description="Not found")},
        tags=['Allergies']
    )
    @action(detail=True, methods=['delete'], url_path='allergies/(?P<allergy_id>[^/.]+)')
    def delete_allergy(self, request, pk=None, allergy_id=None):
        patient = self.get_object()
        try:
            allergy = patient.allergies.get(id=allergy_id)
        except PatientAllergy.DoesNotExist:
            return Response({'success': False, 'error': 'Allergy not found'}, status=status.HTTP_404_NOT_FOUND)
        allergy.is_active = False
        allergy.save()
        return Response({'success': True, 'message': 'Allergy deactivated successfully'},
                        status=status.HTTP_204_NO_CONTENT)

    # =========================
    # Visits / Stats / Admin ops
    # =========================
    @extend_schema(
        summary="Record patient visit",
        description="Increment visit count and update last visit date.",
        request=None,
        responses={200: OpenApiResponse(description="Visit recorded")},
        tags=['Patients']
    )
    @action(detail=True, methods=['post'])
    def update_visit(self, request, pk=None):
        patient = self.get_object()
        patient.total_visits += 1
        patient.last_visit_date = timezone.now()
        patient.save()
        return Response({
            'success': True,
            'message': 'Visit recorded successfully',
            'data': {'total_visits': patient.total_visits, 'last_visit_date': patient.last_visit_date}
        })

    @extend_schema(
        summary="Get patient statistics",
        description="Statistical overview of all patients (Admin only).",
        responses={200: PatientStatisticsSerializer},
        tags=['Patients']
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        # Allow superadmins or Administrators
        is_superadmin = getattr(request.user, 'is_super_admin', False)
        is_administrator = request.user.groups.filter(name='Administrator').exists()

        if not (is_superadmin or is_administrator):
            return Response({'success': False, 'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        # Get base queryset filtered by tenant
        base_qs = PatientProfile.objects.all()
        if hasattr(request, 'tenant_id'):
            base_qs = base_qs.filter(tenant_id=request.tenant_id)

        total = base_qs.count()
        active = base_qs.filter(status='active').count()
        inactive = base_qs.filter(status='inactive').count()
        deceased = base_qs.filter(status='deceased').count()

        import datetime
        patients_with_insurance = base_qs.filter(
            insurance_provider__isnull=False,
            insurance_expiry_date__gte=datetime.date.today()
        ).count()
        avg_age = base_qs.aggregate(avg=Avg('age'))['avg'] or 0
        total_visits = base_qs.aggregate(total=Sum('total_visits'))['total'] or 0

        gender_dist = {label: base_qs.filter(gender=code).count()
                       for code, label in getattr(PatientProfile, 'GENDER_CHOICES', [])}

        blood_dist = {}
        for bg_code, _bg_label in getattr(PatientProfile, 'BLOOD_GROUP_CHOICES', []):
            c = base_qs.filter(blood_group=bg_code).count()
            if c > 0:
                blood_dist[bg_code] = c

        data = {
            'total_patients': total,
            'active_patients': active,
            'inactive_patients': inactive,
            'deceased_patients': deceased,
            'patients_with_insurance': patients_with_insurance,
            'average_age': round(avg_age, 1),
            'total_visits': total_visits,
            'gender_distribution': gender_dist,
            'blood_group_distribution': blood_dist
        }

        s = PatientStatisticsSerializer(data)
        return Response({'success': True, 'data': s.data})

    @extend_schema(
        summary="Activate patient profile",
        description="Activate a patient profile (Admin only).",
        request=None,
        responses={200: PatientProfileDetailSerializer},
        tags=['Patients']
    )
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        # Allow superadmins or Administrators
        is_superadmin = getattr(request.user, 'is_super_admin', False)
        is_administrator = request.user.groups.filter(name='Administrator').exists()

        if not (is_superadmin or is_administrator):
            return Response({'success': False, 'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        patient = self.get_object()
        patient.status = 'active'
        patient.save()
        return Response({'success': True, 'message': 'Patient profile activated successfully',
                         'data': PatientProfileDetailSerializer(patient).data})

    @extend_schema(
        summary="Mark patient as deceased",
        description="Mark a patient as deceased (Admin only).",
        request=None,
        responses={200: PatientProfileDetailSerializer},
        tags=['Patients']
    )
    @action(detail=True, methods=['post'])
    def mark_deceased(self, request, pk=None):
        # Allow superadmins or Administrators
        is_superadmin = getattr(request.user, 'is_super_admin', False)
        is_administrator = request.user.groups.filter(name='Administrator').exists()

        if not (is_superadmin or is_administrator):
            return Response({'success': False, 'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        patient = self.get_object()
        patient.status = 'deceased'
        patient.save()
        return Response({'success': True, 'message': 'Patient marked as deceased',
                         'data': PatientProfileDetailSerializer(patient).data})