"""
URL configuration for HMS authentication endpoints
"""

from django.urls import path
from apps.auth import views

app_name = 'auth'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('token/refresh/', views.refresh_token_view, name='token_refresh'),
    path('token/verify/', views.verify_token_view, name='token_verify'),
    path('me/', views.me_view, name='me'),
]
