from django.contrib import admin
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import (
    ServiceCategory,
    DiagnosticTest,
    NursingCarePackage,
    HomeHealthcareService
)

class ServiceCategoryAdmin(TenantModelAdmin):
    list_display = ['name', 'type', 'is_active']
    list_filter = ['type', 'is_active']
    search_fields = ['name']
    readonly_fields = ['tenant_id']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'type', 'is_active')
        }),
        ('Tenant Information', {
            'fields': ('tenant_id',),
            'classes': ('collapse',)
        }),
    )


class DiagnosticTestAdmin(TenantModelAdmin):
    list_display = [
        'name', 'code', 'category',
        'sample_type', 'is_active', 'base_price'
    ]
    list_filter = [
        'category', 'sample_type',
        'is_active', 'is_home_collection'
    ]
    search_fields = ['name', 'code']
    readonly_fields = ['tenant_id']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'category', 'sample_type')
        }),
        ('Pricing & Status', {
            'fields': ('base_price', 'is_active', 'is_home_collection')
        }),
        ('Tenant Information', {
            'fields': ('tenant_id',),
            'classes': ('collapse',)
        }),
    )


class NursingCarePackageAdmin(TenantModelAdmin):
    list_display = [
        'name', 'code', 'category',
        'package_type', 'is_active', 'base_price'
    ]
    list_filter = ['category', 'package_type', 'is_active']
    search_fields = ['name', 'code']
    readonly_fields = ['tenant_id']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'category', 'package_type')
        }),
        ('Pricing & Status', {
            'fields': ('base_price', 'is_active')
        }),
        ('Tenant Information', {
            'fields': ('tenant_id',),
            'classes': ('collapse',)
        }),
    )


class HomeHealthcareServiceAdmin(TenantModelAdmin):
    list_display = [
        'name', 'code', 'category',
        'service_type', 'is_active', 'base_price'
    ]
    list_filter = [
        'category', 'service_type',
        'staff_type_required', 'is_active'
    ]
    search_fields = ['name', 'code']
    readonly_fields = ['tenant_id']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'category', 'service_type', 'staff_type_required')
        }),
        ('Pricing & Status', {
            'fields': ('base_price', 'is_active')
        }),
        ('Tenant Information', {
            'fields': ('tenant_id',),
            'classes': ('collapse',)
        }),
    )

# Register models with custom admin site
hms_admin_site.register(ServiceCategory, ServiceCategoryAdmin)
hms_admin_site.register(DiagnosticTest, DiagnosticTestAdmin)
hms_admin_site.register(NursingCarePackage, NursingCarePackageAdmin)
hms_admin_site.register(HomeHealthcareService, HomeHealthcareServiceAdmin)
