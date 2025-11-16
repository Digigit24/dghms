# Common HMS Components

This package provides shared infrastructure for SuperAdmin integration in DigiHMS.

## Overview

The `common` package implements JWT-based authentication, tenant isolation, and permission management for DigiHMS integration with a centralized SuperAdmin application.

## Components

### 1. Middleware (`middleware.py`)

**JWTAuthenticationMiddleware** - Validates JWT tokens and sets request attributes

```python
# Automatically applied to all API requests
# Public paths (admin, static, etc.) are exempted
# Sets request attributes:
#   - request.user_id
#   - request.email
#   - request.tenant_id
#   - request.tenant_slug
#   - request.is_patient
#   - request.permissions
```

### 2. Authentication Backends (`auth_backends.py`)

**TenantUser** - User class without database model
```python
# Mimics Django User for admin access
# Populated from JWT payload or SuperAdmin API
```

**SuperAdminAuthBackend** - Authenticates against SuperAdmin
```python
# Used for admin login
# Validates credentials with SuperAdmin API
# Returns TenantUser instance
```

**JWTAuthBackend** - Authenticates via JWT token
```python
# Used for API requests
# Decodes and validates JWT tokens
# Returns TenantUser instance
```

### 3. Permissions (`permissions.py`)

**HMSPermissions** - Permission constants
```python
from common.permissions import HMSPermissions

# Available permissions:
HMSPermissions.PATIENTS_VIEW
HMSPermissions.PATIENTS_CREATE
HMSPermissions.DOCTORS_VIEW
HMSPermissions.APPOINTMENTS_CREATE
# ... and more
```

**Permission Checking Functions**
```python
from common.permissions import check_permission, permission_required

# Check permission in view
if check_permission(request, HMSPermissions.PATIENTS_VIEW):
    # User has permission
    pass

# Decorator for function-based views
@permission_required(HMSPermissions.PATIENTS_CREATE)
def create_patient(request):
    pass
```

**PermissionRequiredMixin** - For ViewSets
```python
from common.permissions import PermissionRequiredMixin, HMSPermissions

class PatientViewSet(PermissionRequiredMixin, viewsets.ModelViewSet):
    permission_map = {
        'list': HMSPermissions.PATIENTS_VIEW,
        'create': HMSPermissions.PATIENTS_CREATE,
        'update': HMSPermissions.PATIENTS_EDIT,
        'destroy': HMSPermissions.PATIENTS_DELETE,
    }
```

### 4. Mixins (`mixins.py`)

**TenantMixin** - Automatic tenant_id handling in serializers
```python
from common.mixins import TenantMixin

class PatientSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ['id', 'name', 'tenant_id', ...]
        read_only_fields = ['tenant_id']
```

**TenantViewSetMixin** - Automatic tenant filtering in ViewSets
```python
from common.mixins import TenantViewSetMixin

class PatientViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = Patient.objects.all()  # Auto-filtered by tenant_id
```

**PatientAccessMixin** - Restrict patients to own records
```python
from common.mixins import PatientAccessMixin

class PatientViewSet(PatientAccessMixin, TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = Patient.objects.all()
    # Patients only see their own records
    # Staff see all records for their tenant
```

### 5. Admin Site (`admin_site.py`)

**HMSAdminSite** - Custom admin with tenant support
```python
from common.admin_site import hms_admin_site

# Already configured as default admin site
# Automatically filters models by tenant_id
```

**TenantModelAdmin** - Base ModelAdmin class
```python
from common.admin_site import TenantModelAdmin

class PatientAdmin(TenantModelAdmin):
    list_display = ['name', 'tenant_id', ...]
    # Auto-filters by tenant_id
    # Auto-sets tenant_id on creation
```

### 6. Views (`views.py`)

Authentication endpoints:
- `/auth/login/` - Admin login page
- `/auth/proxy-login/` - SuperAdmin login proxy (CORS workaround)
- `/auth/token-login/` - JWT token login for frontend
- `/auth/logout/` - Logout and clear session
- `/auth/health/` - Health check endpoint

## Usage Examples

### Example ViewSet with Full Integration

