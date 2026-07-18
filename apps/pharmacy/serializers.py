from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from common.mixins import TenantMixin
from .models import (
    ProductCategory,
    PharmacyProduct,
    Cart,
    CartItem,
    PharmacyOrder,
    PharmacyOrderItem,
)


class ProductCategorySerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Product Categories"""

    class Meta:
        model = ProductCategory
        fields = [
            'id',
            'name',
            'description',
            'type',
            'is_active',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'tenant_id']


class PharmacyProductSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Pharmacy Products"""
    category = ProductCategorySerializer(read_only=True)
    category_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    is_in_stock = serializers.BooleanField(read_only=True)
    low_stock_warning = serializers.BooleanField(read_only=True)

    class Meta:
        model = PharmacyProduct
        fields = [
            'id',
            'product_name',
            'category',
            'category_id',
            'company',
            'batch_no',
            'mrp',
            'selling_price',
            'quantity',
            'minimum_stock_level',
            'expiry_date',
            'is_active',
            'is_in_stock',
            'low_stock_warning',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_in_stock', 'low_stock_warning', 'search_vector', 'tenant_id']

    def validate_category_id(self, value):
        """Validate category exists"""
        if value is not None:
            if not ProductCategory.objects.filter(id=value).exists():
                raise serializers.ValidationError("Invalid category ID")
        return value

    def validate_selling_price(self, value):
        """Ensure selling price is not greater than MRP"""
        mrp = self.initial_data.get('mrp')
        if value and mrp and float(value) > float(mrp):
            raise serializers.ValidationError("Selling price cannot be greater than MRP")
        return value


class CartItemSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Cart Items"""
    product = PharmacyProductSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)
    total_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = CartItem
        fields = [
            'id',
            'product',
            'product_id',
            'quantity',
            'price_at_time',
            'total_price'
        ]
        read_only_fields = ['price_at_time', 'total_price', 'tenant_id']

    def validate_product_id(self, value):
        """Validate product exists and is active"""
        try:
            product = PharmacyProduct.objects.get(id=value)
            if not product.is_active:
                raise serializers.ValidationError("Product is not active")
        except PharmacyProduct.DoesNotExist:
            raise serializers.ValidationError("Product not found")
        return value

    def validate_quantity(self, value):
        """Validate quantity is positive"""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value


class CartSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Cart"""
    cart_items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = Cart
        fields = [
            'id',
            'user_id',
            'cart_items',
            'total_items',
            'total_amount',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['user_id', 'created_at', 'updated_at', 'total_items', 'total_amount', 'tenant_id']


class PharmacyOrderItemSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Order Items"""
    product = PharmacyProductSerializer(read_only=True)
    total_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = PharmacyOrderItem
        fields = [
            'id',
            'product',
            'quantity',
            'price_at_time',
            'total_price'
        ]
        read_only_fields = ['product', 'price_at_time', 'total_price', 'tenant_id']


class PharmacyOrderSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Pharmacy Orders"""
    order_items = PharmacyOrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)

    class Meta:
        model = PharmacyOrder
        fields = [
            'id',
            'user_id',
            'total_amount',
            'status',
            'status_display',
            'payment_status',
            'payment_status_display',
            'shipping_address',
            'billing_address',
            'created_at',
            'updated_at',
            'order_items'
        ]
        read_only_fields = ['user_id', 'total_amount', 'created_at', 'updated_at', 'tenant_id']

    def validate_shipping_address(self, value):
        """Validate shipping address is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Shipping address is required")
        return value

    def validate_billing_address(self, value):
        """Validate billing address is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Billing address is required")
        return value


class PrescriptionItemSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for prescription line items.

    NOTE: the model stores the medicine name in ``medicine_name`` — the
    public API key ``drug_name`` is kept as an alias for compatibility with
    the originally documented contract. The previous version referenced
    non-model fields (``drug_name``/``instructions``) directly, which made
    every prescription endpoint (and /api/schema/) raise
    ImproperlyConfigured.
    """

    drug_name = serializers.CharField(
        source="medicine_name", required=False, allow_blank=True
    )
    inventory_item_name = serializers.SerializerMethodField()

    class Meta:
        from apps.pharmacy.models import PrescriptionItem
        model = PrescriptionItem
        fields = [
            "id", "prescription", "inventory_item", "source_row_key",
            "drug_name", "dosage", "frequency",
            "duration", "quantity", "inventory_item_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_inventory_item_name(self, obj) -> str:
        return obj.medicine_name


class PrescriptionSerializer(TenantMixin, serializers.ModelSerializer):
    """Serializer for Prescription model.

    ``doctor_user_id`` is kept as the public API key; it maps to the model's
    ``created_by_user_id`` (the prescribing user's SuperAdmin UUID).
    """

    doctor_user_id = serializers.UUIDField(
        source="created_by_user_id", read_only=True
    )
    visit_id = serializers.IntegerField(required=False, allow_null=True)
    encounter_type = serializers.CharField(required=False, write_only=True)
    encounter_id = serializers.IntegerField(required=False, write_only=True)
    encounter_type_label = serializers.SerializerMethodField()
    encounter_id_value = serializers.IntegerField(source="object_id", read_only=True)
    patient_id = serializers.SerializerMethodField()
    patient_name = serializers.SerializerMethodField()
    items = PrescriptionItemSerializer(many=True, read_only=True)

    class Meta:
        from apps.pharmacy.models import Prescription
        model = Prescription
        fields = [
            "id", "tenant_id", "visit_id", "encounter_type", "encounter_id",
            "encounter_type_label", "encounter_id_value", "doctor_user_id", "status",
            "notes", "patient_id", "patient_name", "items", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    ENCOUNTER_TYPE_ALIASES = {
        "opd": ("opd", "visit"),
        "opd.visit": ("opd", "visit"),
        "opd_visit": ("opd", "visit"),
        "visit": ("opd", "visit"),
        "ipd": ("ipd", "admission"),
        "ipd.admission": ("ipd", "admission"),
        "ipd_admission": ("ipd", "admission"),
        "admission": ("ipd", "admission"),
    }

    @classmethod
    def resolve_encounter_type(cls, value):
        normalized = str(value or "").strip().lower()
        if normalized not in cls.ENCOUNTER_TYPE_ALIASES:
            raise serializers.ValidationError(
                "Unsupported encounter_type. Use 'opd'/'opd.visit' or "
                "'ipd'/'ipd.admission'."
            )
        app_label, model = cls.ENCOUNTER_TYPE_ALIASES[normalized]
        try:
            return ContentType.objects.get(app_label=app_label, model=model)
        except ContentType.DoesNotExist as exc:
            raise serializers.ValidationError(
                f"Encounter content type '{app_label}.{model}' is not registered."
            ) from exc

    def validate(self, attrs):
        encounter_type = attrs.pop("encounter_type", None)
        encounter_id = attrs.pop("encounter_id", None)
        visit_id = attrs.get("visit_id")

        if encounter_type:
            if not encounter_id:
                raise serializers.ValidationError(
                    {"encounter_id": "This field is required when encounter_type is provided."}
                )
            content_type = self.resolve_encounter_type(encounter_type)
            attrs["content_type"] = content_type
            attrs["object_id"] = encounter_id
            if content_type.app_label == "opd" and content_type.model == "visit":
                attrs["visit_id"] = encounter_id
            elif visit_id:
                raise serializers.ValidationError(
                    {"visit_id": "Do not send visit_id for non-OPD encounters."}
                )
        elif visit_id:
            attrs["content_type"] = self.resolve_encounter_type("opd.visit")
            attrs["object_id"] = visit_id

        return attrs

    def get_encounter_type_label(self, obj):
        if not obj.content_type_id:
            return "opd.visit" if obj.visit_id else None
        return f"{obj.content_type.app_label}.{obj.content_type.model}"

    def _encounter_patient(self, obj):
        encounter = getattr(obj, "encounter", None) or getattr(obj, "visit", None)
        return getattr(encounter, "patient", None)

    def get_patient_id(self, obj):
        patient = self._encounter_patient(obj)
        return getattr(patient, "id", None)

    def get_patient_name(self, obj):
        patient = self._encounter_patient(obj)
        return getattr(patient, "full_name", None)
