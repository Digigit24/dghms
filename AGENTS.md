# DigiHMS - Hospital Management System

## Complete Architecture & Development Guide

**Last Updated**: 2025-11-17
**Version**: 2.0 (SuperAdmin Integration)

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Authentication & Authorization](#authentication--authorization)
3. [Multi-Tenancy Architecture](#multi-tenancy-architecture)
4. [Database Schema](#database-schema)
5. [API Structure](#api-structure)
6. [Admin Interface](#admin-interface)
7. [Development Guidelines](#development-guidelines)
8. [Common Pitfalls & Solutions](#common-pitfalls--solutions)

---

## System Overview

### Technology Stack
- **Framework**: Django 5.2.8 + Django REST Framework
- **Database**: PostgreSQL (multi-tenant with UUID tenant_id)
- **Authentication**: JWT (from SuperAdmin) + Session (for Django Admin)
- **User Management**: Centralized via SuperAdmin (no local User model)

### Architecture Pattern
DigiHMS operates as a **satellite application** under a centralized SuperAdmin system:

```
┌─────────────────────────────────────────┐
│         SuperAdmin (Port 8000)           │
│  - User Management                       │
│  - Tenant Management                     │
│  - JWT Token Generation                  │
│  - Permission Management                 │
└──────────────┬──────────────────────────┘
               │ JWT Tokens
               │ User Authentication
               ▼
┌─────────────────────────────────────────┐
│         DigiHMS (Port 8002)              │
│  - Hospital Management                   │
│  - Patient Records                       │
│  - Doctor Profiles                       │
│  - Appointments, OPD, Pharmacy          │
│  - NO User Model (uses user_id UUID)   │
└─────────────────────────────────────────┘
```

### Key Architectural Principles

1. **No Django User Model**: All user references are UUID fields (`user_id`, `created_by_user_id`, etc.)
2. **Tenant Isolation**: Every model has a `tenant_id` UUIDField for data segregation
3. **JWT-Based API Auth**: All API requests authenticated via Bearer tokens from SuperAdmin
4. **Session-Based Admin Auth**: Django Admin uses proxy authentication to SuperAdmin
5. **No Django Permissions**: Permission checking done via JWT payload, not Django's permission system

---

## Authentication & Authorization

### 1. User Management

**CRITICAL**: DigiHMS does NOT manage users. All user operations are handled by SuperAdmin.

#### User References in Models

```python
# ❌ WRONG - Do NOT use ForeignKey to User
from django.contrib.auth import get_user_model
User = get_user_model()

class DoctorProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # WRONG!

# ✅ CORRECT - Use UUID field
class DoctorProfile(models.Model):
    user_id = models.UUIDField(
        unique=True,
        db_index=True,
        help_text="SuperAdmin User ID (required for doctors)"
    )
```

#### Audit Trail Fields

```python
class PatientProfile(models.Model):
    # Core user link
    user_id = models.UUIDField(
        null=True,  # Null for walk-in patients
        blank=True,
        db_index=True,
        help_text="SuperAdmin User ID (null for walk-in patients)"
    )

    # Audit trails
    created_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SuperAdmin User ID who created this record"
    )
```

### 2. JWT Authentication (API Requests)

#### JWT Token Structure

Tokens received from SuperAdmin contain:

```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "doctor@hospital.com",
  "tenant_id": "123e4567-e89b-12d3-a456-426614174000",
  "tenant_slug": "city-hospital",
  "user_type": "staff",
  "is_patient": false,
  "is_super_admin": false,
  "permissions": {
    "hms.patients.view": "all",
    "hms.patients.create": true,
    "hms.doctors.view": "all",
    "hms.appointments.create": true
  },
  "enabled_modules": ["hms"],
  "exp": 1700000000
}
```

#### Making API Requests

```bash
# Get JWT token from SuperAdmin login
TOKEN="eyJhbGci..."

# Use Bearer token in Authorization header
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8002/api/patients/
```

#### Middleware Processing

The `JWTAuthenticationMiddleware` automatically:
1. Validates JWT signature and expiration
2. Checks if 'hms' module is enabled
3. Sets request attributes:
   ```python
   request.user_id          # UUID from token
   request.email            # User's email
   request.tenant_id        # Tenant UUID
   request.tenant_slug      # Tenant name
   request.permissions      # Permission dict
   request.is_patient       # Boolean flag
   request.user_type        # "staff" or "patient"
   ```

### 3. Session Authentication (Django Admin)

#### Login Flow

1. User visits `/admin/`
2. Custom login form sends credentials to SuperAdmin API
3. SuperAdmin validates and returns JWT token
4. DigiHMS creates session with TenantUser object
5. User accesses admin with session cookie

#### TenantUser Class

```python
# Non-database user class for admin access
class TenantUser:
    def __init__(self, user_data):
        self.id = user_data['user_id']
        self.email = user_data['email']
        self.tenant_id = user_data['tenant_id']
        self.is_active = True
        self.is_staff = True  # All HMS users are staff
        self.is_superuser = user_data.get('is_super_admin', False)
```

### 4. Permissions

#### How Permissions Work

**❌ DO NOT USE Django Permissions**
```python
# WRONG - Django permissions don't work
from rest_framework.permissions import DjangoModelPermissions
```

**✅ USE JWT Permissions**
```python
from common.permissions import check_permission, HMSPermissions

def get_queryset(self, request):
    if check_permission(request, HMSPermissions.PATIENTS_VIEW):
        return PatientProfile.objects.filter(tenant_id=request.tenant_id)
    raise PermissionDenied("No permission to view patients")
```

#### Permission Constants

```python
from common.permissions import HMSPermissions

# Available permissions
HMSPermissions.PATIENTS_VIEW      # "hms.patients.view"
HMSPermissions.PATIENTS_CREATE    # "hms.patients.create"
HMSPermissions.PATIENTS_EDIT      # "hms.patients.edit"
HMSPermissions.PATIENTS_DELETE    # "hms.patients.delete"
HMSPermissions.DOCTORS_VIEW       # "hms.doctors.view"
HMSPermissions.APPOINTMENTS_CREATE # "hms.appointments.create"
# ... and more
```

#### Permission Scopes

Permissions can have different scopes:

- `true` - User has permission
- `false` - User does NOT have permission
- `"all"` - User can access all records in their tenant
- `"own"` - User can only access their own records
- `"team"` - User can access team records (future)

Example:
```python
# Staff user
{
    "hms.patients.view": "all",  # Can view all patients in tenant
    "hms.patients.create": true  # Can create patients
}

# Patient user
{
    "hms.patients.view": "own",  # Can only view own patient record
    "hms.appointments.create": true  # Can create own appointments
}
```

---

## Multi-Tenancy Architecture

### Tenant Isolation

Every model MUST have a `tenant_id` field:

```python
class YourModel(models.Model):
    # REQUIRED for all models
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant this record belongs to"
    )

    # ... other fields ...

    class Meta:
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'status']),  # Combined indexes
        ]
```

### Automatic Tenant Filtering

#### In ViewSets

```python
from common.mixins import TenantViewSetMixin

class PatientViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = PatientProfile.objects.all()
    serializer_class = PatientSerializer

    # Automatically filters by request.tenant_id
    # No manual filtering needed!
```

#### In Serializers

```python
from common.mixins import TenantMixin

class PatientSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = PatientProfile
        fields = ['id', 'tenant_id', 'first_name', ...]
        read_only_fields = ['tenant_id']  # Auto-set from request
```

#### Manual Filtering (when needed)

```python
def get_queryset(self):
    return PatientProfile.objects.filter(
        tenant_id=self.request.tenant_id
    )
```

### Patient Access Control

For models that patients can access, use `PatientAccessMixin`:

```python
from common.mixins import PatientAccessMixin, TenantViewSetMixin

class PatientViewSet(PatientAccessMixin, TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = PatientProfile.objects.all()

    # Behavior:
    # - Staff users: See all patients in their tenant
    # - Patient users: Only see their own patient record (where user_id matches)
```

---

## Database Schema

### Standard Model Pattern

```python
from django.db import models
import uuid

class ExampleModel(models.Model):
    """Example model showing all standard fields"""

    # Primary Key (auto-generated)
    id = models.AutoField(primary_key=True)

    # Tenant Isolation (REQUIRED)
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant this record belongs to"
    )

    # User Reference (UUID, not ForeignKey)
    user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SuperAdmin User ID"
    )

    # Regular Fields
    name = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('inactive', 'Inactive')],
        default='active'
    )

    # Timestamps (STANDARD)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Audit Trail
    created_by_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SuperAdmin User ID who created this record"
    )

    class Meta:
        db_table = 'example_models'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['user_id']),
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.id})"
```

### Key Models

#### PatientProfile
```python
class PatientProfile(models.Model):
    tenant_id = models.UUIDField(db_index=True)
    user_id = models.UUIDField(null=True, blank=True)  # Null for walk-ins
    patient_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    # ... contact, medical, insurance fields ...
    created_by_user_id = models.UUIDField(null=True, blank=True)
```

#### DoctorProfile
```python
class DoctorProfile(models.Model):
    tenant_id = models.UUIDField(db_index=True)
    user_id = models.UUIDField(unique=True)  # REQUIRED - doctors must login
    medical_license_number = models.CharField(max_length=64)
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2)
    # ... professional details ...
```

#### Appointment
```python
class Appointment(models.Model):
    tenant_id = models.UUIDField(db_index=True)
    appointment_id = models.CharField(max_length=20, unique=True)
    patient = models.ForeignKey(PatientProfile, on_delete=models.PROTECT)
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.PROTECT)
    # ... appointment details ...
    created_by_user_id = models.UUIDField(null=True, blank=True)
    cancelled_by_user_id = models.UUIDField(null=True, blank=True)
```

---

## API Structure

### ViewSet Pattern

```python
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from common.mixins import TenantViewSetMixin, PatientAccessMixin
from common.permissions import check_permission, HMSPermissions

class PatientViewSet(
    TenantViewSetMixin,      # Auto-filter by tenant
    PatientAccessMixin,       # Patient access control
    viewsets.ModelViewSet
):
    queryset = PatientProfile.objects.all()

    # Multiple serializers for different actions
    def get_serializer_class(self):
        if self.action == 'list':
            return PatientProfileListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return PatientProfileCreateUpdateSerializer
        return PatientProfileDetailSerializer

    # Filters and search
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'blood_group', 'gender']
    search_fields = ['first_name', 'last_name', 'mobile_primary', 'patient_id']
    ordering_fields = ['created_at', 'last_name']
    ordering = ['-created_at']

    # Permission checking
    def get_queryset(self):
        if not check_permission(self.request, HMSPermissions.PATIENTS_VIEW):
            raise PermissionDenied("No permission to view patients")
        return super().get_queryset()

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.PATIENTS_CREATE):
            raise PermissionDenied("No permission to create patients")

        # Auto-set created_by
        serializer.save(created_by_user_id=self.request.user_id)
```

### Serializer Pattern

```python
from rest_framework import serializers
from common.mixins import TenantMixin

# List Serializer (minimal fields)
class PatientProfileListSerializer(TenantMixin, serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    age = serializers.ReadOnlyField()

    class Meta:
        model = PatientProfile
        fields = [
            'id', 'patient_id', 'full_name', 'age', 'gender',
            'mobile_primary', 'status', 'tenant_id'
        ]
        read_only_fields = ['tenant_id']

# Detail Serializer (all fields)
class PatientProfileDetailSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = PatientProfile
        fields = '__all__'
        read_only_fields = ['tenant_id', 'patient_id', 'created_by_user_id']

# Create/Update Serializer (exclude auto fields)
class PatientProfileCreateUpdateSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = PatientProfile
        exclude = ['tenant_id', 'patient_id', 'created_by_user_id']

    def validate(self, attrs):
        # Custom validation
        if attrs.get('insurance_provider') and not attrs.get('insurance_policy_number'):
            raise serializers.ValidationError({
                'insurance_policy_number': 'Required when insurance provider is specified'
            })
        return attrs
```

### URL Configuration

```python
from rest_framework.routers import DefaultRouter
from .views import PatientViewSet

router = DefaultRouter()
router.register(r'patients', PatientViewSet, basename='patient')

urlpatterns = router.urls
```

---

## Admin Interface

### TenantModelAdmin

All admin classes must inherit from `TenantModelAdmin`:

```python
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import PatientProfile

class PatientProfileAdmin(TenantModelAdmin):
    list_display = [
        'patient_id',
        'full_name',
        'mobile_primary',
        'status',
        'tenant_id'  # Always show tenant_id
    ]

    list_filter = ['status', 'gender', 'blood_group']
    search_fields = ['first_name', 'last_name', 'patient_id', 'mobile_primary']

    readonly_fields = [
        'patient_id',
        'tenant_id',  # Tenant ID is read-only
        'created_at',
        'updated_at',
        'created_by_user_id'
    ]

    fieldsets = (
        ('Patient Information', {
            'fields': ('patient_id', 'first_name', 'last_name', 'gender')
        }),
        ('Contact', {
            'fields': ('mobile_primary', 'email', 'address_line1', 'city')
        }),
        ('System Fields', {
            'fields': ('tenant_id', 'created_by_user_id', 'created_at'),
            'classes': ('collapse',)
        }),
    )

# Register with custom admin site
hms_admin_site.register(PatientProfile, PatientProfileAdmin)
```

### Important Admin Rules

1. **Always show `tenant_id`** in list_display and readonly_fields
2. **Never** allow editing `tenant_id` - it's auto-set
3. **Use `user_id`** fields, not `user` ForeignKeys
4. **Don't reference** `.user.get_full_name()` - there's no user relationship

#### ❌ WRONG Admin Code
```python
# WRONG - References user ForeignKey that doesn't exist
class AppointmentAdmin(admin.ModelAdmin):
    def doctor_display(self, obj):
        return f"Dr. {obj.doctor.user.get_full_name()}"  # FAILS!

    def get_queryset(self, request):
        return Appointment.objects.select_related('doctor__user')  # FAILS!
```

#### ✅ CORRECT Admin Code
```python
# CORRECT - Uses user_id UUID field
class AppointmentAdmin(TenantModelAdmin):
    def doctor_display(self, obj):
        return f"Dr. (ID: {obj.doctor.user_id})"  # Works!

    def get_queryset(self, request):
        return Appointment.objects.select_related('doctor', 'patient')  # Works!
```

---

## Development Guidelines

### 1. Creating New Models

```python
# Standard template for new models
from django.db import models

class YourModel(models.Model):
    # 1. Tenant ID (REQUIRED)
    tenant_id = models.UUIDField(db_index=True)

    # 2. User references (UUID, not ForeignKey)
    user_id = models.UUIDField(null=True, blank=True, db_index=True)

    # 3. Your fields
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, default='active')

    # 4. Timestamps (ALWAYS include)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 5. Audit trail
    created_by_user_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'your_models'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['tenant_id', 'status']),
        ]
```

### 2. Creating ViewSets

```python
from rest_framework import viewsets
from common.mixins import TenantViewSetMixin

class YourViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = YourModel.objects.all()
    serializer_class = YourSerializer

    def perform_create(self, serializer):
        # Auto-set creator
        serializer.save(created_by_user_id=self.request.user_id)
```

### 3. Creating Serializers

```python
from rest_framework import serializers
from common.mixins import TenantMixin

class YourSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = YourModel
        fields = '__all__'
        read_only_fields = ['tenant_id', 'created_by_user_id']
```

### 4. Accessing User Information

```python
# In views
def some_view(request):
    user_id = request.user_id          # UUID from JWT
    email = request.email              # User's email
    tenant_id = request.tenant_id      # Tenant UUID
    is_patient = request.is_patient    # True/False

    # Check permission
    if check_permission(request, HMSPermissions.PATIENTS_CREATE):
        # User has permission
        pass
```

### 5. Testing

```bash
# Start server
python manage.py runserver 0.0.0.0:8002

# Test admin login
# Visit: http://localhost:8002/admin/
# Login with SuperAdmin credentials

# Test API with JWT
TOKEN="your-jwt-token-from-superadmin"
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8002/api/patients/
```

---

## Common Pitfalls & Solutions

### ❌ Pitfall 1: Trying to use Django User model

**Problem**:
```python
from django.contrib.auth import get_user_model
User = get_user_model()

class DoctorProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # ERROR!
```

**Solution**:
```python
class DoctorProfile(models.Model):
    user_id = models.UUIDField(unique=True, db_index=True)  # CORRECT
```

### ❌ Pitfall 2: Using Django permissions

**Problem**:
```python
from rest_framework.permissions import DjangoModelPermissions

class PatientViewSet(viewsets.ModelViewSet):
    permission_classes = [DjangoModelPermissions]  # Won't work!
```

**Solution**:
```python
from common.permissions import check_permission, HMSPermissions

class PatientViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        if not check_permission(self.request, HMSPermissions.PATIENTS_VIEW):
            raise PermissionDenied()
        return super().get_queryset()
```

### ❌ Pitfall 3: Forgetting tenant_id in models

**Problem**:
```python
class MyModel(models.Model):
    name = models.CharField(max_length=200)
    # Missing tenant_id!
```

**Solution**:
```python
class MyModel(models.Model):
    tenant_id = models.UUIDField(db_index=True)  # REQUIRED
    name = models.CharField(max_length=200)
```

### ❌ Pitfall 4: Admin trying to access .user

**Problem**:
```python
class AppointmentAdmin(admin.ModelAdmin):
    def doctor_name(self, obj):
        return obj.doctor.user.get_full_name()  # ERROR! No .user
```

**Solution**:
```python
class AppointmentAdmin(TenantModelAdmin):
    def doctor_name(self, obj):
        return f"Doctor (ID: {obj.doctor.user_id})"  # CORRECT
```

### ❌ Pitfall 5: Not using TenantMixin in serializers

**Problem**:
```python
class MySerializer(serializers.ModelSerializer):
    class Meta:
        model = MyModel
        fields = '__all__'

    def create(self, validated_data):
        # tenant_id not set!
        return MyModel.objects.create(**validated_data)
```

**Solution**:
```python
from common.mixins import TenantMixin

class MySerializer(TenantMixin, serializers.ModelSerializer):
    # TenantMixin automatically sets tenant_id from request
    class Meta:
        model = MyModel
        fields = '__all__'
        read_only_fields = ['tenant_id']
```

### ❌ Pitfall 6: select_related('user')

**Problem**:
```python
queryset = DoctorProfile.objects.select_related('user')  # ERROR!
```

**Solution**:
```python
queryset = DoctorProfile.objects.all()  # user_id is a UUID field, not ForeignKey
```

---

## Environment Configuration

### Required .env Variables

```bash
# Django Core
SECRET_KEY=your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/dghms

# SuperAdmin Integration (CRITICAL)
SUPERADMIN_URL=https://admin.celiyo.com
JWT_SECRET_KEY=your-jwt-secret-key-must-match-superadmin
JWT_ALGORITHM=HS256
JWT_LEEWAY=30

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,https://admin.celiyo.com
```

### Settings Configuration

```python
# hms/settings.py

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'django_filters',
    'corsheaders',

    # Common (MUST be first local app)
    'common',

    # HMS Apps
    'apps.patients',
    'apps.doctors',
    'apps.appointments',
    'apps.hospital',
    'apps.pharmacy',
    'apps.orders',
    'apps.payments',
    'apps.opd',
    'apps.services',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'common.middleware.JWTAuthenticationMiddleware',  # JWT middleware
    'common.middleware.CustomAuthenticationMiddleware',  # Custom auth
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'common.auth_backends.SuperAdminAuthBackend',
    'common.auth_backends.JWTAuthBackend',
]

# NO AUTH_USER_MODEL - We don't use Django User!
# AUTH_USER_MODEL = 'accounts.User'  # REMOVED

# JWT Configuration
JWT_SECRET_KEY = config('JWT_SECRET_KEY')
JWT_ALGORITHM = config('JWT_ALGORITHM', default='HS256')
JWT_LEEWAY = config('JWT_LEEWAY', default=30, cast=int)

# SuperAdmin URL
SUPERADMIN_URL = config('SUPERADMIN_URL')
```

---

## Quick Reference

### Field Naming Conventions

```python
# Tenant and User
tenant_id                    # UUID - REQUIRED on all models
user_id                      # UUID - User reference (not ForeignKey)
created_by_user_id          # UUID - Creator audit trail
updated_by_user_id          # UUID - Last updater
recorded_by_user_id         # UUID - For medical records

# Timestamps
created_at                   # DateTimeField(auto_now_add=True)
updated_at                   # DateTimeField(auto_now=True)
deleted_at                   # DateTimeField (for soft deletes)

# Status
status                       # CharField with choices
is_active                    # BooleanField
is_verified                  # BooleanField
```

### Common Imports

```python
# Models
from django.db import models
import uuid

# ViewSets
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend

# Common mixins
from common.mixins import TenantViewSetMixin, PatientAccessMixin, TenantMixin
from common.permissions import check_permission, HMSPermissions

# Admin
from common.admin_site import TenantModelAdmin, hms_admin_site
```

### Useful Commands

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Run server
python manage.py runserver 0.0.0.0:8002

# Create superuser (NOT USED - use SuperAdmin)
# python manage.py createsuperuser  # DON'T DO THIS

# Collect static files
python manage.py collectstatic
```

---

## Support & Further Reading

- **Migration Guide**: See `MIGRATION_GUIDE.md` for detailed migration instructions
- **Deployment Guide**: See `DEPLOYMENT_STEPS.md` for deployment checklist
- **Project Rules**: See `rules.md` for coding standards and conventions
- **Common Package**: See `common/README.md` for detailed API documentation

---

**Questions or Issues?**

1. Check this documentation first
2. Review the migration and deployment guides
3. Check the common package README
4. Contact SuperAdmin team for JWT/tenant setup

---

**End of Documentation**
