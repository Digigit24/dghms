"""
Authentication views for HMS using SuperAdmin backend

Provides login, logout, and token refresh endpoints that integrate
with the external SuperAdmin authentication service.
"""

import requests
import jwt
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from common.auth_backends import TenantUser
import logging

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """
    Login endpoint that authenticates against SuperAdmin API.

    Request body:
    {
        "email": "user@example.com",
        "password": "password123"
    }

    Response:
    {
        "message": "Login successful",
        "user": {
            "id": "uuid",
            "email": "user@example.com",
            ...
        },
        "tokens": {
            "access": "jwt_access_token",
            "refresh": "jwt_refresh_token"
        }
    }
    """
    email = request.data.get('email')
    password = request.data.get('password')

    if not email or not password:
        return Response({
            'error': 'Email and password are required'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Call SuperAdmin login API
        superadmin_url = getattr(settings, 'SUPERADMIN_URL', 'https://admin.celiyo.com')
        login_url = f"{superadmin_url}/api/auth/login/"

        logger.info(f"Attempting login for user: {email}")

        response = requests.post(login_url, json={
            'email': email,
            'password': password
        }, timeout=10)

        if response.status_code == 200:
            data = response.json()
            tokens = data.get('tokens', {})
            user_data = data.get('user', {})

            # Validate JWT token
            access_token = tokens.get('access')
            if not access_token:
                logger.error("No access token in response")
                return Response({
                    'error': 'Authentication failed'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Decode JWT to verify and get payload
            secret_key = getattr(settings, 'JWT_SECRET_KEY')
            algorithm = getattr(settings, 'JWT_ALGORITHM', 'HS256')
            leeway = getattr(settings, 'JWT_LEEWAY', 30)

            try:
                payload = jwt.decode(
                    access_token,
                    secret_key,
                    algorithms=[algorithm],
                    leeway=leeway
                )

                # Check if HMS module is enabled
                enabled_modules = payload.get('enabled_modules', [])
                if 'hms' not in enabled_modules:
                    logger.warning(f"HMS module not enabled for user {email}")
                    return Response({
                        'error': 'HMS module is not enabled for your account'
                    }, status=status.HTTP_403_FORBIDDEN)

                # Store tokens in session for middleware
                if hasattr(request, 'session'):
                    request.session['jwt_token'] = access_token
                    request.session['refresh_token'] = tokens.get('refresh')
                    request.session['tenant_id'] = user_data.get('tenant')
                    request.session['tenant_slug'] = user_data.get('tenant_name')
                    request.session['user_data'] = payload

                logger.info(f"Login successful for user: {email}, tenant: {user_data.get('tenant_name')}")

                return Response({
                    'message': 'Login successful',
                    'user': user_data,
                    'tokens': tokens
                }, status=status.HTTP_200_OK)

            except jwt.InvalidTokenError as e:
                logger.error(f"Invalid JWT token: {e}")
                return Response({
                    'error': 'Invalid authentication token'
                }, status=status.HTTP_401_UNAUTHORIZED)

        else:
            logger.warning(f"Login failed for user {email}: {response.status_code}")
            error_message = response.json().get('error', 'Invalid credentials') if response.text else 'Invalid credentials'
            return Response({
                'error': error_message
            }, status=response.status_code)

    except requests.RequestException as e:
        logger.error(f"Error connecting to SuperAdmin: {e}")
        return Response({
            'error': 'Authentication service unavailable'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}", exc_info=True)
        return Response({
            'error': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    Logout endpoint that blacklists the refresh token.

    Request body:
    {
        "refresh_token": "jwt_refresh_token"
    }

    Response:
    {
        "message": "Logout successful"
    }
    """
    try:
        refresh_token_str = request.data.get('refresh_token')

        if not refresh_token_str:
            return Response({
                'error': 'Refresh token is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Blacklist the refresh token (if using djangorestframework-simplejwt with blacklist)
        try:
            token = RefreshToken(refresh_token_str)
            token.blacklist()
            logger.info(f"User logged out: {request.user.email}")
        except AttributeError:
            # Blacklist app not installed, just clear session
            logger.warning("Token blacklist not available, clearing session only")

        # Clear session data
        if hasattr(request, 'session'):
            request.session.flush()

        return Response({
            'message': 'Logout successful'
        }, status=status.HTTP_200_OK)

    except TokenError as e:
        logger.warning(f"Invalid token during logout: {e}")
        # Still clear session even if token is invalid
        if hasattr(request, 'session'):
            request.session.flush()
        return Response({
            'error': 'Invalid token',
            'message': 'Logged out locally'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Unexpected error during logout: {e}", exc_info=True)
        return Response({
            'error': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token_view(request):
    """
    Refresh JWT access token using refresh token.

    Request body:
    {
        "refresh": "jwt_refresh_token"
    }

    Response:
    {
        "access": "new_jwt_access_token",
        "refresh": "new_jwt_refresh_token"  # Optional, depends on SuperAdmin API
    }
    """
    refresh_token_str = request.data.get('refresh')

    if not refresh_token_str:
        return Response({
            'error': 'Refresh token is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Call SuperAdmin refresh endpoint
        superadmin_url = getattr(settings, 'SUPERADMIN_URL', 'https://admin.celiyo.com')
        refresh_url = f"{superadmin_url}/api/auth/token/refresh/"

        logger.debug("Attempting token refresh")

        response = requests.post(refresh_url, json={
            'refresh': refresh_token_str
        }, timeout=10)

        if response.status_code == 200:
            data = response.json()
            new_access_token = data.get('access')

            # Update session with new token
            if hasattr(request, 'session') and new_access_token:
                request.session['jwt_token'] = new_access_token

            logger.info("Token refresh successful")
            return Response(data, status=status.HTTP_200_OK)
        else:
            logger.warning(f"Token refresh failed: {response.status_code}")
            error_message = response.json().get('error', 'Token refresh failed') if response.text else 'Token refresh failed'
            return Response({
                'error': error_message
            }, status=response.status_code)

    except requests.RequestException as e:
        logger.error(f"Error connecting to SuperAdmin during refresh: {e}")
        return Response({
            'error': 'Authentication service unavailable'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as e:
        logger.error(f"Unexpected error during token refresh: {e}", exc_info=True)
        return Response({
            'error': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    """
    Get current user information.

    Response:
    {
        "id": "uuid",
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "tenant_id": "tenant_uuid",
        "is_super_admin": true,
        "enabled_modules": ["hms", "crm"]
    }
    """
    user = request.user

    return Response({
        'id': str(user._original_id) if hasattr(user, '_original_id') else None,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'username': user.username,
        'tenant_id': user.tenant_id,
        'tenant_slug': user.tenant_slug,
        'is_super_admin': user.is_super_admin,
        'is_staff': user.is_staff,
        'enabled_modules': user.enabled_modules,
        'permissions': user.permissions,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_token_view(request):
    """
    Verify if a JWT token is valid.

    Request body:
    {
        "token": "jwt_access_token"
    }

    Response:
    {
        "valid": true,
        "user_id": "uuid",
        "email": "user@example.com"
    }
    """
    token = request.data.get('token')

    if not token:
        return Response({
            'error': 'Token is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        secret_key = getattr(settings, 'JWT_SECRET_KEY')
        algorithm = getattr(settings, 'JWT_ALGORITHM', 'HS256')
        leeway = getattr(settings, 'JWT_LEEWAY', 30)

        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[algorithm],
            leeway=leeway
        )

        return Response({
            'valid': True,
            'user_id': payload.get('user_id'),
            'email': payload.get('email'),
            'tenant_id': payload.get('tenant_id'),
            'is_super_admin': payload.get('is_super_admin', False)
        }, status=status.HTTP_200_OK)

    except jwt.ExpiredSignatureError:
        return Response({
            'valid': False,
            'error': 'Token has expired'
        }, status=status.HTTP_401_UNAUTHORIZED)
    except jwt.InvalidTokenError as e:
        return Response({
            'valid': False,
            'error': 'Invalid token'
        }, status=status.HTTP_401_UNAUTHORIZED)
