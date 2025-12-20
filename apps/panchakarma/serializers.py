from rest_framework import serializers
from .models import Therapy, PanchakarmaOrder, PanchakarmaSession
from common.mixins import TenantMixin

class TherapySerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = Therapy
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at']

class PanchakarmaOrderSerializer(TenantMixin, serializers.ModelSerializer):
    billing_target = serializers.ReadOnlyField()
    therapy_name = serializers.CharField(source='therapy.name', read_only=True)
    patient_name = serializers.CharField(source='patient.user.get_full_name', read_only=True)

    class Meta:
        model = PanchakarmaOrder
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at']

class PanchakarmaSessionSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = PanchakarmaSession
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at']
