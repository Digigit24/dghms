# apps/nakshatra_api/serializers.py

from rest_framework import serializers
from .models import NakshatraLead


class NakshatraLeadSerializer(serializers.ModelSerializer):
    """
    Serializer for Nakshatra Lead model.
    Used for listing and retrieving lead records.
    """

    full_name = serializers.ReadOnlyField()
    is_successfully_processed = serializers.ReadOnlyField()

    class Meta:
        model = NakshatraLead
        fields = [
            'id',
            'first_name',
            'last_name',
            'full_name',
            'email',
            'phone',
            'services',
            'appointment_date',
            'client_event_id',
            'ip_address',
            'user_agent',
            'custom_api_status',
            'custom_api_response',
            'meta_capi_status',
            'meta_capi_response',
            'is_successfully_processed',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'full_name',
            'is_successfully_processed',
        ]


class NakshatraLeadListSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for listing leads.
    Shows only essential information.
    """

    full_name = serializers.ReadOnlyField()
    is_successfully_processed = serializers.ReadOnlyField()

    class Meta:
        model = NakshatraLead
        fields = [
            'id',
            'full_name',
            'email',
            'phone',
            'services',
            'appointment_date',
            'custom_api_status',
            'meta_capi_status',
            'is_successfully_processed',
            'created_at',
        ]


class NakshatraLeadCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating Nakshatra leads.
    Used internally when saving form submissions.
    """

    class Meta:
        model = NakshatraLead
        fields = [
            'first_name',
            'last_name',
            'email',
            'phone',
            'services',
            'appointment_date',
            'client_event_id',
            'ip_address',
            'user_agent',
            'custom_api_status',
            'custom_api_response',
            'meta_capi_status',
            'meta_capi_response',
        ]

    def validate_email(self, value):
        """Validate email format"""
        if not value:
            raise serializers.ValidationError("Email is required.")
        return value.lower()

    def validate_phone(self, value):
        """Validate phone number"""
        if not value:
            raise serializers.ValidationError("Phone number is required.")
        
        return value
