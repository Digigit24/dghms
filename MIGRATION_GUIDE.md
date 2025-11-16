# DigiHMS SuperAdmin Integration - Migration Guide

This guide documents the migration from local authentication to centralized SuperAdmin authentication with tenant isolation.

## Table of Contents
1. [Overview](#overview)
2. [What Has Been Implemented](#what-has-been-implemented)
3. [Next Steps - Adding tenant_id to Models](#next-steps---adding-tenant_id-to-models)
4. [Testing Checklist](#testing-checklist)
5. [Deployment Steps](#deployment-steps)

---

## Overview

DigiHMS is being migrated from local authentication to a centralized SuperAdmin system:

**Before**: DigiHMS had its own User model and authentication
**After**: SuperAdmin handles authentication, DigiHMS validates JWT tokens and manages profiles

### Key Changes
- ✅ JWT-based authentication via SuperAdmin
- ✅ Session-based Django Admin access
- ✅ Tenant isolation via `tenant_id` field
- ✅ Custom permission system from JWT tokens
- ✅ Patient portal support via `is_patient` flag

---

## What Has Been Implemented

### 1. Common Infrastructure (`common/` folder)

All files have been created with HMS-specific configuration:

- **middleware.py** - JWT authentication middleware (checks for 'hms' module)
- **auth_backends.py** - TenantUser class and SuperAdmin authentication
- **admin_site.py** - Custom admin site with tenant filtering
- **permissions.py** - HMS-specific permission constants and checking
- **mixins.py** - TenantMixin and PatientAccessMixin for ViewSets
- **views.py** - Authentication proxy views (login, logout, token validation)
- **urls.py** - Authentication routes

### 2. Settings Configuration

`hms/settings.py` has been updated with:

- ✅ `common` app added to INSTALLED_APPS
- ✅ JWT middleware added
- ✅ Authentication backends configured
- ✅ JWT settings (JWT_SECRET_KEY, JWT_ALGORITHM)
- ✅ SuperAdmin URL configuration
- ✅ Session settings for admin
- ✅ CORS headers for tenant isolation
- ✅ DATABASE_URL support

### 3. Templates

- ✅ Custom login page at `templates/admin/login.html`

### 4. Environment Variables

- ✅ `.env.example` updated with all required variables

---

## Next Steps - Adding tenant_id to Models

### Phase 1: Add tenant_id Field to All Models

Every model needs a `tenant_id` field for data isolation. Here's how:

#### 1.1 Update Model Definitions

For each model in your apps, add the `tenant_id` field:

```python
from django.db import models
import uuid

class YourModel(models.Model):
    # Add this field to EVERY model
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant this record belongs to"
    )

    # ... rest of your fields ...

    class Meta:
        # Add tenant_id to indexes for better query performance
        indexes = [
            models.Index(fields=['tenant_id']),
            # ... other indexes ...
        ]
```

#### 1.2 Models That Need tenant_id

Update these models in order:

**apps/patients/models.py**:
- ✅ PatientProfile
- ✅ PatientVitals
- ✅ PatientAllergy

**apps/doctors/models.py**:
- ✅ Specialty
- ✅ DoctorProfile
- ✅ DoctorAvailability

**apps/appointments/models.py**:
- ✅ Appointment
- ✅ AppointmentStatus (if exists)

**apps/hospital/models.py**:
- ✅ Hospital
- ✅ Department
- ✅ Ward (if exists)

**apps/pharmacy/models.py**:
- ✅ Medicine
- ✅ MedicineStock
- ✅ Prescription

**apps/orders/models.py**:
- ✅ Order
- ✅ OrderItem

**apps/payments/models.py**:
- ✅ Payment
- ✅ PaymentMethod

**apps/opd/models.py**:
- ✅ OPDVisit
- ✅ OPDPrescription

**apps/services/models.py**:
- ✅ Service
- ✅ ServiceCategory

### Phase 2: Create Migrations

After adding `tenant_id` to all models:

```bash
# Create migrations
python manage.py makemigrations

# Review the migration files
# They should add tenant_id fields with db_index=True

# Apply migrations
python manage.py migrate
```

### Phase 3: Update Serializers

For each serializer, use the `TenantMixin`:

```python
from common.mixins import TenantMixin

class YourModelSerializer(TenantMixin, serializers.ModelSerializer):
    class Meta:
        model = YourModel
        fields = ['id', 'tenant_id', 'name', ...]  # Include tenant_id in fields
        read_only_fields = ['tenant_id']  # Make it read-only for clients
```

### Phase 4: Update ViewSets

For each ViewSet, use `TenantViewSetMixin`:

```python
from common.mixins import TenantViewSetMixin, PatientAccessMixin
from common.permissions import PermissionRequiredMixin, HMSPermissions

class YourModelViewSet(
    TenantViewSetMixin,
    PatientAccessMixin,  # For patient-related models
    PermissionRequiredMixin,
    viewsets.ModelViewSet
):
    queryset = YourModel.objects.all()
    serializer_class = YourModelSerializer

    # Define permissions for each action
    permission_map = {
        'list': HMSPermissions.PATIENTS_VIEW,
        'retrieve': HMSPermissions.PATIENTS_VIEW,
        'create': HMSPermissions.PATIENTS_CREATE,
        'update': HMSPermissions.PATIENTS_EDIT,
        'partial_update': HMSPermissions.PATIENTS_EDIT,
        'destroy': HMSPermissions.PATIENTS_DELETE,
    }
```

### Phase 5: Refactor User References

#### Current State
Models currently reference `settings.AUTH_USER_MODEL`:

```python
user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
```

#### Target State
Change to use `user_id` (UUID from SuperAdmin):

```python
# Replace ForeignKey with UUIDField
user_id = models.UUIDField(
    db_index=True,
    help_text="User ID from SuperAdmin"
)
```

#### Migration Strategy for User Fields

**Option 1: Gradual Migration (Recommended)**
1. Add `user_id` field alongside existing `user` field
2. Write data migration to copy user IDs
3. Make `user` field nullable
4. Deprecate `user` field in code
5. Remove `user` field after full migration

**Option 2: Direct Migration (Breaking Change)**
1. Backup database
2. Replace `user` ForeignKey with `user_id` UUIDField
3. Update all code references
4. Run migrations

---

## Testing Checklist

Before going to production, verify:

### Environment Setup
- [ ] `.env` file created from `.env.example`
- [ ] `DATABASE_URL` configured correctly
- [ ] `JWT_SECRET_KEY` matches SuperAdmin
- [ ] `SUPERADMIN_URL` points to correct SuperAdmin instance

### Authentication
- [ ] SuperAdmin login works (`/admin/`)
- [ ] JWT token validation works for API requests
- [ ] Session persists across page loads
- [ ] Logout clears session properly
- [ ] Invalid tokens are rejected

### Tenant Isolation
- [ ] Creating records sets `tenant_id` automatically
- [ ] Queries filter by `tenant_id` automatically
- [ ] Different tenants see different data
- [ ] Cannot access other tenant's data

### Permissions
- [ ] Permission checking works from JWT
- [ ] Users without HMS module are denied
- [ ] Staff users see appropriate data
- [ ] Patient users only see their own data

### Admin Panel
- [ ] Static files load (CSS, JS, images)
- [ ] Tenant information displays correctly
- [ ] Model admins show tenant-filtered data
- [ ] Creating records via admin sets tenant_id

---

## Deployment Steps

### 1. Update Environment Variables

```bash
# Add to .env
JWT_SECRET_KEY=<get-from-superadmin-team>
SUPERADMIN_URL=https://admin.celiyo.com
DATABASE_URL=postgresql://user:pass@host:port/db
```

### 2. Install Dependencies

```bash
pip install PyJWT requests dj-database-url
```

### 3. Run Migrations

```bash
# After adding tenant_id to models
python manage.py makemigrations
python manage.py migrate
```

### 4. Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### 5. Test Authentication

```bash
# Start server
python manage.py runserver 0.0.0.0:8002

# Test login at http://localhost:8002/admin/
# Use SuperAdmin credentials
```

### 6. Create SuperAdmin Users

Work with SuperAdmin team to:
1. Create tenant for your hospital
2. Create staff users with HMS module enabled
3. Configure permissions for different roles
4. Get JWT_SECRET_KEY for your environment

---

## Common Issues & Solutions

### Issue: "JWT_SECRET_KEY not configured"
**Solution**: Add `JWT_SECRET_KEY` to `.env` file (must match SuperAdmin)

### Issue: "HMS module not enabled for this user"
**Solution**: Contact SuperAdmin team to enable HMS module for the user's tenant

### Issue: "No tenant_id in request"
**Solution**: Ensure JWT middleware is properly configured in `MIDDLEWARE` setting

### Issue: "Static files not loading"
**Solution**: Run `python manage.py collectstatic` and check `STATIC_ROOT` setting

### Issue: "Cannot create records (tenant_id missing)"
**Solution**: Use `TenantMixin` in serializers and `TenantViewSetMixin` in ViewSets

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     SuperAdmin (Port 8000)                   │
│  - User Management                                           │
│  - Tenant Management                                         │
│  - JWT Token Generation                                      │
│  - Permission Management                                     │
└──────────────────────┬──────────────────────────────────────┘
                       │ JWT Tokens
                       │ User Data
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     DigiHMS (Port 8002)                      │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  JWT Middleware                                     │    │
│  │  - Validates tokens                                 │    │
│  │  - Extracts tenant_id                              │    │
│  │  - Checks HMS module                               │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Common Layer                                       │    │
│  │  - TenantMixin (auto tenant_id)                    │    │
│  │  - PatientAccessMixin (own data only)             │    │
│  │  - Permission checking                             │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Business Logic                                     │    │
│  │  - Patient Management                              │    │
│  │  - Doctor Management                               │    │
│  │  - Appointments, OPD, Pharmacy, etc.              │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Database (PostgreSQL)                             │    │
│  │  - All tables have tenant_id                       │    │
│  │  - Automatic tenant filtering                      │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Next Actions Required

1. **Update Models** - Add `tenant_id` to all models (see Phase 1 above)
2. **Create Migrations** - Generate and apply database migrations
3. **Update Serializers** - Use `TenantMixin` in all serializers
4. **Update ViewSets** - Use `TenantViewSetMixin` and permission checking
5. **Refactor User References** - Change from ForeignKey to user_id UUIDField
6. **Test Thoroughly** - Verify tenant isolation and permissions work
7. **Coordinate with SuperAdmin Team** - Get JWT keys and create test users

---

## Support

For questions or issues:
1. Check this migration guide
2. Review DigiCRM reference implementation
3. Contact SuperAdmin team for JWT/tenant setup
4. Review common/ code for implementation examples

---

**Last Updated**: 2025-11-16
**Status**: Phase 1 Complete (Common Infrastructure) - Phase 2 Pending (Model Updates)
