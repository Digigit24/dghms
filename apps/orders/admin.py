from django.contrib import admin
from django.utils.html import format_html
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import Order, OrderItem, OrderFee, FeeType, RazorpayConfig


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
        'payment_verified',
        'payment_method',
        'created_at'
    ]

    list_filter = [
        'status',
        'services_type',
        'is_paid',
        'payment_verified',
        'payment_method',
        'created_at'
    ]

    search_fields = [
        'order_number',
        'patient__first_name',
        'patient__last_name',
        'patient__mobile_primary',
        'razorpay_order_id',
        'razorpay_payment_id'
    ]

    inlines = [OrderItemInline, OrderFeeInline]

    readonly_fields = [
        'order_number',
        'subtotal',
        'total_fees',
        'total_amount',
        'razorpay_order_id',
        'razorpay_payment_id',
        'razorpay_signature',
        'payment_verified',
        'created_at',
        'updated_at',
        'tenant_id',
        'created_by_user_id',
        'cancelled_by_user_id',
    ]

    fieldsets = (
        ('Order Details', {
            'fields': (
                'order_number',
                'patient',
                'appointment',
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
        ('Razorpay Payment Details', {
            'fields': (
                'razorpay_order_id',
                'razorpay_payment_id',
                'razorpay_signature',
                'payment_verified',
                'payment_failed_reason'
            ),
            'classes': ('collapse',)
        }),
        ('Audit & Timestamps', {
            'fields': (
                'user_id',
                'created_by_user_id',
                'cancelled_by_user_id',
                'tenant_id',
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',)
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


class RazorpayConfigAdmin(TenantModelAdmin):
    """Admin configuration for Razorpay Config"""
    list_display = [
        'tenant_id',
        'is_active',
        'is_test_mode',
        'auto_capture',
        'updated_at'
    ]

    list_filter = [
        'is_active',
        'is_test_mode',
        'auto_capture'
    ]

    readonly_fields = [
        'tenant_id',
        'created_at',
        'updated_at'
    ]

    fieldsets = (
        ('Tenant Information', {
            'fields': ('tenant_id',)
        }),
        ('API Credentials', {
            'fields': (
                'razorpay_key_id',
                'razorpay_key_secret',
                'razorpay_webhook_secret'
            ),
            'description': 'Get credentials from Razorpay Dashboard. Keep these secure!'
        }),
        ('Settings', {
            'fields': ('is_test_mode', 'is_active', 'auto_capture')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        """Make key_secret readonly after creation for security"""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj:  # Editing existing config
            readonly.append('razorpay_key_secret')
        return readonly


# Register models with custom admin site
hms_admin_site.register(FeeType, FeeTypeAdmin)
hms_admin_site.register(Order, OrderAdmin)
hms_admin_site.register(OrderItem, OrderItemAdmin)
hms_admin_site.register(RazorpayConfig, RazorpayConfigAdmin)