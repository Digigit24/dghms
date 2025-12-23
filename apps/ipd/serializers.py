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
    """Serializer for IPD Bill Items with manual price override support."""

    # Computed field showing if price matches system calculation
    actual_price = serializers.DecimalField(
        source='unit_price',
        max_digits=10,
        decimal_places=2,
        read_only=True,
        help_text="The actual price (same as unit_price, for frontend clarity)"
    )

    class Meta:
        model = IPDBillItem
        fields = [
            'id', 'tenant_id', 'bill', 'item_name', 'source',
            'quantity', 'system_calculated_price', 'unit_price', 'actual_price',
            'total_price', 'is_price_overridden', 'notes',
            'origin_content_type', 'origin_object_id',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'tenant_id', 'total_price',
            'is_price_overridden', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'system_calculated_price': {'required': False, 'allow_null': True}
        }

    def validate(self, attrs):
        """Validate bill item data."""
        unit_price = attrs.get('unit_price')
        
        # If system_calculated_price is not provided, set it to unit_price
        if 'system_calculated_price' not in attrs or attrs.get('system_calculated_price') is None:
            attrs['system_calculated_price'] = unit_price

        # Detect if price was manually overridden
        if unit_price != attrs.get('system_calculated_price'):
            attrs['is_price_overridden'] = True
        else:
            attrs['is_price_overridden'] = False

        return attrs


class IPDBillingSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for IPD Billing model."""

    admission_id = serializers.ReadOnlyField(source='admission.admission_id')
    patient_name = serializers.ReadOnlyField(source='admission.patient.full_name')
    items = IPDBillItemSerializer(many=True, read_only=True)

    class Meta:
        model = IPDBilling
        fields = [
            'id', 'tenant_id', 'admission', 'admission_id', 'patient_name',
            'bill_number', 'bill_date', 'doctor_id', 'diagnosis', 'remarks',
            'total_amount', 'discount_percent', 'discount_amount', 'payable_amount',
            'payment_mode', 'payment_details', 'received_amount', 'balance_amount', 'payment_status',
            'items', 'billed_by_id', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'tenant_id', 'bill_number', 'total_amount', 'payable_amount', 'balance_amount',
            'payment_status', 'billed_by_id', 'created_at', 'updated_at'
        ]

    def create(self, validated_data):
        """
        Create a new IPD Billing instance.
        """
        # The admission instance is expected to be in validated_data
        billing = IPDBilling.objects.create(**validated_data)

        # Optionally, add initial bed charges or other items
        billing.add_bed_charges()

        return billing


class IPDBillingListSerializer(TenantMixin, serializers.ModelSerializer):
    """Minimal serializer for listing IPD bills."""

    admission_id = serializers.ReadOnlyField(source='admission.admission_id')
    patient_name = serializers.ReadOnlyField(source='admission.patient.full_name')

    class Meta:
        model = IPDBilling
        fields = [
            'id', 'bill_number', 'admission_id', 'patient_name',
            'bill_date', 'total_amount', 'received_amount', 'balance_amount', 'payment_status'
        ]
