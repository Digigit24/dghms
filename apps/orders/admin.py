from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Count
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import Order, OrderItem, OrderFee, FeeType, RazorpayConfig


# ============================================================================
# INLINE ADMIN CLASSES
# ============================================================================

class OrderFeeInline(admin.TabularInline):
    """Inline admin for Order Fees"""
    model = OrderFee
    extra = 0
    fields = ['fee_type', 'amount']
    readonly_fields = ['amount']
    can_delete = True

    def has_add_permission(self, request, obj=None):
        """Allow adding fees to orders"""
        return True


class OrderItemInline(admin.TabularInline):
    """Inline admin for Order Items"""
    model = OrderItem
    extra = 0
    fields = ['content_type', 'object_id', 'quantity', 'get_total_price', 'created_at']
    readonly_fields = ['get_total_price', 'created_at']
    can_delete = True

    def get_total_price(self, obj):
        """Display total price for the item"""
        if obj.pk:
            return f"₹{obj.get_total_price()}"
        return "-"
    get_total_price.short_description = "Total Price"

    def has_add_permission(self, request, obj=None):
        """Allow adding items to orders"""
        return True


# ============================================================================
# FEE TYPE ADMIN
# ============================================================================

@admin.register(FeeType, site=hms_admin_site)
class FeeTypeAdmin(TenantModelAdmin):
    """
    Admin configuration for Fee Types
    Manages different types of fees that can be applied to orders
    """
    list_display = [
        'name',
        'code',
        'category',
        'fee_display',
        'is_percentage',
        'value',
        'tenant_id'
    ]

    list_filter = [
        'category',
        'is_percentage',
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
        ('Fee Configuration', {
            'fields': ('is_percentage', 'value'),
            'description': 'Set fee value. If percentage, enter value like 5.00 for 5%'
        }),
        ('System Information', {
            'fields': ('tenant_id',),
            'classes': ('collapse',)
        }),
    )

    def fee_display(self, obj):
        """Display fee in readable format"""
        if obj.is_percentage:
            return f"{obj.value}%"
        return f"₹{obj.value}"
    fee_display.short_description = "Fee Amount"


# ============================================================================
# ORDER ADMIN
# ============================================================================

