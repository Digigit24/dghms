from rest_framework import serializers
from .models import Investigation, Requisition, DiagnosticOrder, LabReport, InvestigationRange
from common.mixins import TenantMixin

class InvestigationSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = Investigation
        fields = '__all__'
        read_only_fields = ['tenant_id']

class InvestigationRangeSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = InvestigationRange
        fields = '__all__'
        read_only_fields = ['tenant_id']

class DiagnosticOrderSerializer(TenantMixin, serializers.ModelSerializer):
    investigation_name = serializers.CharField(source='investigation.name', read_only=True)
    
    class Meta:
        model = DiagnosticOrder
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at']

class RequisitionSerializer(TenantMixin, serializers.ModelSerializer):
    billing_target = serializers.ReadOnlyField()
    orders = DiagnosticOrderSerializer(many=True, read_only=True)
    patient_name = serializers.CharField(source='patient.user.get_full_name', read_only=True)

    class Meta:
        model = Requisition
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at', 'requisition_number']

class LabReportSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = LabReport
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at']