# ipd/serializers.py
from rest_framework import serializers
from common.mixins import TenantMixin
from .models import Ward, Bed, Admission, BedTransfer, IPDBilling, IPDBillItem


class WardSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Ward model."""

    available_beds_count = serializers.ReadOnlyField(source='get_available_beds_count')
    occupied_beds_count = serializers.ReadOnlyField(source='get_occupied_beds_count')

    class Meta:
        model = Ward
        fields = [
            'id', 'tenant_id', 'name', 'type', 'floor', 'total_beds',
            'description', 'is_active', 'available_beds_count',
            'occupied_beds_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['tenant_id', 'created_at', 'updated_at']


class BedSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Bed model."""

    ward_name = serializers.ReadOnlyField(source='ward.name')

    class Meta:
        model = Bed
        fields = [
            'id', 'tenant_id', 'ward', 'ward_name', 'bed_number', 'bed_type',
            'daily_charge', 'is_occupied', 'status', 'is_active',
            'has_oxygen', 'has_ventilator', 'description',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['tenant_id', 'is_occupied', 'created_at', 'updated_at']


class BedListSerializer(TenantMixin, serializers.ModelSerializer):
    """Minimal serializer for listing beds."""

    ward_name = serializers.ReadOnlyField(source='ward.name')

    class Meta:
        model = Bed
        fields = [
            'id', 'ward', 'ward_name', 'bed_number', 'bed_type',
            'daily_charge', 'is_occupied', 'status'
        ]


class AdmissionSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Admission model."""

    patient_name = serializers.ReadOnlyField(source='patient.full_name')
    ward_name = serializers.ReadOnlyField(source='ward.name')
    bed_number = serializers.ReadOnlyField(source='bed.bed_number')
    length_of_stay = serializers.SerializerMethodField()

    class Meta:
        model = Admission
        fields = [
            'id', 'tenant_id', 'admission_id', 'patient', 'patient_name',
            'doctor_id', 'ward', 'ward_name', 'bed', 'bed_number',
            'admission_date', 'reason', 'provisional_diagnosis', 'final_diagnosis',
            'discharge_date', 'discharge_summary', 'discharge_type', 'status',
            'length_of_stay', 'created_by_user_id', 'discharged_by_user_id',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'tenant_id', 'admission_id', 'created_by_user_id',
            'discharged_by_user_id', 'created_at', 'updated_at'
        ]

    def get_length_of_stay(self, obj):
        return obj.calculate_length_of_stay()


class AdmissionListSerializer(TenantMixin, serializers.ModelSerializer):
    """Minimal serializer for listing admissions."""

    patient_name = serializers.ReadOnlyField(source='patient.full_name')
    ward_name = serializers.ReadOnlyField(source='ward.name')
    bed_number = serializers.ReadOnlyField(source='bed.bed_number')

    class Meta:
        model = Admission
        fields = [
            'id', 'admission_id', 'patient', 'patient_name', 'doctor_id',
            'ward_name', 'bed_number', 'admission_date', 'status'
        ]


class BedTransferSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for BedTransfer model."""

    from_bed_info = serializers.ReadOnlyField(source='from_bed.__str__')
    to_bed_info = serializers.ReadOnlyField(source='to_bed.__str__')
    admission_id = serializers.ReadOnlyField(source='admission.admission_id')

    class Meta:
        model = BedTransfer
        fields = [
            'id', 'tenant_id', 'admission', 'admission_id',
            'from_bed', 'from_bed_info', 'to_bed', 'to_bed_info',
            'transfer_date', 'reason', 'performed_by_user_id', 'created_at'
        ]
        read_only_fields = ['tenant_id', 'created_at']


class IPDBillItemSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for IPD Bill Items."""

    class Meta:
        model = IPDBillItem
        fields = [
            'id', 'tenant_id', 'billing', 'item_name', 'source',
            'quantity', 'unit_price', 'total_price', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['tenant_id', 'total_price', 'created_at', 'updated_at']


class IPDBillingSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for IPD Billing model."""

    admission_id = serializers.ReadOnlyField(source='admission.admission_id')
    patient_name = serializers.ReadOnlyField(source='admission.patient.full_name')
    items = IPDBillItemSerializer(many=True, read_only=True)

    class Meta:
        model = IPDBilling
        fields = [
            'tenant_id', 'admission', 'admission_id', 'patient_name',
            'bill_number', 'bill_date', 'total_amount', 'discount', 'tax',
            'paid_amount', 'balance_amount', 'status', 'items',
            'created_by_user_id', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'tenant_id', 'bill_number', 'total_amount', 'balance_amount',
            'status', 'created_by_user_id', 'created_at', 'updated_at'
        ]

    def create(self, validated_data):
        """
        Create a new IPD Billing instance, and automatically add bed charges.
        """
        # Ensure admission is provided
        admission = validated_data.get('admission')
        if not admission:
            raise serializers.ValidationError({'admission': 'Admission is required.'})

        # Check if a bill already exists for this admission
        if IPDBilling.objects.filter(admission=admission).exists():
            raise serializers.ValidationError({'admission': 'A bill already exists for this admission.'})

        # Create the billing instance
        billing = IPDBilling.objects.create(**validated_data)

        # Add initial bed charges
        billing.add_bed_charges()

        return billing


class IPDBillingListSerializer(TenantMixin, serializers.ModelSerializer):
    """Minimal serializer for listing IPD bills."""

    admission_id = serializers.ReadOnlyField(source='admission.admission_id')
    patient_name = serializers.ReadOnlyField(source='admission.patient.full_name')

    class Meta:
        model = IPDBilling
        fields = [
            'bill_number', 'admission_id', 'patient_name',
            'bill_date', 'total_amount', 'paid_amount', 'balance_amount', 'status'
        ]
