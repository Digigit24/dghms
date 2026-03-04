from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import (
    Investigation, Requisition, DiagnosticOrder, LabReport, InvestigationRange,
    MedicineOrder, ProcedureOrder, PackageOrder
)
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
        read_only_fields = ['tenant_id', 'created_at', 'updated_at', 'content_type', 'object_id']

class MedicineOrderSerializer(TenantMixin, serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.product_name', read_only=True)

    class Meta:
        model = MedicineOrder
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at', 'content_type', 'object_id']

class ProcedureOrderSerializer(TenantMixin, serializers.ModelSerializer):
    procedure_name = serializers.CharField(source='procedure.name', read_only=True)

    class Meta:
        model = ProcedureOrder
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at', 'content_type', 'object_id']

class PackageOrderSerializer(TenantMixin, serializers.ModelSerializer):
    package_name = serializers.CharField(source='package.name', read_only=True)

    class Meta:
        model = PackageOrder
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at', 'content_type', 'object_id']

class RequisitionSerializer(TenantMixin, serializers.ModelSerializer):
    billing_target = serializers.ReadOnlyField()
    # Renamed from 'orders' to 'investigation_orders' for clarity
    investigation_orders = DiagnosticOrderSerializer(many=True, read_only=True, source='orders')
    # New nested serializers for different order types
    medicine_orders = MedicineOrderSerializer(many=True, read_only=True)
    procedure_orders = ProcedureOrderSerializer(many=True, read_only=True)
    package_orders = PackageOrderSerializer(many=True, read_only=True)
    patient_name = serializers.CharField(source='patient.user.get_full_name', read_only=True)
    
    # --- Option 1: Smart Payload Fields ---
    encounter_type = serializers.CharField(
        write_only=True, 
        required=False, 
        help_text="String representation of model, e.g. 'opd.visit' or 'ipd.admission'"
    )
    encounter_id = serializers.IntegerField(
        write_only=True, 
        required=False,
        help_text="ID of the encounter object"
    )
    
    # --- Nested Writes for Orders ---
    investigation_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of Investigation IDs to automatically create orders for"
    )

    class Meta:
        model = Requisition
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at', 'requisition_number', 'content_type', 'object_id']

    def validate(self, attrs):
        """
        Validate and resolve encounter_type to content_type.
        """
        encounter_type_str = attrs.get('encounter_type')
        encounter_id = attrs.get('encounter_id')

        # If using smart fields, resolve them
        if encounter_type_str:
            try:
                app_label, model_name = encounter_type_str.split('.')
                content_type = ContentType.objects.get(app_label=app_label, model=model_name)
                attrs['content_type'] = content_type
                
                if encounter_id:
                    attrs['object_id'] = encounter_id
                else:
                    raise serializers.ValidationError({"encounter_id": "This field is required when encounter_type is provided."})
                    
                # Clean up write-only fields so they aren't passed to create() directly if model doesn't have them
                # But we might need to pop them in create() instead if we want them there.
                # Actually, ModelSerializer's create() only uses fields in validated_data that match model fields.
                # We should ensure 'content_type' and 'object_id' are in validated_data.
                
            except ValueError:
                raise serializers.ValidationError({"encounter_type": "Invalid format. Use 'app_label.model_name' (e.g., 'opd.visit')."})
            except ContentType.DoesNotExist:
                raise serializers.ValidationError({"encounter_type": f"Model '{encounter_type_str}' not found."})
        
        return attrs

    def create(self, validated_data):
        # Pop write-only fields that are not model fields
        validated_data.pop('encounter_type', None)
        validated_data.pop('encounter_id', None)
        investigation_ids = validated_data.pop('investigation_ids', [])
        
        # Create the Requisition
        requisition = super().create(validated_data)
        
        # Create Nested Orders
        if investigation_ids:
            orders_to_create = []
            # Fetch investigations in bulk to get prices
            investigations = Investigation.objects.filter(id__in=investigation_ids)
            inv_map = {inv.id: inv for inv in investigations}
            
            for inv_id in investigation_ids:
                if inv_id in inv_map:
                    inv = inv_map[inv_id]
                    orders_to_create.append(
                        DiagnosticOrder(
                            tenant_id=requisition.tenant_id,
                            requisition=requisition,
                            investigation=inv,
                            price=inv.base_charge,
                            status='pending'
                        )
                    )
            
            if orders_to_create:
                DiagnosticOrder.objects.bulk_create(orders_to_create)

        return requisition

class LabReportSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = LabReport
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_at', 'updated_at']
