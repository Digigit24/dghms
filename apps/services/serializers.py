from rest_framework import serializers
from .models import (
    ServiceCategory,
    DiagnosticTest,
    NursingCarePackage,
    HomeHealthcareService
)

class ServiceCategorySerializer(serializers.ModelSerializer):
    """Serializer for service categories"""
    class Meta:
        model = ServiceCategory
        fields = '__all__'


class BaseServiceSerializer(serializers.ModelSerializer):
    """Base serializer for services"""
    category = ServiceCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCategory.objects.all(),
        source='category',
        write_only=True
    )
    final_price = serializers.SerializerMethodField()

    class Meta:
        fields = [
            'id', 'name', 'description', 'base_price',
            'discounted_price', 'category', 'category_id',
            'code', 'is_active', 'is_featured',
            'image', 'duration_minutes',
            'created_at', 'updated_at',
            'final_price'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_final_price(self, obj):
        return obj.calculate_final_price()


class DiagnosticTestSerializer(BaseServiceSerializer):
    """Serializer for diagnostic tests"""
    class Meta(BaseServiceSerializer.Meta):
        model = DiagnosticTest
        fields = BaseServiceSerializer.Meta.fields + [
            'sample_type', 'is_home_collection',
            'home_collection_fee', 'preparation_instructions',
            'typical_turnaround_time', 'reporting_type'
        ]


class NursingCarePackageSerializer(BaseServiceSerializer):
    """Serializer for nursing care packages"""
    class Meta(BaseServiceSerializer.Meta):
        model = NursingCarePackage
        fields = BaseServiceSerializer.Meta.fields + [
            'package_type', 'included_services',
            'max_duration', 'target_group'
        ]


class HomeHealthcareServiceSerializer(BaseServiceSerializer):
    """Serializer for home healthcare services"""
    class Meta(BaseServiceSerializer.Meta):
        model = HomeHealthcareService
        fields = BaseServiceSerializer.Meta.fields + [
            'service_type', 'staff_type_required',
            'equipment_needed', 'max_distance_km'
        ]
