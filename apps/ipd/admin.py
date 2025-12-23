# ipd/admin.py
from django.contrib import admin
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import Ward, Bed, Admission, BedTransfer, IPDBilling, IPDBillItem


@admin.register(Ward, site=hms_admin_site)
class WardAdmin(TenantModelAdmin):
    """Admin for Ward model."""

    list_display = [
        'id', 'name', 'type', 'floor', 'total_beds',
        'is_active', 'tenant_id', 'created_at'
    ]
    list_filter = ['type', 'is_active', 'floor']
    search_fields = ['name', 'floor']
    readonly_fields = ['tenant_id', 'created_at', 'updated_at']

    fieldsets = (
        ('Ward Information', {
            'fields': ('name', 'type', 'floor', 'total_beds', 'description', 'is_active')
        }),
        ('System Fields', {
            'fields': ('tenant_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Bed, site=hms_admin_site)
class BedAdmin(TenantModelAdmin):
    """Admin for Bed model."""

    list_display = [
        'id', 'ward', 'bed_number', 'bed_type', 'daily_charge',
        'is_occupied', 'status', 'is_active', 'tenant_id'
    ]
    list_filter = ['ward', 'bed_type', 'is_occupied', 'status', 'is_active']
    search_fields = ['bed_number', 'ward__name']
    readonly_fields = ['tenant_id', 'is_occupied', 'created_at', 'updated_at']

    fieldsets = (
        ('Bed Information', {
            'fields': ('ward', 'bed_number', 'bed_type', 'daily_charge', 'status', 'is_active')
        }),
        ('Features', {
            'fields': ('has_oxygen', 'has_ventilator', 'description')
        }),
        ('System Fields', {
            'fields': ('tenant_id', 'is_occupied', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Admission, site=hms_admin_site)
class AdmissionAdmin(TenantModelAdmin):
    """Admin for Admission model."""

    list_display = [
        'id', 'admission_id', 'patient', 'doctor_id', 'ward', 'bed',
        'admission_date', 'status', 'tenant_id'
    ]
    list_filter = ['status', 'ward', 'admission_date']
    search_fields = ['admission_id', 'patient__first_name', 'patient__last_name']
    readonly_fields = [
        'tenant_id', 'admission_id', 'created_by_user_id',
        'discharged_by_user_id', 'created_at', 'updated_at'
    ]

    fieldsets = (
        ('Admission Information', {
            'fields': (
                'admission_id', 'patient', 'doctor_id', 'ward', 'bed',
                'admission_date', 'reason', 'provisional_diagnosis', 'status'
            )
        }),
        ('Discharge Information', {
            'fields': (
                'discharge_date', 'final_diagnosis', 'discharge_summary', 'discharge_type'
            )
        }),
        ('System Fields', {
            'fields': (
                'tenant_id', 'created_by_user_id', 'discharged_by_user_id',
                'created_at', 'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )


@admin.register(BedTransfer, site=hms_admin_site)
class BedTransferAdmin(TenantModelAdmin):
    """Admin for BedTransfer model."""

    list_display = [
        'id', 'admission', 'from_bed', 'to_bed', 'transfer_date',
        'performed_by_user_id', 'tenant_id'
    ]
    list_filter = ['transfer_date']
    search_fields = ['admission__admission_id']
    readonly_fields = ['tenant_id', 'performed_by_user_id', 'created_at']

    fieldsets = (
        ('Transfer Information', {
            'fields': ('admission', 'from_bed', 'to_bed', 'transfer_date', 'reason')
        }),
        ('System Fields', {
            'fields': ('tenant_id', 'performed_by_user_id', 'created_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(IPDBilling, site=hms_admin_site)
class IPDBillingAdmin(TenantModelAdmin):
    """Admin for IPD Billing model."""

    list_display = [
        'admission', 'bill_number', 'bill_date', 'total_amount',
        'received_amount', 'balance_amount', 'payment_status', 'tenant_id'
    ]
    list_filter = ['payment_status', 'bill_date']
    search_fields = ['bill_number', 'admission__admission_id', 'admission__patient__first_name']
    readonly_fields = [
        'tenant_id', 'bill_number', 'total_amount', 'balance_amount',
        'payment_status', 'billed_by_id', 'created_at', 'updated_at'
    ]

    fieldsets = (
        ('Billing Information', {
            'fields': ('bill_number', 'admission', 'bill_date', 'payment_status')
        }),
        ('Financial Details', {
            'fields': ('total_amount', 'discount_percent', 'discount_amount', 'payable_amount', 'received_amount', 'balance_amount')
        }),
        ('System Fields', {
            'fields': ('tenant_id', 'billed_by_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(IPDBillItem, site=hms_admin_site)
class IPDBillItemAdmin(TenantModelAdmin):
    """Admin for IPD Bill Item model."""

    list_display = [
        'id', 'bill', 'item_name', 'source', 'quantity',
        'unit_price', 'total_price', 'tenant_id'
    ]
    list_filter = ['source']
    search_fields = ['item_name', 'bill__bill_number']
    readonly_fields = ['tenant_id', 'total_price', 'created_at', 'updated_at']

    fieldsets = (
        ('Item Information', {
            'fields': ('bill', 'item_name', 'source', 'quantity', 'unit_price', 'total_price', 'notes')
        }),
        ('System Fields', {
            'fields': ('tenant_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
