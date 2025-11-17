from django.db.models import Avg
from django.utils.timezone import now
from django.db import transaction
from django.contrib.auth.models import Group

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, DjangoModelPermissions, AllowAny

from django_filters.rest_framework import DjangoFilterBackend

from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample, OpenApiResponse
)

from .models import DoctorProfile, Specialty, DoctorAvailability
from .serializers import (
    DoctorProfileListSerializer,
    DoctorProfileDetailSerializer,
    DoctorProfileCreateUpdateSerializer,
    DoctorRegistrationSerializer,  # NEW
    SpecialtySerializer,
    DoctorAvailabilitySerializer,
    DoctorAvailabilityCreateUpdateSerializer,
)


# =============================================================================
# SPECIALTIES VIEWSET
# =============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List specialties",
        description="Get list of all medical specialties (requires view_specialty permission).",
        parameters=[
            OpenApiParameter(name='is_active', type=bool, description='Filter by active status'),
            OpenApiParameter(name='department', type=str, description='Filter by department'),
            OpenApiParameter(name='search', type=str, description='Search by name, code, description'),
        ],
        tags=['Specialties'],
    ),
    retrieve=extend_schema(
        summary="Get specialty details",
        description="Retrieve a specialty by ID (requires view_specialty permission).",
        tags=['Specialties'],
    ),
    create=extend_schema(
        summary="Create specialty",
        description="Create a new medical specialty (requires add_specialty permission).",
        tags=['Specialties'],
    ),
    update=extend_schema(
        summary="Update specialty",
        description="Update a medical specialty (requires change_specialty permission).",
        tags=['Specialties'],
    ),
    partial_update=extend_schema(
        summary="Partial update specialty",
        description="Partially update a medical specialty (requires change_specialty permission).",
        tags=['Specialties'],
    ),
    destroy=extend_schema(
        summary="Delete specialty",
        description="Delete a medical specialty (requires delete_specialty permission). "
                    "Deletion is blocked if the specialty has active doctors.",
        tags=['Specialties'],
    ),
)
class SpecialtyViewSet(viewsets.ModelViewSet):
    """
    Medical Specialties Management
    
    Uses Django model permissions for access control.
    """
    queryset = Specialty.objects.all()
    serializer_class = SpecialtySerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'department']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({'success': True, 'data': serializer.data})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({'success': True, 'data': serializer.data})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        return Response(
            {
                'success': True,
                'message': 'Specialty created successfully',
                'data': serializer.data
            },
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response({
            'success': True,
            'message': 'Specialty updated successfully',
            'data': serializer.data
        })

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Business rule: prevent delete if specialty has active doctors
        if instance.doctors.filter(status='active').exists():
            return Response(
                {
                    'success': False,
                    'error': 'Cannot delete specialty with active doctors'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        self.perform_destroy(instance)
        return Response(
            {'success': True, 'message': 'Specialty deleted successfully'},
            status=status.HTTP_204_NO_CONTENT,
        )


# =============================================================================
# DOCTOR PROFILES VIEWSET
# =============================================================================

@extend_schema_view(
    list=extend_schema(
        summary="List doctors",
        description="List doctor profiles (requires view_doctorprofile permission).",
        parameters=[
            OpenApiParameter(name='specialty', type=str, description='Filter by specialty name (icontains)'),
            OpenApiParameter(name='status', type=str, description='Filter by status (active, on_leave, inactive)'),
            OpenApiParameter(name='available', type=bool, description='Filter active doctors only'),
            OpenApiParameter(name='city', type=str, description='Filter by user city'),
            OpenApiParameter(name='min_rating', type=float, description='Minimum average rating'),
            OpenApiParameter(name='min_fee', type=float, description='Minimum consultation fee'),
            OpenApiParameter(name='max_fee', type=float, description='Maximum consultation fee'),
            OpenApiParameter(name='search', type=str, description='Search by name, email, license, qualifications'),
        ],
        tags=['Doctors'],
    ),
    retrieve=extend_schema(
        summary="Get doctor details",
        description="Retrieve a doctor profile by ID (requires view_doctorprofile permission).",
        tags=['Doctors'],
    ),
    create=extend_schema(
        summary="Create doctor profile",
        description="Create a doctor profile (requires add_doctorprofile permission).",
        examples=[
            OpenApiExample(
                'Doctor Profile Creation',
                value={
                    'user_id': 2,
                    'medical_license_number': 'MED123456',
                    'license_issuing_authority': 'Medical Council of India',
                    'license_issue_date': '2020-01-01',
                    'license_expiry_date': '2030-01-01',
                    'qualifications': 'MBBS, MD',
                    'specialty_ids': [1, 2],
                    'years_of_experience': 5,
                    'consultation_fee': 500.00,
                    'consultation_duration': 30,
                    'status': 'active',
                    'is_available_online': True,
                    'is_available_offline': True,
                    'languages_spoken': 'English, Hindi, Marathi'
                },
                request_only=True,
            ),
        ],
        tags=['Doctors'],
    ),
    update=extend_schema(
        summary="Update doctor profile",
        description="Update doctor profile (requires change_doctorprofile permission, or owner can edit).",
        tags=['Doctors'],
    ),
    partial_update=extend_schema(
        summary="Partial update doctor profile",
        description="Partially update doctor profile (requires change_doctorprofile permission, or owner can edit).",
        tags=['Doctors'],
    ),
    destroy=extend_schema(
        summary="Deactivate doctor profile",
        description="Soft delete - set status to inactive (requires delete_doctorprofile permission).",
        tags=['Doctors'],
    ),
)
class DoctorProfileViewSet(viewsets.ModelViewSet):
    """
    Doctor Profile Management
    
    Uses Django model permissions with owner shortcuts:
    - Doctors can view/edit their own profile without global permissions
    - Others need appropriate model permissions
    """
    queryset = DoctorProfile.objects.prefetch_related(
        'specialties', 'availability'
    ).all()
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'is_available_online', 'is_available_offline']
    search_fields = [
        'user_id',
        'medical_license_number', 'qualifications',
    ]
    ordering_fields = ['created_at', 'consultation_fee', 'average_rating', 'years_of_experience']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return DoctorProfileListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return DoctorProfileCreateUpdateSerializer
        return DoctorProfileDetailSerializer

    def get_queryset(self):
        """Filter queryset by query params"""
        queryset = super().get_queryset()
        params = self.request.query_params

        # Filter by specialty
        specialty = params.get('specialty')
        if specialty:
            queryset = queryset.filter(specialties__name__icontains=specialty)

        # Filter by available (active status)
        available = params.get('available')
        if available and available.lower() == 'true':
            queryset = queryset.filter(status='active')

        # Filter by city (from user)
        city = params.get('city')
        if city:
            queryset = queryset.filter(user__city__icontains=city)

        # Filter by rating
        min_rating = params.get('min_rating')
        if min_rating:
            try:
                queryset = queryset.filter(average_rating__gte=float(min_rating))
            except ValueError:
                pass

        # Filter by fee range
        min_fee = params.get('min_fee')
        max_fee = params.get('max_fee')
        if min_fee:
            try:
                queryset = queryset.filter(consultation_fee__gte=float(min_fee))
            except ValueError:
                pass
        if max_fee:
            try:
                queryset = queryset.filter(consultation_fee__lte=float(max_fee))
            except ValueError:
                pass

        return queryset.distinct()

    def _is_owner(self, request, instance):
        """Check if request user is the owner of the profile"""
        return instance.user_id == request.user.id

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({'success': True, 'data': serializer.data})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({'success': True, 'data': serializer.data})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = serializer.save()
        
        return Response(
            {
                'success': True,
                'message': 'Doctor profile created successfully',
                'data': DoctorProfileDetailSerializer(doctor).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        """Allow update if user has permission OR is the owner"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Check permission: has change permission OR is owner
        has_perm = request.user.has_perm('doctors.change_doctorprofile')
        is_owner = self._is_owner(request, instance)

        if not has_perm and not is_owner:
            return Response(
                {'success': False, 'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        doctor = serializer.save()
        
        return Response({
            'success': True,
            'message': 'Doctor profile updated successfully',
            'data': DoctorProfileDetailSerializer(doctor).data
        })

    def destroy(self, request, *args, **kwargs):
        """Soft delete - set status to inactive"""
        instance = self.get_object()
        instance.status = 'inactive'
        instance.save(update_fields=['status'])
        
        return Response(
            {'success': True, 'message': 'Doctor profile deactivated successfully'},
            status=status.HTTP_204_NO_CONTENT
        )

    # =========================================================================
    # NEW: DEDICATED REGISTRATION ENDPOINT
    # =========================================================================

    @extend_schema(
        summary="Register doctor with user account",
        description="Register a new doctor with user account creation. Creates both User and DoctorProfile in one transaction.",
        request=DoctorRegistrationSerializer,
        responses={
            201: OpenApiResponse(
                description="Doctor registered successfully",
                response=DoctorProfileDetailSerializer
            ),
            400: OpenApiResponse(description="Validation error")
        },
        examples=[
            OpenApiExample(
                'Doctor Registration Example',
                value={
                    'email': 'doctor@hospital.com',
                    'username': 'doctor1',
                    'password': 'SecurePass123',
                    'password_confirm': 'SecurePass123',
                    'first_name': 'John',
                    'last_name': 'Doe',
                    'phone': '+919876543210',
                    'medical_license_number': 'MED123456',
                    'license_issuing_authority': 'Medical Council of India',
                    'license_issue_date': '2020-01-01',
                    'license_expiry_date': '2030-01-01',
                    'qualifications': 'MBBS, MD - Cardiology',
                    'specialty_ids': [1, 2],
                    'years_of_experience': 5,
                    'consultation_fee': 500.00,
                    'consultation_duration': 30,
                    'is_available_online': True,
                    'is_available_offline': True,
                    'languages_spoken': 'English, Hindi, Marathi'
                },
                request_only=True,
            ),
        ],
        tags=['Doctor Registration'],
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def register(self, request):
        """
        Register a new doctor with user account.
        Creates User + DoctorProfile in one transaction.
        """
        serializer = DoctorRegistrationSerializer(data=request.data)
        
        if serializer.is_valid():
            doctor = serializer.save()
            
            # Generate token for immediate login
            from rest_framework.authtoken.models import Token
            token, created = Token.objects.get_or_create(user=doctor.user)
            
            return Response({
                'success': True,
                'message': 'Doctor registered successfully',
                'data': {
                    'token': token.key,
                    'doctor': DoctorProfileDetailSerializer(doctor).data
                }
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # CUSTOM ACTIONS
    # =========================================================================

    @extend_schema(
        summary="Get doctor availability",
        description="Get weekly availability for a doctor.",
        responses={200: DoctorAvailabilitySerializer(many=True)},
        tags=['Doctors'],
    )
    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """Get doctor's availability schedule"""
        doctor = self.get_object()
        availability = doctor.availability.all()
        serializer = DoctorAvailabilitySerializer(availability, many=True)
        return Response({'success': True, 'data': serializer.data})

    @extend_schema(
        summary="Add availability slot",
        description="Add a new availability slot (requires add_doctoravailability permission or owner).",
        request=DoctorAvailabilityCreateUpdateSerializer,
        responses={
            201: DoctorAvailabilitySerializer,
            403: OpenApiResponse(description="Permission denied")
        },
        examples=[
            OpenApiExample(
                'Availability Example',
                value={
                    'day_of_week': 'monday',
                    'start_time': '09:00:00',
                    'end_time': '17:00:00',
                    'is_available': True,
                    'max_appointments': 20,
                },
                request_only=True,
            ),
        ],
        tags=['Doctors'],
    )
    @action(detail=True, methods=['post'])
    def set_availability(self, request, pk=None):
        """Add availability slot"""
        doctor = self.get_object()

        # Check permission: has add permission OR is owner
        has_perm = request.user.has_perm('doctors.add_doctoravailability')
        is_owner = self._is_owner(request, doctor)

        if not has_perm and not is_owner:
            return Response(
                {'success': False, 'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = DoctorAvailabilityCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(doctor=doctor)
            return Response(
                {
                    'success': True,
                    'message': 'Availability added successfully',
                    'data': serializer.data
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {'success': False, 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        summary="Doctor statistics",
        description="Basic doctor statistics (requires view_doctorprofile permission).",
        responses={200: OpenApiResponse(description="Statistics object")},
        tags=['Doctors'],
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get doctor statistics"""
        # Require view permission
        if not request.user.has_perm('doctors.view_doctorprofile'):
            return Response(
                {'success': False, 'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        total = DoctorProfile.objects.count()
        active = DoctorProfile.objects.filter(status='active').count()
        on_leave = DoctorProfile.objects.filter(status='on_leave').count()
        inactive = DoctorProfile.objects.filter(status='inactive').count()

        avg_stats = DoctorProfile.objects.aggregate(
            avg_rating=Avg('average_rating'),
            avg_experience=Avg('years_of_experience'),
            avg_fee=Avg('consultation_fee'),
        )

        return Response({
            'success': True,
            'data': {
                'total_doctors': total,
                'active_doctors': active,
                'on_leave_doctors': on_leave,
                'inactive_doctors': inactive,
                'average_rating': round(float(avg_stats['avg_rating'] or 0), 2),
                'average_experience': round(float(avg_stats['avg_experience'] or 0), 1),
                'average_consultation_fee': round(float(avg_stats['avg_fee'] or 0), 2),
                'generated_at': now().isoformat(),
            }
        })

    @extend_schema(
        summary="Activate doctor profile",
        description="Activate a doctor profile (requires change_doctorprofile permission).",
        request=None,
        responses={200: DoctorProfileDetailSerializer},
        tags=['Doctors'],
    )
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate doctor profile"""
        if not request.user.has_perm('doctors.change_doctorprofile'):
            return Response(
                {'success': False, 'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        doctor = self.get_object()
        doctor.status = 'active'
        doctor.save(update_fields=['status'])
        
        return Response({
            'success': True,
            'message': 'Doctor profile activated successfully',
            'data': DoctorProfileDetailSerializer(doctor).data,
        })

    @extend_schema(
        summary="Deactivate doctor profile",
        description="Deactivate a doctor profile (requires change_doctorprofile permission).",
        request=None,
        responses={200: DoctorProfileDetailSerializer},
        tags=['Doctors'],
    )
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate doctor profile"""
        if not request.user.has_perm('doctors.change_doctorprofile'):
            return Response(
                {'success': False, 'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        doctor = self.get_object()
        doctor.status = 'inactive'
        doctor.save(update_fields=['status'])
        
        return Response({
            'success': True,
            'message': 'Doctor profile deactivated successfully',
            'data': DoctorProfileDetailSerializer(doctor).data,
        })