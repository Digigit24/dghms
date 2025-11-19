"""
Serializers for Auth App - User CRUD Operations

These serializers handle user data validation and serialization for
communication with the SuperAdmin API.
"""

from rest_framework import serializers
from typing import Dict, Any


class UserSerializer(serializers.Serializer):
    """
    Serializer for displaying user data
    Matches the SuperAdmin CustomUser model structure
    """
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    tenant = serializers.UUIDField(read_only=True)
    tenant_name = serializers.CharField(read_only=True)
    roles = serializers.ListField(child=serializers.DictField(), read_only=True)
    is_super_admin = serializers.BooleanField(read_only=True)
    profile_picture = serializers.URLField(max_length=500, required=False, allow_blank=True, allow_null=True)
    timezone = serializers.CharField(max_length=50, default='Asia/Kolkata')
    is_active = serializers.BooleanField(read_only=True)
    date_joined = serializers.DateTimeField(read_only=True)


class UserCreateSerializer(serializers.Serializer):
    """
    Serializer for creating new users
    Maps to SuperAdmin UserCreateSerializer
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text="Minimum 8 characters"
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text="Must match password"
    )
    phone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        allow_null=True
    )
    first_name = serializers.CharField(max_length=150, required=True)
    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        default=""
    )
    role_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        help_text="List of role UUIDs to assign to the user"
    )
    timezone = serializers.CharField(
        max_length=50,
        default='Asia/Kolkata',
        required=False
    )

    def validate(self, attrs):
        """Validate password match"""
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({
                "password": "Passwords don't match"
            })
        return attrs

    def validate_email(self, value):
        """Validate email format"""
        return value.lower().strip()

    def to_superadmin_payload(self) -> Dict[str, Any]:
        """
        Convert validated data to SuperAdmin API payload format

        Returns:
            Dict ready to send to SuperAdmin API
        """
        data = self.validated_data.copy()
        # Remove password_confirm as SuperAdmin expects it separately
        return data


class UserUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating existing users
    Only includes fields that can be updated
    """
    phone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        allow_null=True
    )
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    profile_picture = serializers.URLField(
        max_length=500,
        required=False,
        allow_blank=True,
        allow_null=True
    )
    timezone = serializers.CharField(max_length=50, required=False)
    is_active = serializers.BooleanField(required=False)
    role_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        help_text="List of role UUIDs to assign to the user"
    )

    def to_superadmin_payload(self) -> Dict[str, Any]:
        """
        Convert validated data to SuperAdmin API payload format

        Returns:
            Dict ready to send to SuperAdmin API
        """
        return self.validated_data.copy()


class UserListFilterSerializer(serializers.Serializer):
    """
    Serializer for user list filtering and pagination
    """
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=20)
    search = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    role_id = serializers.UUIDField(required=False)
    ordering = serializers.CharField(
        max_length=50,
        required=False,
        help_text="Field to order by (e.g., 'email', '-date_joined')"
    )


class RoleAssignmentSerializer(serializers.Serializer):
    """
    Serializer for assigning/updating user roles
    """
    role_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True,
        allow_empty=False,
        help_text="List of role UUIDs to assign to the user"
    )


class PasswordChangeSerializer(serializers.Serializer):
    """
    Serializer for changing user password
    """
    old_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'}
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'}
    )

    def validate(self, attrs):
        """Validate password match"""
        if attrs.get('new_password') != attrs.get('new_password_confirm'):
            raise serializers.ValidationError({
                "new_password": "Passwords don't match"
            })
        return attrs


# ==================== Doctor User Creation Serializers ====================

class DoctorUserCreateSerializer(serializers.Serializer):
    """
    Serializer for creating a user account when creating a doctor profile
    Used in the combined doctor + user creation flow
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text="Minimum 8 characters"
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'}
    )
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    first_name = serializers.CharField(max_length=150, required=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    timezone = serializers.CharField(max_length=50, default='Asia/Kolkata', required=False)

    def validate(self, attrs):
        """Validate password match"""
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({
                "password": "Passwords don't match"
            })
        return attrs

    def validate_email(self, value):
        """Validate email format"""
        return value.lower().strip()

    def to_superadmin_payload(self) -> Dict[str, Any]:
        """
        Convert to SuperAdmin API payload format

        Returns:
            Dict ready to send to SuperAdmin API
        """
        return self.validated_data.copy()
