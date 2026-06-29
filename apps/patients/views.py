import csv
import io
from collections import OrderedDict

from django.db.models import Q, Avg, Sum
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from common.drf_auth import HMSPermission, IsAuthenticated
from common.mixins import TenantViewSetMixin
from common.cache import CeliyoCache

from drf_spectacular.utils import (
    extend_schema, extend_schema_view,
    OpenApiParameter, OpenApiExample, OpenApiResponse
)

from .models import PatientProfile, PatientAllergy
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
# Export: all columns available for patient bulk export
# Each entry: column_key -> (header_label, value_getter_fn)
# --------------------------------------------------------------------------------------

EXPORTABLE_COLUMNS = OrderedDict([
    ('patient_id',                 ('Patient ID',                  lambda p: p.patient_id or '')),
    ('full_name',                  ('Full Name',                   lambda p: p.full_name or '')),
    ('first_name',                 ('First Name',                  lambda p: p.first_name or '')),
    ('middle_name',                ('Middle Name',                 lambda p: p.middle_name or '')),
    ('last_name',                  ('Last Name',                   lambda p: p.last_name or '')),
    ('date_of_birth',              ('Date of Birth',               lambda p: str(p.date_of_birth) if p.date_of_birth else '')),
    ('age',                        ('Age',                         lambda p: str(p.age) if p.age is not None else '')),
    ('gender',                     ('Gender',                      lambda p: p.get_gender_display() if p.gender else '')),
    ('mobile_primary',             ('Mobile (Primary)',            lambda p: p.mobile_primary or '')),
    ('mobile_secondary',           ('Mobile (Secondary)',          lambda p: p.mobile_secondary or '')),
    ('email',                      ('Email',                       lambda p: p.email or '')),
    ('address_line1',              ('Address Line 1',             lambda p: p.address_line1 or '')),
    ('address_line2',              ('Address Line 2',             lambda p: p.address_line2 or '')),
    ('city',                       ('City',                        lambda p: p.city or '')),
    ('state',                      ('State',                       lambda p: p.state or '')),
    ('country',                    ('Country',                     lambda p: p.country or '')),
    ('pincode',                    ('Pincode',                     lambda p: p.pincode or '')),
    ('full_address',               ('Full Address',                lambda p: p.full_address or '')),
    ('blood_group',                ('Blood Group',                 lambda p: p.blood_group or '')),
    ('height',                     ('Height (cm)',                 lambda p: str(p.height) if p.height is not None else '')),
    ('weight',                     ('Weight (kg)',                 lambda p: str(p.weight) if p.weight is not None else '')),
    ('bmi',                        ('BMI',                         lambda p: str(round(float(p.bmi), 2)) if p.bmi is not None else '')),
    ('marital_status',             ('Marital Status',              lambda p: p.get_marital_status_display() if p.marital_status else '')),
    ('occupation',                 ('Occupation',                  lambda p: p.occupation or '')),
    ('emergency_contact_name',     ('Emergency Contact Name',      lambda p: p.emergency_contact_name or '')),
    ('emergency_contact_phone',    ('Emergency Contact Phone',     lambda p: p.emergency_contact_phone or '')),
    ('emergency_contact_relation', ('Emergency Contact Relation',  lambda p: p.emergency_contact_relation or '')),
    ('insurance_provider',         ('Insurance Provider',          lambda p: p.insurance_provider or '')),
    ('insurance_policy_number',    ('Insurance Policy Number',     lambda p: p.insurance_policy_number or '')),
    ('insurance_expiry_date',      ('Insurance Expiry Date',       lambda p: str(p.insurance_expiry_date) if p.insurance_expiry_date else '')),
    ('is_insurance_valid',         ('Insurance Valid',             lambda p: 'Yes' if p.is_insurance_valid else 'No')),
    ('registration_date',          ('Registration Date',           lambda p: p.registration_date.strftime('%Y-%m-%d %H:%M') if p.registration_date else '')),
    ('last_visit_date',            ('Last Visit Date',             lambda p: p.last_visit_date.strftime('%Y-%m-%d %H:%M') if p.last_visit_date else '')),
    ('total_visits',               ('Total Visits',                lambda p: str(p.total_visits))),
    ('status',                     ('Status',                      lambda p: p.get_status_display() if p.status else '')),
    ('created_at',                 ('Registered On',               lambda p: p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else '')),
])


