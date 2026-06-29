
from rest_framework import serializers
from .models import Hospital


class HospitalSerializer(serializers.ModelSerializer):
    """Hospital configuration serializer"""
    type_display = serializers.CharField(
        source='get_type_display',
        read_only=True
    )
    full_address = serializers.CharField(read_only=True)

    class Meta:
        model = Hospital
        fields = [
            'id', 'name', 'type', 'type_display', 'tagline',
            'email', 'phone', 'alternate_phone', 'website',
            'address', 'city', 'state', 'country', 'pincode',
            'full_address', 'logo', 'working_hours',
            'has_emergency', 'has_pharmacy', 'has_laboratory',
            'registration_number', 'established_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class HospitalUpdateSerializer(serializers.ModelSerializer):
    """Hospital update serializer"""

    class Meta:
        model = Hospital
        exclude = ['id', 'created_at', 'updated_at']
