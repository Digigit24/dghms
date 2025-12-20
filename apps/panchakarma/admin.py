from django.contrib import admin
from .models import Therapy, PanchakarmaOrder, PanchakarmaSession

@admin.register(Therapy)
class TherapyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'base_charge', 'is_active')
    search_fields = ('name', 'code')
    list_filter = ('is_active',)

@admin.register(PanchakarmaOrder)
class PanchakarmaOrderAdmin(admin.ModelAdmin):
    list_display = ('patient', 'therapy', 'order_date', 'status')
    search_fields = ('patient__first_name', 'patient__last_name', 'therapy__name')
    list_filter = ('status', 'order_date')

@admin.register(PanchakarmaSession)
class PanchakarmaSessionAdmin(admin.ModelAdmin):
    list_display = ('order', 'session_number', 'scheduled_date', 'status')
    list_filter = ('status', 'scheduled_date')
