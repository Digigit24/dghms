"""
URL configuration for HMS authentication endpoints
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.auth import views

app_name = 'auth'

# Router for User CRUD operations
router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')

urlpatterns = [
    # Authentication endpoints
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('token/refresh/', views.refresh_token_view, name='token_refresh'),
    path('token/verify/', views.verify_token_view, name='token_verify'),
    path('me/', views.me_view, name='me'),

    # User CRUD endpoints (ViewSet routes)
    # GET    /api/auth/users/                    - List users
    # POST   /api/auth/users/                    - Create user
    # GET    /api/auth/users/{id}/               - Get user details
    # PUT    /api/auth/users/{id}/               - Update user
    # PATCH  /api/auth/users/{id}/               - Partial update user
    # DELETE /api/auth/users/{id}/               - Delete user
    # POST   /api/auth/users/{id}/assign_roles/  - Assign roles to user
    path('', include(router.urls)),
]