```python
from rest_framework import viewsets
from common.mixins import TenantViewSetMixin, PatientAccessMixin
from common.permissions import PermissionRequiredMixin, HMSPermissions
from .models import Patient
from .serializers import PatientSerializer

class PatientViewSet(
    TenantViewSetMixin,      # Auto tenant filtering
    PatientAccessMixin,       # Patient access control
    PermissionRequiredMixin,  # Permission checking
    viewsets.ModelViewSet
):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer

    permission_map = {
        'list': HMSPermissions.PATIENTS_VIEW,
        'retrieve': HMSPermissions.PATIENTS_VIEW,
        'create': HMSPermissions.PATIENTS_CREATE,
        'update': HMSPermissions.PATIENTS_EDIT,
        'partial_update': HMSPermissions.PATIENTS_EDIT,
        'destroy': HMSPermissions.PATIENTS_DELETE,
    }
```

### Example Serializer with Tenant Handling

```python
from rest_framework import serializers
from common.mixins import TenantMixin
from .models import Patient

class PatientSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ['id', 'tenant_id', 'name', 'email', ...]
        read_only_fields = ['tenant_id']  # Set automatically from request
```

### Example Model with tenant_id

```python
from django.db import models

class Patient(models.Model):
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant this patient belongs to"
    )
    name = models.CharField(max_length=200)
    # ... other fields ...

    class Meta:
        indexes = [
            models.Index(fields=['tenant_id']),
        ]
```

## Configuration

### Required Settings

```python
# hms/settings.py

INSTALLED_APPS = [
    # ... other apps ...
    'common',  # Must be before local apps
    'apps.accounts',
    # ... other local apps ...
]

MIDDLEWARE = [
    # ... other middleware ...
    'common.middleware.JWTAuthenticationMiddleware',
    # ... other middleware ...
]

AUTHENTICATION_BACKENDS = [
    'common.auth_backends.SuperAdminAuthBackend',
    'common.auth_backends.JWTAuthBackend',
]

# JWT Settings
JWT_SECRET_KEY = config('JWT_SECRET_KEY')
JWT_ALGORITHM = config('JWT_ALGORITHM', default='HS256')

# SuperAdmin Integration
SUPERADMIN_URL = config('SUPERADMIN_URL')
```

### Required Environment Variables

```bash
# .env
JWT_SECRET_KEY=your-jwt-secret-key-must-match-superadmin
JWT_ALGORITHM=HS256
SUPERADMIN_URL=https://admin.celiyo.com
```

## JWT Token Payload

The JWT token from SuperAdmin contains:

```json
{
  "user_id": "uuid-string",
  "email": "user@example.com",
  "tenant_id": "tenant-uuid",
  "tenant_slug": "hospital-name",
  "user_type": "staff|patient",
  "is_patient": false,
  "is_super_admin": false,
  "permissions": {
    "hms.patients.view": "all|team|own",
    "hms.patients.create": true,
    "hms.doctors.view": "all"
  },
  "enabled_modules": ["hms"],
  "database_url": "postgresql://..."
}
```

## Permission Scopes

Permissions can have different scopes:

- **Boolean**: `true` (allowed) or `false` (denied)
- **"all"**: User can see all records in their tenant
- **"team"**: User can see team records (future implementation)
- **"own"**: User can only see their own records

Example:
```python
# Staff user with "all" scope
permissions = {
    "hms.patients.view": "all"  # Can view all patients in tenant
}

# Patient user with "own" scope
permissions = {
    "hms.patients.view": "own"  # Can only view own patient record
}
```

## File Structure

```
common/
├── __init__.py           # Package initialization
├── apps.py              # App configuration
├── middleware.py        # JWT authentication middleware
├── auth_backends.py     # TenantUser and authentication backends
├── permissions.py       # Permission constants and checking
├── mixins.py           # Serializer and ViewSet mixins
├── admin_site.py       # Custom admin site
├── views.py            # Authentication views
├── urls.py             # URL routing
└── README.md           # This file
```

## Testing

### Test Authentication
```bash
# Start server
python manage.py runserver

# Visit admin
http://localhost:8002/admin/

# Login with SuperAdmin credentials
```

### Test API with JWT
```bash
# Get JWT token from SuperAdmin
TOKEN="your-jwt-token"

# Make API request
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8002/api/patients/
```

## Troubleshooting

### "JWT_SECRET_KEY not configured"
- Add `JWT_SECRET_KEY` to `.env` file
- Must match SuperAdmin configuration

### "HMS module not enabled for this user"
- Contact SuperAdmin team
- Enable HMS module for tenant

### "Authorization header required"
- Add `Authorization: Bearer <token>` header
- Or access via public paths (/admin/, /static/)

### "No tenant_id in request"
- Check JWT middleware is in `MIDDLEWARE` setting
- Verify JWT token contains `tenant_id`

## Support

See `MIGRATION_GUIDE.md` for full migration instructions and examples.
