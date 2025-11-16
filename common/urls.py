from django.urls import path
from .views import (
    SuperAdminLoginView,
    TokenLoginView,
    superadmin_proxy_login_view,
    SuperAdminProxyLoginView,
    AdminHealthView,
    admin_logout_view,
)

app_name = 'common'

urlpatterns = [
    # Login views
    path('login/', SuperAdminLoginView.as_view(), name='login'),
    path('token-login/', TokenLoginView.as_view(), name='token_login'),
    path('proxy-login/', superadmin_proxy_login_view, name='proxy_login'),
    path('logout/', admin_logout_view, name='logout'),

    # Health check
    path('health/', AdminHealthView.as_view(), name='health'),
]
