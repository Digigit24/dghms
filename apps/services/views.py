from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend

from common.drf_auth import HMSPermission

from .models import (
    ServiceCategory,
    DiagnosticTest,
    NursingCarePackage,
    HomeHealthcareService
)
from .serializers import (
    ServiceCategorySerializer,
    DiagnosticTestSerializer,
    NursingCarePackageSerializer,
    HomeHealthcareServiceSerializer
)


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    """Service category management"""
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [HMSPermission]
    hms_module = 'services'

    action_permission_map = {
        'list': 'view_services',
        'retrieve': 'view_services',
        'create': 'create_service',
        'update': 'edit_service',
        'partial_update': 'edit_service',
        'destroy': 'delete_service',
    }
    filter_backends = [
        DjangoFilterBackend, 
        filters.SearchFilter, 
        filters.OrderingFilter
    ]
    filterset_fields = ['type', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']


class DiagnosticTestViewSet(viewsets.ModelViewSet):
    """Diagnostic test management"""
    queryset = DiagnosticTest.objects.select_related('category')
    serializer_class = DiagnosticTestSerializer
    permission_classes = [HMSPermission]
    hms_module = 'services'

    action_permission_map = {
        'list': 'view_services',
        'retrieve': 'view_services',
        'create': 'create_service',
        'update': 'edit_service',
        'partial_update': 'edit_service',
        'destroy': 'delete_service',
    }
    filter_backends = [
        DjangoFilterBackend, 
        filters.SearchFilter, 
        filters.OrderingFilter
    ]
    filterset_fields = [
        'category', 'sample_type', 
        'is_active', 'is_home_collection', 
        'reporting_type'
    ]
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'base_price', 'created_at']


class NursingCarePackageViewSet(viewsets.ModelViewSet):
    """Nursing care package management"""
    queryset = NursingCarePackage.objects.select_related('category')
    serializer_class = NursingCarePackageSerializer
    permission_classes = [HMSPermission]
    hms_module = 'services'

    action_permission_map = {
        'list': 'view_services',
        'retrieve': 'view_services',
        'create': 'create_service',
        'update': 'edit_service',
        'partial_update': 'edit_service',
        'destroy': 'delete_service',
    }
    filter_backends = [
        DjangoFilterBackend, 
        filters.SearchFilter, 
        filters.OrderingFilter
    ]
    filterset_fields = [
        'category', 'package_type', 
        'is_active', 'target_group'
    ]
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'base_price', 'created_at']


class HomeHealthcareServiceViewSet(viewsets.ModelViewSet):
    """Home healthcare service management"""
    queryset = HomeHealthcareService.objects.select_related('category')
    serializer_class = HomeHealthcareServiceSerializer
    permission_classes = [HMSPermission]
    hms_module = 'services'

    action_permission_map = {
        'list': 'view_services',
        'retrieve': 'view_services',
        'create': 'create_service',
        'update': 'edit_service',
        'partial_update': 'edit_service',
        'destroy': 'delete_service',
    }
    filter_backends = [
        DjangoFilterBackend, 
        filters.SearchFilter, 
        filters.OrderingFilter
    ]
    filterset_fields = [
        'category', 'service_type', 
        'is_active', 'staff_type_required'
    ]
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'base_price', 'created_at']