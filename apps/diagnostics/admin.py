from django.contrib import admin
from .models import Investigation, Requisition, DiagnosticOrder, LabReport, InvestigationRange

@admin.register(Investigation)
class InvestigationAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'category', 'base_charge')
    search_fields = ('name', 'code')
    list_filter = ('category', 'is_active')

@admin.register(Requisition)
class RequisitionAdmin(admin.ModelAdmin):
    list_display = ('requisition_number', 'patient', 'status', 'priority', 'order_date')
    search_fields = ('requisition_number', 'patient__first_name', 'patient__last_name')
    list_filter = ('status', 'priority', 'order_date')

@admin.register(DiagnosticOrder)
class DiagnosticOrderAdmin(admin.ModelAdmin):
    list_display = ('investigation', 'requisition', 'status', 'sample_id')
    list_filter = ('status',)

@admin.register(LabReport)
class LabReportAdmin(admin.ModelAdmin):
    list_display = ('diagnostic_order', 'technician_id', 'verified_by', 'created_at')

@admin.register(InvestigationRange)
class InvestigationRangeAdmin(admin.ModelAdmin):
    list_display = ('investigation', 'gender', 'min_age', 'max_age', 'min_value', 'max_value', 'unit')
    list_filter = ('gender',)