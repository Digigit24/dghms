from django.contrib import admin
from django.utils.html import format_html
from common.admin_site import TenantModelAdmin
from .models import Order, OrderItem, OrderFee, FeeType


class OrderFeeInline(admin.TabularInline):
    """Inline admin for Order Fees"""
    model = OrderFee
    extra = 1
    readonly_fields = ['amount']
    can_delete = False


class OrderItemInline(admin.TabularInline):
    """Inline admin for Order Items"""
    model = OrderItem
    extra = 0
    readonly_fields = [
        'get_total_price', 
        'created_at', 
        'updated_at'
    ]
    
    def get_total_price(self, obj):
        """Display total price for the item"""
        return obj.get_total_price()
    get_total_price.short_description = "Total Price"
    
    def has_add_permission(self, request, obj=None):
        """Restrict adding items to existing orders"""
        return request.user.is_superuser


@admin.register(FeeType)
class FeeTypeAdmin(TenantModelAdmin):
    """Admin configuration for Fee Types"""
    list_display = [
        'name',
        'code',
        'category',
        'is_percentage',
        'value'
    ]

    list_filter = [
        'category',
        'is_percentage'
    ]

    search_fields = [
        'name',
        'code',
        'description'
    ]

    readonly_fields = ['tenant_id']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'category', 'description')
        }),
        ('Fee Details', {
            'fields': ('is_percentage', 'value')
        }),
        ('Tenant Information', {
            'fields': ('tenant_id',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Order)
class OrderAdmin(TenantModelAdmin):
    """Comprehensive Order Management in Admin"""
    list_display = [
        'order_number',
        'patient_display',
        'services_type',
        'status_badge',
        'subtotal',
        'total_fees',
        'total_amount',
        'is_paid',
        'payment_method',
        'created_at'
    ]

    list_filter = [
        'status',
        'services_type',
        'is_paid',
        'payment_method',
        'created_at'
    ]

    search_fields = [
        'order_number',
        'patient__first_name',
        'patient__last_name',
        'patient__mobile_primary'
    ]

    inlines = [OrderItemInline, OrderFeeInline]

    readonly_fields = [
        'order_number',
        'subtotal',
        'total_fees',
        'total_amount',
        'created_at',
        'updated_at',
        'tenant_id',
    ]

    fieldsets = (
        ('Order Details', {
            'fields': (
                'order_number',
                'patient',
                'services_type',
                'status',
                'notes'
            )
        }),
        ('Financial Information', {
            'fields': (
                'subtotal',
                'total_fees',
                'total_amount',
                'payment_method',
                'is_paid'
            )
        }),
        ('Timestamps', {
            'fields': (
                'user_id',
                'tenant_id',
                'created_at',
                'updated_at'
            )
        }),
    )
    
    def patient_display(self, obj):
        """Display patient information"""
        if obj.patient:
            return f"{obj.patient.full_name} ({obj.patient.mobile_primary})"
        return "No Patient"
    patient_display.short_description = "Patient"
    
    def status_badge(self, obj):
        """Colorful status representation"""
        color_map = {
            'pending': 'orange',
            'processing': 'blue',
            'completed': 'green',
            'cancelled': 'red',
            'refunded': 'purple'
        }
        color = color_map.get(obj.status, 'gray')
        return format_html(
            '<span style="color:{}; font-weight:bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Status"
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related(
            'patient'
        ).prefetch_related(
            'order_items',
            'order_fee_details'
        )
    
    def save_model(self, request, obj, form, change):
        """
        Recalculate totals when saving
        """
        super().save_model(request, obj, form, change)
        obj.calculate_totals()


@admin.register(OrderItem)
class OrderItemAdmin(TenantModelAdmin):
    """Admin configuration for Order Items"""
    list_display = [
        'order',
        'content_type',
        'service_display',
        'quantity',
        'total_price_display'
    ]

    list_filter = [
        'order__status',
        'content_type',
        'created_at'
    ]

    search_fields = [
        'order__order_number',
        'order__patient__first_name',
        'order__patient__last_name'
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'tenant_id',
    ]

    fieldsets = (
        ('Order Item Details', {
            'fields': ('order', 'content_type', 'object_id', 'quantity')
        }),
        ('Timestamps', {
            'fields': ('tenant_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def service_display(self, obj):
        """Display service name dynamically"""
        try:
            if hasattr(obj.service, 'appointment_id'):
                return f"Appointment: {obj.service.appointment_id}"
            return str(obj.service)
        except:
            return "Unknown Service"
    service_display.short_description = "Service"
    
    def total_price_display(self, obj):
        """Display total price dynamically"""
        return obj.get_total_price()
    total_price_display.short_description = "Total Price"
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related(
            'order', 
            'content_type'
        )