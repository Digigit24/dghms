from django.contrib import admin
from django.utils.html import format_html
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import (
    ProductCategory,
    PharmacyProduct,
    Cart,
    CartItem,
    PharmacyOrder,
    PharmacyOrderItem
)


class ProductCategoryAdmin(TenantModelAdmin):
    """Admin for Product Categories"""
    list_display = ['name', 'type', 'is_active', 'created_at']
    list_filter = ['type', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'tenant_id']
    ordering = ['name']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'type', 'description')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('tenant_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class PharmacyProductAdmin(TenantModelAdmin):
    """Admin for Pharmacy Products"""
    list_display = [
        'product_name',
        'category',
        'company',
        'mrp',
        'selling_price',
        'quantity',
        'stock_status',
        'expiry_date',
        'is_active'
    ]
    list_filter = ['category', 'is_active', 'created_at']
    search_fields = ['product_name', 'company', 'batch_no']
    readonly_fields = ['created_at', 'updated_at', 'is_in_stock', 'low_stock_warning', 'tenant_id']
    ordering = ['-created_at']

    fieldsets = (
        ('Product Information', {
            'fields': ('product_name', 'category', 'company', 'batch_no')
        }),
        ('Pricing', {
            'fields': ('mrp', 'selling_price')
        }),
        ('Inventory', {
            'fields': ('quantity', 'minimum_stock_level', 'expiry_date')
        }),
        ('Status', {
            'fields': ('is_active', 'is_in_stock', 'low_stock_warning')
        }),
        ('Timestamps', {
            'fields': ('tenant_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def stock_status(self, obj):
        """Display stock status with color coding"""
        if obj.quantity == 0:
            return format_html('<span style="color: red;">Out of Stock</span>')
        elif obj.low_stock_warning:
            return format_html('<span style="color: orange;">Low Stock</span>')
        else:
            return format_html('<span style="color: green;">In Stock</span>')
    stock_status.short_description = 'Stock Status'


class CartItemInline(admin.TabularInline):
    """Inline admin for Cart Items"""
    model = CartItem
    extra = 0
    readonly_fields = ['price_at_time', 'total_price']
    fields = ['product', 'quantity', 'price_at_time', 'total_price']
    
    def total_price(self, obj):
        """Calculate total price for cart item"""
        if obj.id:
            return obj.total_price
        return 0
    total_price.short_description = 'Total Price'


class CartAdmin(TenantModelAdmin):
    """Admin for Shopping Carts"""
    list_display = ['user_id', 'total_items', 'total_amount', 'created_at', 'updated_at']
    search_fields = []
    readonly_fields = ['created_at', 'updated_at', 'total_items', 'total_amount', 'tenant_id']
    inlines = [CartItemInline]

    fieldsets = (
        ('Cart Information', {
            'fields': ('user_id', 'total_items', 'total_amount')
        }),
        ('Timestamps', {
            'fields': ('tenant_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class PharmacyOrderItemInline(admin.TabularInline):
    """Inline admin for Order Items"""
    model = PharmacyOrderItem
    extra = 0
    readonly_fields = ['product', 'quantity', 'price_at_time', 'total_price']
    can_delete = False
    
    def total_price(self, obj):
        """Calculate total price for order item"""
        if obj.id:
            return obj.total_price
        return 0
    total_price.short_description = 'Total Price'


class PharmacyOrderAdmin(TenantModelAdmin):
    """Admin for Pharmacy Orders"""
    list_display = [
        'id',
        'user_id',
        'total_amount',
        'status',
        'payment_status',
        'created_at'
    ]
    list_filter = ['status', 'payment_status', 'created_at']
    search_fields = ['id']
    readonly_fields = ['created_at', 'updated_at', 'total_amount', 'tenant_id']
    inlines = [PharmacyOrderItemInline]
    ordering = ['-created_at']

    fieldsets = (
        ('Order Information', {
            'fields': ('user_id', 'total_amount')
        }),
        ('Status', {
            'fields': ('status', 'payment_status')
        }),
        ('Addresses', {
            'fields': ('shipping_address', 'billing_address')
        }),
        ('Timestamps', {
            'fields': ('tenant_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        """Disable manual order creation in admin"""
        return False


# Register models with custom admin site
hms_admin_site.register(ProductCategory, ProductCategoryAdmin)
hms_admin_site.register(PharmacyProduct, PharmacyProductAdmin)
hms_admin_site.register(Cart, CartAdmin)
hms_admin_site.register(PharmacyOrder, PharmacyOrderAdmin)