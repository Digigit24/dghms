from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

# Import custom HMS admin site
from common.admin_site import hms_admin_site

# ✅ Import drf-spectacular views
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView
)

urlpatterns = [
    # Root redirect to admin
    path('', RedirectView.as_view(url='/admin/', permanent=False), name='index'),

    # Admin panel - Using custom HMS admin site
    path('admin/', hms_admin_site.urls),

    # Authentication endpoints (SuperAdmin integration)
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

    # Nuvi API (No authentication required)
    path('api/', include('apps.nuviapi.urls')),
    
    # ✅ API Documentation endpoints
    # OpenAPI schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    
    # Swagger UI (Interactive documentation)
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    
    # ReDoc UI (Alternative documentation)
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)