from django.contrib import admin
from django.utils.html import format_html
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import PaymentCategory, Transaction, AccountingPeriod


class PaymentCategoryAdmin(TenantModelAdmin):
    """Admin configuration for Payment Categories"""
    list_display = [
        'name',
        'category_type',
        'description'
    ]

    list_filter = ['category_type']
    search_fields = ['name', 'description']
    readonly_fields = ['tenant_id']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category_type', 'description')
        }),
        ('Tenant Information', {
            'fields': ('tenant_id',),
            'classes': ('collapse',)
        }),
    )


class TransactionAdmin(TenantModelAdmin):
    """Comprehensive Transaction Management in Admin"""
    list_display = [
        'transaction_number',
        'amount',
        'category',
        'transaction_type',
        'payment_method',
        'status_badge',
        'created_at'
    ]

    list_filter = [
        'transaction_type',
        'category',
        'payment_method',
        'is_reconciled',
        'created_at'
    ]

    search_fields = [
        'transaction_number',
        'description'
    ]

    readonly_fields = [
        'transaction_number',
        'created_at',
        'updated_at',
        'reconciled_at',
        'tenant_id',
    ]

    fieldsets = (
        ('Transaction Details', {
            'fields': (
                'transaction_number',
                'amount',
                'category',
                'transaction_type',
                'payment_method',
                'description'
            )
        }),
        ('Related Object', {
            'fields': (
                'content_type',
                'object_id'
            )
        }),
        ('User Information', {
            'fields': ('user_id',)
        }),
        ('Reconciliation', {
            'fields': (
                'is_reconciled',
                'reconciled_at',
                'reconciled_by_id'
            )
        }),
        ('Timestamps', {
            'fields': (
                'tenant_id',
                'created_at',
                'updated_at'
            )
        }),
    )
    
    def status_badge(self, obj):
        """Colorful status representation"""
        color_map = {
            'payment': 'green',
            'refund': 'blue',
            'expense': 'red',
            'adjustment': 'orange'
        }
        color = color_map.get(obj.transaction_type, 'gray')
        return format_html(
            '<span style="color:{}; font-weight:bold;">{}</span>',
            color,
            obj.get_transaction_type_display()
        )
    status_badge.short_description = "Transaction Type"
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related(
            'category'
        )


class AccountingPeriodAdmin(TenantModelAdmin):
    """Admin configuration for Accounting Periods"""
    list_display = [
        'name',
        'start_date',
        'end_date',
        'period_type',
        'total_income',
        'total_expenses',
        'net_profit',
        'is_closed'
    ]

    list_filter = [
        'period_type',
        'is_closed',
        'start_date',
        'end_date'
    ]

    search_fields = ['name']

    readonly_fields = [
        'total_income',
        'total_expenses',
        'net_profit',
        'closed_at',
        'tenant_id',
    ]

    fieldsets = (
        ('Period Information', {
            'fields': ('name', 'start_date', 'end_date', 'period_type')
        }),
        ('Financial Summary', {
            'fields': ('total_income', 'total_expenses', 'net_profit')
        }),
        ('Status', {
            'fields': ('is_closed', 'closed_at', 'closed_by_id')
        }),
        ('Tenant Information', {
            'fields': ('tenant_id',),
            'classes': ('collapse',)
        }),
    )

    actions = ['calculate_financial_summary']
    
    def calculate_financial_summary(self, request, queryset):
        """
        Action to recalculate financial summary for selected accounting periods
        """
        for period in queryset:
            period.calculate_financial_summary()
        
        self.message_user(request, f"{queryset.count()} accounting periods updated.")
    calculate_financial_summary.short_description = "Recalculate Financial Summary"

# Register models with custom admin site
hms_admin_site.register(PaymentCategory, PaymentCategoryAdmin)
hms_admin_site.register(Transaction, TransactionAdmin)
hms_admin_site.register(AccountingPeriod, AccountingPeriodAdmin)
