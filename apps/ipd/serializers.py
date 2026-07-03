# ipd/serializers.py
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from common.mixins import TenantMixin
from .models import (
    Ward, Bed, Admission, BedTransfer, IPDBilling, IPDBillItem,
    IPDBillTemplate, IPDBillTemplateItem,
)

# catalog_type -> (app_label, model_name, name_field, price_field, source)
# 'investigation' maps its own source dynamically based on the Investigation's
# category (Lab vs Radiology), matching the mapping already used in
# IPDBillingViewSet.sync_clinical_charges() for DiagnosticOrder.
CATALOG_TYPE_MAP = {
    'procedure': ('opd', 'proceduremaster', 'name', 'default_charge', 'Procedure'),
    'package': ('opd', 'procedurepackage', 'name', 'discounted_charge', 'Package'),
    'service': ('opd', 'service', 'name', 'default_charge', 'Service'),
    'investigation': ('diagnostics', 'investigation', 'name', 'base_charge', None),
}


class WardSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Ward model."""

    # These are read from DB annotations in WardViewSet.get_queryset() (no extra query).
    # Fall back to Python methods when used outside the viewset (admin, tests, etc.)
    available_beds_count = serializers.SerializerMethodField()
    occupied_beds_count = serializers.SerializerMethodField()
    total_active_beds_count = serializers.SerializerMethodField()

    class Meta:
        model = Ward
        fields = [
            'id', 'tenant_id', 'name', 'type', 'floor', 'total_beds',
            'description', 'is_active', 'available_beds_count',
            'occupied_beds_count', 'total_active_beds_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['tenant_id', 'created_at', 'updated_at']

    def get_available_beds_count(self, obj):
        if hasattr(obj, 'available_beds_count') and not callable(getattr(Ward, 'available_beds_count', None)):
            return obj.available_beds_count
        return obj.get_available_beds_count()

    def get_occupied_beds_count(self, obj):
        if hasattr(obj, 'occupied_beds_count') and not callable(getattr(Ward, 'occupied_beds_count', None)):
            return obj.occupied_beds_count
        return obj.get_occupied_beds_count()

    def get_total_active_beds_count(self, obj):
        if hasattr(obj, 'total_active_beds_count') and not callable(getattr(Ward, 'total_active_beds_count', None)):
            return obj.total_active_beds_count
        return obj.beds.filter(is_active=True).count()


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
    patient_id_display = serializers.ReadOnlyField(source='patient.patient_id')
    # Patient contact/identity mirrors of AdmissionListSerializer — the detail
    # payload must carry these too, so drawer/detail consumers (e.g. the
    # WhatsApp tab reading patient_mobile) see registration edits immediately.
    patient_mobile = serializers.ReadOnlyField(source='patient.mobile_primary')
    patient_age = serializers.ReadOnlyField(source='patient.age')
    patient_gender = serializers.ReadOnlyField(source='patient.gender')
    patient_photo = serializers.ReadOnlyField(source='patient.photo_data')
    doctor_name = serializers.SerializerMethodField()
    ward_name = serializers.ReadOnlyField(source='ward.name')
    bed_number = serializers.ReadOnlyField(source='bed.bed_number')
    length_of_stay = serializers.SerializerMethodField()

    class Meta:
        model = Admission
        fields = [
            'id', 'tenant_id', 'admission_id', 'patient', 'patient_name',
            'patient_id_display', 'patient_mobile', 'patient_age',
            'patient_gender', 'patient_photo', 'doctor_id', 'doctor_name',
            'ward', 'ward_name', 'bed', 'bed_number',
            'admission_date', 'reason', 'provisional_diagnosis', 'final_diagnosis',
            'has_mediclaim', 'tpa_name', 'claim_status',
            'claim_reference_number', 'claim_notes',
            'discharge_date', 'discharge_summary', 'discharge_type', 'status',
            'length_of_stay', 'created_by_user_id', 'discharged_by_user_id',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'tenant_id', 'admission_id', 'created_by_user_id',
            'discharged_by_user_id', 'created_at', 'updated_at'
        ]

    def get_doctor_name(self, obj):
        """Return doctor full name from the doctor FK if it exists."""
        try:
            return obj.doctor.full_name if obj.doctor else None
        except Exception:
            return None

    def validate_discharge_date(self, value):
        if value is not None:
            admission_date = self.initial_data.get('admission_date')
            if admission_date and value < admission_date:
                raise serializers.ValidationError(
                    "Discharge date must be after or equal to admission date"
                )
        return value

    def get_length_of_stay(self, obj):
        return obj.calculate_length_of_stay()


class AdmissionListSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for listing admissions — enough for a rich row card without
    an extra per-row API call (patient identity/contact + a billing
    snapshot). All of this rides on the same select_related('patient') and
    ipd_bills annotations already applied in AdmissionViewSet.get_queryset(),
    so it adds zero extra queries per row."""

    patient_name = serializers.ReadOnlyField(source='patient.full_name')
    patient_id_display = serializers.ReadOnlyField(source='patient.patient_id')
    patient_mobile = serializers.ReadOnlyField(source='patient.mobile_primary')
    patient_age = serializers.ReadOnlyField(source='patient.age')
    patient_gender = serializers.ReadOnlyField(source='patient.gender')
    patient_photo = serializers.ReadOnlyField(source='patient.photo_data')
    ward_name = serializers.ReadOnlyField(source='ward.name')
    bed_number = serializers.ReadOnlyField(source='bed.bed_number')
    # los_days is populated by DB annotation in AdmissionViewSet.get_queryset() - no extra query
    los_days = serializers.IntegerField(read_only=True, default=None)
    length_of_stay = serializers.SerializerMethodField()
    # bill_total / bill_paid are annotated Sum()s over ipd_bills — see
    # AdmissionViewSet.list(). None (not 0) means "no bills yet", which the
    # frontend treats differently from "billed but nothing due".
    bill_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=None)
    bill_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=None)

    class Meta:
        model = Admission
        fields = [
            'id', 'admission_id', 'patient', 'patient_name', 'patient_id_display',
            'patient_mobile', 'patient_age', 'patient_gender', 'patient_photo',
            'doctor_id', 'ward_name', 'bed_number', 'admission_date', 'discharge_date',
            'status', 'has_mediclaim', 'tpa_name', 'claim_status',
            'claim_reference_number', 'los_days', 'length_of_stay',
            'bill_total', 'bill_paid', 'created_by_user_id',
        ]

    def get_length_of_stay(self, obj):
        """Return los_days annotation if present, else fall back to model method."""
        if hasattr(obj, 'los_days') and obj.los_days is not None:
            return obj.los_days
        return obj.calculate_length_of_stay()


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
    """Serializer for IPD Bill Items with manual price override support.

    Create payloads may optionally include ``catalog_type`` (one of
    'procedure', 'package', 'service', 'investigation') and ``catalog_id``.
    When both are present, the corresponding master-data row is resolved
    tenant-scoped, and item_name/system_calculated_price/source are snapshot
    from it. The client may still send its own unit_price in the same
    request to override the snapshot immediately (is_price_overridden is set
    automatically when unit_price != system_calculated_price). When
    catalog_type/catalog_id are absent, the item behaves exactly as a fully
    custom/manual line (client supplies item_name/source/unit_price
    directly, origin left null).
    """

    # Computed field showing if price matches system calculation
    actual_price = serializers.DecimalField(
        source='unit_price',
        max_digits=10,
        decimal_places=2,
        read_only=True,
        help_text="The actual price (same as unit_price, for frontend clarity)"
    )
    catalog_type = serializers.ChoiceField(
        choices=list(CATALOG_TYPE_MAP.keys()),
        required=False,
        write_only=True,
        allow_null=True,
        help_text="Optional catalog to snapshot this item from: procedure, package, service, investigation",
    )
    catalog_id = serializers.IntegerField(
        required=False,
        write_only=True,
        allow_null=True,
        help_text="Primary key of the catalog row referenced by catalog_type",
    )

    class Meta:
        model = IPDBillItem
        fields = [
            'id', 'tenant_id', 'bill', 'item_name', 'source',
            'quantity', 'system_calculated_price', 'unit_price', 'actual_price',
            'total_price', 'is_price_overridden', 'notes',
            'origin_content_type', 'origin_object_id',
            'catalog_type', 'catalog_id',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'tenant_id', 'total_price',
            'is_price_overridden', 'origin_content_type', 'origin_object_id',
            'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'system_calculated_price': {'required': False, 'allow_null': True},
            'item_name': {'required': False},
            'source': {'required': False},
            # unit_price is required at the model level, but must be
            # optional at the DRF field level so a catalog_type/catalog_id
            # payload (no unit_price) can pass per-field validation and reach
            # validate(), where it is defaulted to the catalog snapshot price.
            # validate() raises if it is still missing on a fully custom item.
            'unit_price': {'required': False},
        }

    def _resolve_catalog(self, catalog_type, catalog_id, tenant_id):
        """Resolve a tenant-scoped catalog row for catalog_type/catalog_id.

        Never trusts a cross-tenant id — every lookup is filtered by
        tenant_id. Raises ValidationError (400) if not found.
        """
        app_label, model_name, name_field, price_field, source = CATALOG_TYPE_MAP[catalog_type]
        try:
            model = ContentType.objects.get(app_label=app_label, model=model_name).model_class()
        except ContentType.DoesNotExist:
            raise serializers.ValidationError({'catalog_type': 'Unsupported catalog_type.'})

        instance = model.objects.filter(tenant_id=tenant_id, pk=catalog_id).first()
        if instance is None:
            raise serializers.ValidationError({'catalog_id': 'Catalog item not found for this tenant.'})

        name = getattr(instance, name_field)
        price = getattr(instance, price_field)

        if catalog_type == 'investigation':
            category = getattr(instance, 'category', '') or ''
            source = 'Lab' if category != 'radiology' else 'Radiology'

        return instance, name, Decimal(price), source

    def validate(self, attrs):
        """Validate bill item data, resolving catalog_type/catalog_id if present."""
        catalog_type = attrs.pop('catalog_type', None)
        catalog_id = attrs.pop('catalog_id', None)

        request = self.context.get('request')
        tenant_id = getattr(request, 'tenant_id', None) if request else None

        if catalog_type and catalog_id:
            if tenant_id is None:
                raise serializers.ValidationError('Tenant context is required to resolve catalog items.')
            instance, name, system_price, source = self._resolve_catalog(catalog_type, catalog_id, tenant_id)

            attrs['item_name'] = attrs.get('item_name') or name
            attrs['source'] = source
            attrs['system_calculated_price'] = system_price
            if 'unit_price' not in attrs or attrs.get('unit_price') is None:
                attrs['unit_price'] = system_price

            content_type = ContentType.objects.get_for_model(instance)
            attrs['origin_content_type'] = content_type
            attrs['origin_object_id'] = instance.pk
        elif catalog_type or catalog_id:
            raise serializers.ValidationError(
                'Both catalog_type and catalog_id must be supplied together.'
            )
        else:
            if not attrs.get('item_name') and not (self.instance and self.instance.item_name):
                raise serializers.ValidationError({'item_name': 'This field is required.'})
            # unit_price is optional at the field level only so catalog-linked
            # creates can omit it — a fully custom item (no catalog_type/
            # catalog_id) must still supply it on create.
            no_existing_unit_price = not (self.instance and self.instance.unit_price is not None)
            if attrs.get('unit_price') is None and no_existing_unit_price:
                raise serializers.ValidationError({'unit_price': 'This field is required.'})

        unit_price = attrs.get('unit_price', getattr(self.instance, 'unit_price', None))
        system_price = attrs.get(
            'system_calculated_price', getattr(self.instance, 'system_calculated_price', None)
        )

        # If system_calculated_price is still not provided, default it to unit_price
        if system_price is None:
            system_price = unit_price
            attrs['system_calculated_price'] = system_price

        # Detect if price was manually overridden
        attrs['is_price_overridden'] = (unit_price != system_price)

        return attrs


class IPDBillingSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for IPD Billing model."""

    admission_id = serializers.ReadOnlyField(source='admission.admission_id')
    patient_name = serializers.ReadOnlyField(source='admission.patient.full_name')
    items = IPDBillItemSerializer(many=True, read_only=True)
    bed_day_info = serializers.SerializerMethodField()

    class Meta:
        model = IPDBilling
        fields = [
            'id', 'tenant_id', 'admission', 'admission_id', 'patient_name',
            'bill_number', 'bill_date', 'doctor_id', 'diagnosis', 'remarks',
            'total_amount', 'discount_percent', 'discount_amount', 'payable_amount',
            'payment_mode', 'payment_details', 'received_amount', 'balance_amount', 'payment_status',
            'items', 'bed_day_info', 'billed_by_id', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'tenant_id', 'bill_number', 'total_amount', 'payable_amount', 'balance_amount',
            'payment_status', 'billed_by_id', 'created_at', 'updated_at'
        ]

    def get_bed_day_info(self, obj):
        return obj.get_bed_day_info()


class IPDBillingListSerializer(IPDBillingSerializer):
    """Lightweight serializer for list views."""

    class Meta(IPDBillingSerializer.Meta):
        pass


class IPDBillTemplateItemSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for a single line item within an IPD bill template.

    'Bed' is explicitly rejected as a source — bed charges are always
    computed per-bill from the admission's actual length of stay via
    IPDBilling.add_bed_charges(), never part of a reusable template.
    """

    class Meta:
        model = IPDBillTemplateItem
        fields = [
            'id', 'tenant_id', 'template', 'item_name', 'source',
            'default_quantity', 'default_unit_price', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']

    def validate_source(self, value):
        if value == 'Bed':
            raise serializers.ValidationError(
                "Bed charges are always auto-computed per bill and cannot be part of a template."
            )
        return value


class IPDBillTemplateSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for IPD Bill Templates with nested, writable items.

    Nested items are accepted as a plain list of
    {item_name, source, default_quantity, default_unit_price} on create.
    Any item with source='Bed' is rejected with a 400 (standard error
    envelope raised at the view layer — see IPDBillTemplateViewSet.create).
    """

    items = IPDBillTemplateItemSerializer(many=True, required=False)

    class Meta:
        model = IPDBillTemplate
        fields = [
            'id', 'tenant_id', 'name', 'description', 'is_active',
            'created_by_user_id', 'items', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant_id', 'created_by_user_id', 'created_at', 'updated_at']

    def validate_items(self, value):
        for item in value:
            if item.get('source') == 'Bed':
                raise serializers.ValidationError(
                    "Bed charges are always auto-computed per bill and cannot be part of a template."
                )
        return value

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        request = self.context.get('request')
        tenant_id = getattr(request, 'tenant_id', None) if request else validated_data.get('tenant_id')
        validated_data['tenant_id'] = tenant_id

        template = IPDBillTemplate.objects.create(**validated_data)
        for item_data in items_data:
            item_data.pop('tenant_id', None)
            item_data.pop('template', None)
            IPDBillTemplateItem.objects.create(tenant_id=tenant_id, template=template, **item_data)
        return template


class IPDBillTemplateListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing bill templates (no nested items)."""

    item_count = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model = IPDBillTemplate
        fields = ['id', 'name', 'description', 'is_active', 'item_count', 'created_at', 'updated_at']


class IPDBillTemplateFromBillRequestSerializer(serializers.Serializer):
    """Request body for POST /ipd/bill-templates/from_bill/."""

    bill = serializers.IntegerField(help_text="ID of the IPDBilling to snapshot into a new template.")
    name = serializers.CharField(max_length=200, help_text="Name for the new template.")
    description = serializers.CharField(required=False, allow_blank=True, help_text="Optional template description.")


class IPDBillTemplateApplyRequestSerializer(serializers.Serializer):
    """Request body for POST /ipd/bill-templates/{id}/apply/."""

    bill = serializers.IntegerField(help_text="ID of the IPDBilling to apply this template's items to.")
