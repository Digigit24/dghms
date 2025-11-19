"""
SuperAdmin API Client Service

Centralized HTTP client for making API calls to the SuperAdmin Django application.
Handles user CRUD operations and authentication.
"""

import requests
from django.conf import settings
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class SuperAdminAPIException(Exception):
    """Custom exception for SuperAdmin API errors"""
    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(self.message)


class SuperAdminClient:
    """Client for SuperAdmin API interactions"""

    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize SuperAdmin client

        Args:
            access_token: JWT access token for authenticated requests
        """
        self.base_url = getattr(settings, 'SUPERADMIN_URL', 'https://admin.celiyo.com')
        self.access_token = access_token
        self.timeout = 10

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authorization"""
        headers = {'Content-Type': 'application/json'}
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        return headers

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Handle API response and raise exceptions for errors

        Args:
            response: requests.Response object

        Returns:
            Parsed JSON response data

        Raises:
            SuperAdminAPIException: For any API errors
        """
        try:
            response_data = response.json()
        except ValueError:
            response_data = {'detail': response.text}

        if response.status_code >= 400:
            error_message = response_data.get('error') or response_data.get('detail') or 'Unknown error'
            logger.error(f"SuperAdmin API error [{response.status_code}]: {error_message}")
            raise SuperAdminAPIException(
                message=error_message,
                status_code=response.status_code,
                response_data=response_data
            )

        return response_data

    # ==================== USER CRUD OPERATIONS ====================

    def create_user(self, user_data: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
        """
        Create a new user in SuperAdmin

        Args:
            user_data: User data including email, password, first_name, last_name, etc.
            tenant_id: UUID of the tenant to associate the user with

        Returns:
            Created user data with user_id

        Raises:
            SuperAdminAPIException: If user creation fails
        """
        url = f"{self.base_url}/api/users/"

        # Add tenant_id to the user data
        payload = {
            **user_data,
            'tenant': tenant_id
        }

        logger.info(f"Creating user in SuperAdmin: {user_data.get('email')} for tenant: {tenant_id}")
        logger.debug(f"SuperAdmin API URL: {url}")
        logger.debug(f"Payload: {payload}")

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.timeout
            )

            # Log raw response details
            logger.info(f"SuperAdmin response status: {response.status_code}")
            logger.debug(f"SuperAdmin response headers: {dict(response.headers)}")
            logger.debug(f"SuperAdmin response body: {response.text[:1000]}")  # First 1000 chars

            # EXPLICIT DEBUG - Also print to console
            print(f"\n{'='*60}")
            print(f"SUPERADMIN CLIENT DEBUG")
            print(f"{'='*60}")
            print(f"URL: {url}")
            print(f"Status: {response.status_code}")
            print(f"Response Text: {response.text}")
            print(f"{'='*60}\n")

            result = self._handle_response(response)
            logger.info(f"Parsed response data: {result}")
            logger.info(f"User created successfully: {result.get('id')}")

            print(f"Parsed result: {result}")
            print(f"User ID from result: {result.get('id')}")

            return result

        except requests.RequestException as e:
            logger.error(f"Network error creating user: {str(e)}")
            raise SuperAdminAPIException(f"Network error: {str(e)}")

    def get_user(self, user_id: str) -> Dict[str, Any]:
        """
        Get user details by ID

        Args:
            user_id: UUID of the user

        Returns:
            User data

        Raises:
            SuperAdminAPIException: If user not found or request fails
        """
        url = f"{self.base_url}/api/users/{user_id}/"

        logger.info(f"Fetching user from SuperAdmin: {user_id}")

        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=self.timeout
            )
            return self._handle_response(response)

        except requests.RequestException as e:
            logger.error(f"Network error fetching user: {str(e)}")
            raise SuperAdminAPIException(f"Network error: {str(e)}")

    def list_users(self, tenant_id: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        List users for a tenant

        Args:
            tenant_id: UUID of the tenant
            params: Optional query parameters for filtering/pagination

        Returns:
            List of users (may be paginated)

        Raises:
            SuperAdminAPIException: If request fails
        """
        url = f"{self.base_url}/api/users/"

        # Add tenant filter
        query_params = params or {}
        query_params['tenant'] = tenant_id

        logger.info(f"Listing users for tenant: {tenant_id}")

        try:
            response = requests.get(
                url,
                params=query_params,
                headers=self._get_headers(),
                timeout=self.timeout
            )
            return self._handle_response(response)

        except requests.RequestException as e:
            logger.error(f"Network error listing users: {str(e)}")
            raise SuperAdminAPIException(f"Network error: {str(e)}")

    def update_user(self, user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update user details

        Args:
            user_id: UUID of the user
            user_data: Updated user data

        Returns:
            Updated user data

        Raises:
            SuperAdminAPIException: If update fails
        """
        url = f"{self.base_url}/api/users/{user_id}/"

        logger.info(f"Updating user in SuperAdmin: {user_id}")

        try:
            response = requests.patch(
                url,
                json=user_data,
                headers=self._get_headers(),
                timeout=self.timeout
            )
            result = self._handle_response(response)
            logger.info(f"User updated successfully: {user_id}")
            return result

        except requests.RequestException as e:
            logger.error(f"Network error updating user: {str(e)}")
            raise SuperAdminAPIException(f"Network error: {str(e)}")

    def delete_user(self, user_id: str) -> bool:
        """
        Delete a user (soft delete by setting is_active=False)

        Args:
            user_id: UUID of the user

        Returns:
            True if deletion was successful

        Raises:
            SuperAdminAPIException: If deletion fails
        """
        url = f"{self.base_url}/api/users/{user_id}/"

        logger.info(f"Deleting user in SuperAdmin: {user_id}")

        try:
            response = requests.delete(
                url,
                headers=self._get_headers(),
                timeout=self.timeout
            )
            self._handle_response(response)
            logger.info(f"User deleted successfully: {user_id}")
            return True

        except requests.RequestException as e:
            logger.error(f"Network error deleting user: {str(e)}")
            raise SuperAdminAPIException(f"Network error: {str(e)}")

    def assign_roles(self, user_id: str, role_ids: List[str]) -> Dict[str, Any]:
        """
        Assign roles to a user

        Args:
            user_id: UUID of the user
            role_ids: List of role UUIDs to assign

        Returns:
            Success message

        Raises:
            SuperAdminAPIException: If role assignment fails
        """
        url = f"{self.base_url}/api/users/{user_id}/assign_roles/"

        logger.info(f"Assigning roles to user {user_id}: {role_ids}")

        try:
            response = requests.post(
                url,
                json={'role_ids': role_ids},
                headers=self._get_headers(),
                timeout=self.timeout
            )
            result = self._handle_response(response)
            logger.info(f"Roles assigned successfully to user: {user_id}")
            return result

        except requests.RequestException as e:
            logger.error(f"Network error assigning roles: {str(e)}")
            raise SuperAdminAPIException(f"Network error: {str(e)}")

    # ==================== AUTHENTICATION OPERATIONS ====================

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user and get JWT tokens

        Args:
            email: User email
            password: User password

        Returns:
            Login response with tokens and user data

        Raises:
            SuperAdminAPIException: If authentication fails
        """
        url = f"{self.base_url}/api/auth/login/"

        logger.info(f"Authenticating user: {email}")

        try:
            response = requests.post(
                url,
                json={'email': email, 'password': password},
                headers={'Content-Type': 'application/json'},
                timeout=self.timeout
            )
            result = self._handle_response(response)
            logger.info(f"User authenticated successfully: {email}")
            return result

        except requests.RequestException as e:
            logger.error(f"Network error during login: {str(e)}")
            raise SuperAdminAPIException(f"Network error: {str(e)}")

    def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh JWT access token

        Args:
            refresh_token: JWT refresh token

        Returns:
            New access token

        Raises:
            SuperAdminAPIException: If token refresh fails
        """
        url = f"{self.base_url}/api/auth/token/refresh/"

        try:
            response = requests.post(
                url,
                json={'refresh': refresh_token},
                headers={'Content-Type': 'application/json'},
                timeout=self.timeout
            )
            return self._handle_response(response)

        except requests.RequestException as e:
            logger.error(f"Network error refreshing token: {str(e)}")
            raise SuperAdminAPIException(f"Network error: {str(e)}")


def get_superadmin_client(request) -> SuperAdminClient:
    """
    Helper function to get SuperAdminClient with auth token from request

    Args:
        request: Django request object (should have JWT token)

    Returns:
        Configured SuperAdminClient instance
    """
    # Try to get token from session first (for admin/session auth)
    access_token = request.session.get('jwt_token')

    # If not in session, try Authorization header (for API auth)
    if not access_token:
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            access_token = auth_header.split(' ')[1]

    return SuperAdminClient(access_token=access_token)