@admin.register(Order, site=hms_admin_site)
class OrderAdmin(TenantModelAdmin):
    """
    Comprehensive Order Management Admin
    Main admin for managing hospital service orders
    """
    list_display = [
        'order_number',
        'patient_display',
        'services_type_badge',
        'status_badge',
        'payment_status_badge',
        'subtotal_display',
        'total_fees_display',
        'total_amount_display',
        'payment_method',
        'created_at',
        'tenant_id'
    ]

    list_filter = [
        'status',
        'services_type',
        'is_paid',
        'payment_verified',
        'payment_method',
        'created_at',
    ]

    search_fields = [
        'order_number',
        'patient__first_name',
        'patient__last_name',
        'patient__mobile_primary',
        'patient__email',
        'patient__patient_id',
        'razorpay_order_id',
        'razorpay_payment_id',
        'notes'
    ]

    date_hierarchy = 'created_at'

    inlines = [OrderItemInline, OrderFeeInline]

    readonly_fields = [
        'id',
        'order_number',
        'subtotal',
        'total_fees',
        'total_amount',
        'razorpay_order_id',
        'razorpay_payment_id',
        'razorpay_signature',
        'payment_verified',
        'payment_failed_reason',
        'created_at',
        'updated_at',
        'tenant_id',
        'user_id',
        'created_by_user_id',
        'cancelled_by_user_id',
    ]

    fieldsets = (
        ('Order Information', {
            'fields': (
                'id',
                'order_number',
                'patient',
                'appointment',
                'services_type',
                'status',
                'notes'
            )
        }),
        ('Financial Details', {
            'fields': (
                'subtotal',
                'total_fees',
                'total_amount',
                'payment_method',
                'is_paid'
            ),
            'description': 'Totals are automatically calculated from items and fees'
        }),
        ('Razorpay Payment Integration', {
            'fields': (
                'razorpay_order_id',
                'razorpay_payment_id',
                'razorpay_signature',
                'payment_verified',
                'payment_failed_reason'
            ),
            'classes': ('collapse',),
            'description': 'Payment gateway details for online payments'
        }),
        ('Audit Trail', {
            'fields': (
                'tenant_id',
                'user_id',
                'created_by_user_id',
                'cancelled_by_user_id',
                'created_at',
                'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )

    # Custom display methods
    def patient_display(self, obj):
        """Display patient information"""
        if obj.patient:
            return format_html(
                '<strong>{}</strong><br><small>{}</small>',
                obj.patient.full_name,
                obj.patient.mobile_primary or 'No phone'
            )
        return format_html('<em>No Patient</em>')
    patient_display.short_description = "Patient"

    def services_type_badge(self, obj):
        """Display service type with color coding"""
        color_map = {
            'diagnostic': '#3b82f6',      # Blue
            'nursing_care': '#8b5cf6',    # Purple
            'home_healthcare': '#06b6d4', # Cyan
            'consultation': '#10b981',    # Green
            'laboratory': '#f59e0b',      # Amber
            'pharmacy': '#ef4444'         # Red
        }
        color = color_map.get(obj.services_type, '#6b7280')
        return format_html(
            '<span style="background-color:{}; color:white; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:600;">{}</span>',
            color,
            obj.get_services_type_display()
        )
    services_type_badge.short_description = "Service Type"

    def status_badge(self, obj):
        """Display order status with color coding"""
        color_map = {
            'pending': '#f59e0b',     # Orange
            'processing': '#3b82f6',  # Blue
            'completed': '#10b981',   # Green
            'cancelled': '#ef4444',   # Red
            'refunded': '#8b5cf6'     # Purple
        }
        color = color_map.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color:{}; color:white; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:600;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Status"

    def payment_status_badge(self, obj):
        """Display payment status"""
        if obj.is_paid:
            if obj.payment_verified:
                icon = "✅"
                text = "Paid & Verified"
                color = "#10b981"
            else:
                icon = "💰"
                text = "Paid"
                color = "#3b82f6"
        else:
            icon = "⏳"
            text = "Unpaid"
            color = "#ef4444"

        return format_html(
            '<span style="color:{}; font-weight:600;">{} {}</span>',
            color, icon, text
        )
    payment_status_badge.short_description = "Payment Status"

    def subtotal_display(self, obj):
        """Display subtotal"""
        return f"₹{obj.subtotal}"
    subtotal_display.short_description = "Subtotal"
    subtotal_display.admin_order_field = 'subtotal'

    def total_fees_display(self, obj):
        """Display total fees"""
        return f"₹{obj.total_fees}"
    total_fees_display.short_description = "Fees"
    total_fees_display.admin_order_field = 'total_fees'

    def total_amount_display(self, obj):
        """Display total amount"""
        return format_html(
            '<strong style="color:#10b981;">₹{}</strong>',
            obj.total_amount
        )
    total_amount_display.short_description = "Total"
    total_amount_display.admin_order_field = 'total_amount'

    def get_queryset(self, request):
        """Optimize queryset with select_related and prefetch_related"""
        return super().get_queryset(request).select_related(
            'patient',
            'appointment'
        ).prefetch_related(
            'order_items',
            'order_fee_details',
            'order_fee_details__fee_type'
        )

    def save_model(self, request, obj, form, change):
        """Auto-set created_by and recalculate totals"""
        if not change:  # New order
            if hasattr(request, 'user_id'):
                obj.created_by_user_id = request.user_id

        super().save_model(request, obj, form, change)

        # Recalculate totals after saving
        if obj.pk:
            obj.calculate_totals()

    actions = ['mark_as_completed', 'mark_as_cancelled', 'recalculate_totals']

    def mark_as_completed(self, request, queryset):
        """Mark selected orders as completed"""
        updated = queryset.update(status='completed')
        self.message_user(request, f'{updated} order(s) marked as completed.')
    mark_as_completed.short_description = "Mark selected orders as Completed"

    def mark_as_cancelled(self, request, queryset):
        """Mark selected orders as cancelled"""
        updated = queryset.filter(status='pending').update(status='cancelled')
        self.message_user(request, f'{updated} pending order(s) marked as cancelled.')
    mark_as_cancelled.short_description = "Cancel selected orders"

    def recalculate_totals(self, request, queryset):
        """Recalculate totals for selected orders"""
        count = 0
        for order in queryset:
            order.calculate_totals()
            count += 1
        self.message_user(request, f'Recalculated totals for {count} order(s).')
    recalculate_totals.short_description = "Recalculate totals"


# ============================================================================
# ORDER ITEM ADMIN
# ============================================================================

@admin.register(OrderItem, site=hms_admin_site)
class OrderItemAdmin(TenantModelAdmin):
    """
    Admin configuration for Order Items
    Individual items within an order
    """
    list_display = [
        'order_number_display',
        'patient_display',
        'content_type',
        'service_display',
        'quantity',
        'total_price_display',
        'created_at',
        'tenant_id'
    ]

    list_filter = [
        'order__status',
        'content_type',
        'created_at'
    ]

    search_fields = [
        'order__order_number',
        'order__patient__first_name',
        'order__patient__last_name',
        'order__patient__mobile_primary'
    ]

    date_hierarchy = 'created_at'

    readonly_fields = [
        'order',
        'content_type',
        'object_id',
        'quantity',
        'get_total_price',
        'created_at',
        'updated_at',
        'tenant_id',
    ]

    fieldsets = (
        ('Order Item Details', {
            'fields': (
                'order',
                'content_type',
                'object_id',
                'quantity',
                'get_total_price'
            )
        }),
        ('System Information', {
            'fields': ('tenant_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def order_number_display(self, obj):
        """Display order number with link"""
        if obj.order:
            return format_html(
                '<a href="/admin/orders/order/{}/change/">{}</a>',
                obj.order.id,
                obj.order.order_number
            )
        return "-"
    order_number_display.short_description = "Order"

    def patient_display(self, obj):
        """Display patient name"""
        if obj.order and obj.order.patient:
            return obj.order.patient.full_name
        return "-"
    patient_display.short_description = "Patient"

    def service_display(self, obj):
        """Display service information dynamically"""
        try:
            if obj.service:
                if hasattr(obj.service, 'appointment_id'):
                    return format_html(
                        '<strong>Appointment:</strong> {}',
                        obj.service.appointment_id
                    )
                return str(obj.service)
        except Exception as e:
            return format_html('<em>Error: {}</em>', str(e))
        return "-"
    service_display.short_description = "Service"

    def total_price_display(self, obj):
        """Display total price"""
        if obj.pk:
            return format_html(
                '<strong style="color:#10b981;">₹{}</strong>',
                obj.get_total_price()
            )
        return "-"
    total_price_display.short_description = "Total Price"

    def get_total_price(self, obj):
        """Get total price for readonly field"""
        if obj.pk:
            return f"₹{obj.get_total_price()}"
        return "-"
    get_total_price.short_description = "Total Price"

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'order',
            'order__patient',
            'content_type'
        )

    def has_add_permission(self, request):
        """Disable adding order items directly (should be added via Order)"""
        return False


# ============================================================================
# ORDER FEE ADMIN
# ============================================================================

@admin.register(OrderFee, site=hms_admin_site)
class OrderFeeAdmin(TenantModelAdmin):
    """
    Admin configuration for Order Fees
    Fees applied to orders
    """
    list_display = [
        'order_number_display',
        'patient_display',
        'fee_type',
        'fee_category',
        'amount_display',
        'tenant_id'
    ]

    list_filter = [
        'fee_type__category',
        'order__status'
    ]

    search_fields = [
        'order__order_number',
        'order__patient__first_name',
        'order__patient__last_name',
        'fee_type__name',
        'fee_type__code'
    ]

    readonly_fields = [
        'order',
        'fee_type',
        'amount',
        'tenant_id',
    ]

    fieldsets = (
        ('Fee Information', {
            'fields': ('order', 'fee_type', 'amount')
        }),
        ('System Information', {
            'fields': ('tenant_id',),
            'classes': ('collapse',)
        }),
    )

    def order_number_display(self, obj):
        """Display order number with link"""
        if obj.order:
            return format_html(
                '<a href="/admin/orders/order/{}/change/">{}</a>',
                obj.order.id,
                obj.order.order_number
            )
        return "-"
    order_number_display.short_description = "Order"

    def patient_display(self, obj):
        """Display patient name"""
        if obj.order and obj.order.patient:
            return obj.order.patient.full_name
        return "-"
    patient_display.short_description = "Patient"

    def fee_category(self, obj):
        """Display fee category"""
        return obj.fee_type.get_category_display()
    fee_category.short_description = "Category"

    def amount_display(self, obj):
        """Display amount"""
        return format_html(
            '<strong style="color:#ef4444;">₹{}</strong>',
            obj.amount
        )
    amount_display.short_description = "Amount"
    amount_display.admin_order_field = 'amount'

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'order',
            'order__patient',
            'fee_type'
        )

    def has_add_permission(self, request):
        """Disable adding fees directly (should be added via Order)"""
        return False


# ============================================================================
# RAZORPAY CONFIG ADMIN
# ============================================================================

@admin.register(RazorpayConfig, site=hms_admin_site)
class RazorpayConfigAdmin(TenantModelAdmin):
    """
    Admin configuration for Razorpay Payment Gateway Configuration
    One config per tenant for Razorpay integration
    """
    list_display = [
        'tenant_id',
        'key_id_masked',
        'mode_display',
        'status_display',
        'auto_capture',
        'created_at',
        'updated_at'
    ]

    list_filter = [
        'is_active',
        'is_test_mode',
        'auto_capture',
        'created_at'
    ]

    search_fields = [
        'razorpay_key_id',
        'tenant_id'
    ]

    readonly_fields = [
        'tenant_id',
        'created_at',
        'updated_at',
        'key_id_masked'
    ]

    fieldsets = (
        ('Tenant Information', {
            'fields': ('tenant_id',),
            'description': 'Each tenant can have one Razorpay configuration'
        }),
        ('API Credentials', {
            'fields': (
                'key_id_masked',
                'razorpay_key_id',
                'razorpay_key_secret',
                'razorpay_webhook_secret'
            ),
            'description': '⚠️ Get these credentials from your Razorpay Dashboard. Keep them secure!'
        }),
        ('Payment Settings', {
            'fields': ('is_test_mode', 'is_active', 'auto_capture'),
            'description': 'Configure payment behavior'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def key_id_masked(self, obj):
        """Display masked key ID for security"""
        if obj.razorpay_key_id and len(obj.razorpay_key_id) > 8:
            return f"{obj.razorpay_key_id[:4]}{'*' * 8}{obj.razorpay_key_id[-4:]}"
        return "****"
    key_id_masked.short_description = "Key ID (Masked)"

    def mode_display(self, obj):
        """Display test/live mode"""
        if obj.is_test_mode:
            return format_html(
                '<span style="background-color:#f59e0b; color:white; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:600;">TEST MODE</span>'
            )
        return format_html(
            '<span style="background-color:#10b981; color:white; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:600;">LIVE MODE</span>'
        )
    mode_display.short_description = "Mode"

    def status_display(self, obj):
        """Display active/inactive status"""
        if obj.is_active:
            return format_html(
                '<span style="color:#10b981; font-weight:600;">✅ Active</span>'
            )
        return format_html(
            '<span style="color:#ef4444; font-weight:600;">❌ Inactive</span>'
        )
    status_display.short_description = "Status"

    def get_readonly_fields(self, request, obj=None):
        """Make key_secret readonly after creation for security"""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj:  # Editing existing config
            # Make secrets read-only to prevent accidental changes
            if 'razorpay_key_secret' not in readonly:
                readonly.append('razorpay_key_secret')
            if 'razorpay_webhook_secret' not in readonly:
                readonly.append('razorpay_webhook_secret')
        return readonly

    def has_add_permission(self, request):
        """
        Check if tenant already has a config
        Only one config per tenant allowed
        """
        if hasattr(request, 'tenant_id'):
            # Check if config exists for this tenant
            if RazorpayConfig.objects.filter(tenant_id=request.tenant_id).exists():
                return False
        return super().has_add_permission(request)

    def save_model(self, request, obj, form, change):
        """Validate only one config per tenant"""
        if not change:  # New config
            existing = RazorpayConfig.objects.filter(tenant_id=obj.tenant_id).exists()
            if existing:
                from django.contrib import messages
                messages.error(request, "A Razorpay configuration already exists for this tenant. Please edit the existing one.")
                return
        super().save_model(request, obj, form, change)
