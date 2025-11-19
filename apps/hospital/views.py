from rest_framework import generics, status
from rest_framework.response import Response

from common.drf_auth import HMSPermission, AllowAny

from .models import Hospital
from .serializers import HospitalSerializer, HospitalUpdateSerializer



class HospitalConfigView(generics.RetrieveUpdateAPIView):
    """
    Hospital Configuration View

    GET: Retrieve hospital configuration (public)
    PUT/PATCH: Update hospital configuration (requires edit_config permission)
    """
    queryset = Hospital.objects.all()

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return HospitalUpdateSerializer
        return HospitalSerializer

    def get_permissions(self):
        """Anyone can view, only admins can update"""
        if self.request.method == 'GET':
            return [AllowAny()]  # Public access
        # For updates, use HMS permission
        hms_perm = HMSPermission()
        hms_perm.hms_module = 'hospital'
        hms_perm.action_permission_map = {'update': 'edit_config', 'partial_update': 'edit_config'}
        return [hms_perm]
    
    def get_object(self):
        """Get the singleton hospital instance"""
        try:
            return Hospital.get_hospital()
        except Exception:
            # If no hospital exists, return None for GET
            if self.request.method == 'GET':
                return None
            raise
    
    def retrieve(self, request, *args, **kwargs):
        """Get hospital configuration"""
        try:
            instance = self.get_object()
            if instance is None:
                return Response({
                    'success': False,
                    'error': 'Hospital configuration not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            serializer = self.get_serializer(instance)
            return Response({
                'success': True,
                'data': serializer.data
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        """Update hospital configuration"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, 
            data=request.data, 
            partial=partial
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response({
            'success': True,
            'message': 'Hospital configuration updated successfully',
            'data': HospitalSerializer(instance).data
        })

