from rest_framework import serializers
from common.mixins import TenantMixin
from .models import (
    ProductCategory,
    PharmacyProduct,
    Cart,
    CartItem,
    PharmacyOrder,
    PharmacyOrderItem
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


class RazorpayOrderSerializer(serializers.Serializer):
    """Serializer for creating Razorpay orders"""
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        help_text="Order amount in INR"
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Additional notes for the order"
    )
    voucher_code = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=50,
        help_text="Voucher/coupon code if any"
    )

    def validate_amount(self, value):
        """Validate amount is positive"""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value