class _EchoBuffer:
    """Minimal write-only pseudo-buffer for streaming CSV rows."""
    def write(self, value):
        return value


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
        'record_vitals': 'edit',     # recording vitals = editing patient record
        'vitals': 'view',
        'add_allergy': 'edit',
        'allergies': 'view',
        'update_allergy': 'edit',
        'delete_allergy': 'edit',
        'update_visit': 'edit',
        'statistics': 'view',
        'activate': 'edit',
        'mark_deceased': 'edit',
        'export': 'export',
        'available_columns': 'view',
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
            try:
                qs = qs.filter(age__gte=int(age_min))
            except ValueError:
                pass
        if age_max:
            try:
                qs = qs.filter(age__lte=int(age_max))
            except ValueError:
                pass

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

    def perform_create(self, serializer):
        super().perform_create(serializer)
        CeliyoCache().delete_pattern(f"stats:patients:{self.request.tenant_id}")

    def perform_update(self, serializer):
        super().perform_update(serializer)
        CeliyoCache().delete_pattern(f"stats:patients:{self.request.tenant_id}")

    def perform_destroy(self, instance):
        tenant_id = self.request.tenant_id
        super().perform_destroy(instance)
        CeliyoCache().delete_pattern(f"stats:patients:{tenant_id}")

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
        cache = CeliyoCache()
        cached = cache.get(f"stats:patients:{request.tenant_id}")
        if cached is not None:
            return Response(cached)
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
        result = {'success': True, 'data': s.data}
        cache = CeliyoCache()
        cache.set(f"stats:patients:{request.tenant_id}", result, ttl=300)
        return Response(result)

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

    # =========================
    # Export
    # =========================

    @extend_schema(
        summary="List available export columns",
        description="Returns all column keys and their display labels that can be requested in the export endpoint.",
        responses={200: OpenApiResponse(description="Column list")},
        tags=['Patients'],
    )
    @action(detail=False, methods=['get'])
    def available_columns(self, request):
        data = [{'key': key, 'label': header} for key, (header, _) in EXPORTABLE_COLUMNS.items()]
        return Response({'success': True, 'data': data})

    @extend_schema(
        summary="Bulk export patients",
        description=(
            "Export all patients matching the given filters as a downloadable CSV or XLSX file.\n\n"
            "**Column selection** – pass a comma-separated list of column keys via `columns`. "
            "Omit the parameter to export every column. Call `available_columns` first to discover valid keys.\n\n"
            "**Filters** – all the same query parameters accepted by the patient list endpoint work here too."
        ),
        parameters=[
            OpenApiParameter(name='file_format', type=str, description='csv (default) or xlsx'),
            OpenApiParameter(name='columns',    type=str, description='Comma-separated column keys, e.g. patient_id,full_name,mobile_primary'),
            OpenApiParameter(name='status',     type=str, description='Filter by status'),
            OpenApiParameter(name='gender',     type=str, description='Filter by gender'),
            OpenApiParameter(name='blood_group',type=str, description='Filter by blood group'),
            OpenApiParameter(name='city',       type=str, description='Filter by city'),
            OpenApiParameter(name='age_min',    type=int, description='Minimum age'),
            OpenApiParameter(name='age_max',    type=int, description='Maximum age'),
            OpenApiParameter(name='has_insurance', type=bool, description='Filter by insurance status'),
            OpenApiParameter(name='date_from',  type=str, description='Registration date from (YYYY-MM-DD)'),
            OpenApiParameter(name='date_to',    type=str, description='Registration date to (YYYY-MM-DD)'),
            OpenApiParameter(name='search',     type=str, description='Search by name, patient ID, or phone'),
        ],
        tags=['Patients'],
    )
    @action(detail=False, methods=['get'])
    def export(self, request):
        import logging as _logging
        _logging.getLogger(__name__).warning(
            '[EXPORT DEBUG] export() called | action=%s | params=%s | user=%s',
            getattr(self, 'action', '?'), dict(request.query_params), getattr(request.user, 'email', '?')
        )
        export_format = request.query_params.get('file_format', 'csv').lower()
        if export_format not in ('csv', 'xlsx'):
            return Response(
                {'success': False, 'error': "file_format must be 'csv' or 'xlsx'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve requested columns
        columns_param = request.query_params.get('columns', '').strip()
        if columns_param:
            requested_keys = [k.strip() for k in columns_param.split(',') if k.strip()]
            invalid = [k for k in requested_keys if k not in EXPORTABLE_COLUMNS]
            if invalid:
                return Response(
                    {
                        'success': False,
                        'error': f'Unknown column(s): {invalid}',
                        'available_columns': list(EXPORTABLE_COLUMNS.keys()),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            selected = OrderedDict((k, EXPORTABLE_COLUMNS[k]) for k in requested_keys)
        else:
            selected = EXPORTABLE_COLUMNS

        # Build queryset: reuse all existing filters but skip prefetch (not needed here)
        qs = self.filter_queryset(self.get_queryset().prefetch_related(None))

        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f'patients_export_{timestamp}'

        if export_format == 'csv':
            return self._stream_csv(qs, selected, filename)
        return self._build_xlsx(qs, selected, filename)

    @staticmethod
    def _stream_csv(queryset, columns, filename):
        headers = [header for header, _ in columns.values()]
        getters = [getter for _, getter in columns.values()]

        def _rows():
            writer = csv.writer(_EchoBuffer())
            yield writer.writerow(headers)
            for patient in queryset.iterator(chunk_size=500):
                yield writer.writerow([getter(patient) for getter in getters])

        response = StreamingHttpResponse(_rows(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        return response

    @staticmethod
    def _build_xlsx(queryset, columns, filename):
        import openpyxl
        from openpyxl.styles import Font

        headers = [header for header, _ in columns.values()]
        getters = [getter for _, getter in columns.values()]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Patients'
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)

        for patient in queryset.iterator(chunk_size=500):
            ws.append([getter(patient) for getter in getters])

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
        return response
