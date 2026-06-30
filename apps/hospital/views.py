import structlog
from rest_framework import generics, status
from rest_framework.response import Response

from common.drf_auth import HMSPermission, AllowAny

from .models import Hospital
from .serializers import HospitalSerializer, HospitalUpdateSerializer

log = structlog.get_logger(__name__)


def _get_or_create_hospital(request) -> Hospital:
    """
    Return the tenant's Hospital singleton, auto-creating a skeleton record
    on first access so the Settings page always has something to display.

    Uses the authenticated tenant_id from the JWT so every tenant gets its
    own Hospital row (the model's singleton guard prevents duplicates per DB,
    but in production each tenant runs against its own schema/DB).
    """
    hospital = Hospital.objects.first()
    if hospital is not None:
        return hospital

    tenant_id = getattr(request, 'tenant_id', None)
    tenant_slug = getattr(request, 'tenant_slug', '') or ''

    # Build a human-readable default name from the slug ("city-hospital" → "City Hospital")
    default_name = tenant_slug.replace('-', ' ').replace('_', ' ').title() or 'Hospital'

    log.info(
        "hospital_config_auto_create",
        tenant_id=str(tenant_id) if tenant_id else None,
        default_name=default_name,
    )

    hospital = Hospital(
        tenant_id=tenant_id,
        name=default_name,
        type='hospital',
        email='admin@hospital.com',
        phone='0000000000',
        address='',
        city='',
        state='',
        country='India',
        pincode='000000',
        working_hours='24/7',
        has_emergency=True,
        has_pharmacy=True,
        has_laboratory=True,
    )
    # Bypass the singleton guard in Hospital.save() by calling Django's base
    # Model.save() directly — we already confirmed objects.first() is None.
    from django.db.models import Model as DjangoModel
    DjangoModel.save(hospital)
    return hospital


class HospitalConfigView(generics.RetrieveUpdateAPIView):
    """
    Hospital Configuration View

    GET:        Retrieve hospital configuration — auto-creates defaults on first access.
    PUT/PATCH:  Update hospital configuration (requires hms.hospital.edit_config permission).
    """
    queryset = Hospital.objects.all()

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return HospitalUpdateSerializer
        return HospitalSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        hms_perm = HMSPermission()
        hms_perm.hms_module = 'hospital'
        hms_perm.action_permission_map = {
            'update': 'edit_config',
            'partial_update': 'edit_config',
        }
        return [hms_perm]

    def get_object(self) -> Hospital:
        """Always returns a Hospital instance, creating defaults if necessary."""
        return _get_or_create_hospital(self.request)

    def retrieve(self, request, *args, **kwargs):
        """GET /api/hospital/config/ — returns the singleton, creating it if absent."""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response({
                'success': True,
                'data': serializer.data,
            })
        except Exception as exc:
            log.error("hospital_config_retrieve_failed", error=str(exc))
            return Response({
                'success': False,
                'error': str(exc),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        """PATCH/PUT /api/hospital/config/ — updates (or creates-then-updates) the singleton."""
        partial = kwargs.pop('partial', False)
        try:
            instance = self.get_object()
        except Exception as exc:
            log.error("hospital_config_update_get_failed", error=str(exc))
            return Response({
                'success': False,
                'error': str(exc),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response({
            'success': True,
            'message': 'Hospital configuration updated successfully',
            'data': HospitalSerializer(instance).data,
        })

