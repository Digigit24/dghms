from django.urls import path, include
from django.views.generic import RedirectView

# Import custom HMS admin site
from common.admin_site import hms_admin_site

# Import authentication views
from common.views import (
    superadmin_proxy_login_view,
    admin_logout_view,
    HealthCheckView,
    DashboardSummaryView,
)

# ✅ Import drf-spectacular views
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView
)

urlpatterns = [
    # Root redirect to admin
    path('', RedirectView.as_view(url='/admin/', permanent=False), name='index'),

    # Health check (must be public)
    path('health/', HealthCheckView.as_view(), name='health-check'),

    # Admin panel - Using custom HMS admin site
    path('admin/', hms_admin_site.urls),

    # Authentication endpoints (SuperAdmin integration)
    path('auth/proxy-login/', superadmin_proxy_login_view, name='superadmin-proxy-login'),
    path('auth/logout/', admin_logout_view, name='admin-logout'),
    path('api/auth/', include('apps.auth.urls')),

    # API endpoints
    # Note: accounts app removed - using SuperAdmin for authentication only
    path('api/doctors/', include('apps.doctors.urls')),
    path('api/patients/', include('apps.patients.urls')),
    path('api/hospital/', include('apps.hospital.urls')),
    path('api/appointments/', include('apps.appointments.urls')),
    path('api/orders/', include('apps.orders.urls')),
    path('api/payments/', include('apps.payments.urls')),
    path('api/pharmacy/', include('apps.pharmacy.urls')),
    path('api/services/', include('apps.services.urls')),
    path('api/opd/', include('apps.opd.urls')),
    path('api/ipd/', include('apps.ipd.urls')),
    path('api/diagnostics/', include('apps.diagnostics.urls')),
    path('api/panchakarma/', include('apps.panchakarma.urls')),

    # Phase 1 APIs
    path('api/clinical/', include('apps.clinical.urls')),
    path('api/webhooks/', include('apps.webhooks.urls')),

    # Inventory Management
    path('api/inventory/', include('apps.inventory.urls')),

    # Server-side print rendering (WeasyPrint)
    path('api/print/', include('apps.printing.urls')),

    # Unified dashboard summary (composes OPD/IPD/Payments/Inventory headline numbers)
    path('api/dashboard/summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),

    # Nuvi API (No authentication required)
    path('api/', include('apps.nuviapi.urls')),

    # Nakshatra API (No authentication required)
    path('api/', include('apps.nakshatra_api.urls')),

    # ✅ API Documentation endpoints
    # OpenAPI schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),

    # Swagger UI (Interactive documentation)
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # ReDoc UI (Alternative documentation)
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Serve media files (Django handles this; configure Nginx to proxy /media/ if needed i
