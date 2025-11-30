# HMS API Endpoint Documentation

## Complete API Endpoint Reference

This document provides a comprehensive list of all available API endpoints in the HMS application.

---

## Authentication Endpoints

**Base URL:** `/api/auth/`

### Session Management

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/auth/login/` | User login | No |
| POST | `/api/auth/logout/` | User logout | Yes |
| POST | `/api/auth/token/refresh/` | Refresh JWT token | No |
| POST | `/api/auth/token/verify/` | Verify JWT token | No |
| GET | `/api/auth/me/` | Get current user info | Yes |

### User Management (CRUD)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/auth/users/` | List all users in tenant | Yes |
| POST | `/api/auth/users/` | Create new user | Yes |
| GET | `/api/auth/users/{id}/` | Get user details | Yes |
| PUT | `/api/auth/users/{id}/` | Update user (full) | Yes |
| PATCH | `/api/auth/users/{id}/` | Update user (partial) | Yes |
| DELETE | `/api/auth/users/{id}/` | Delete user (soft delete) | Yes |
| POST | `/api/auth/users/{id}/assign_roles/` | Assign roles to user | Yes |

**Query Parameters for List:**
- `page`: Page number
- `page_size`: Items per page (default: 20, max: 100)
- `search`: Search by email/name
- `is_active`: Filter by active status
- `role_id`: Filter by role UUID
- `ordering`: Order by field

---

## Doctor Management Endpoints

**Base URL:** `/api/doctors/`

### Specialties

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/doctors/specialties/` | List all specialties | Yes |
| POST | `/api/doctors/specialties/` | Create specialty | Yes |
| GET | `/api/doctors/specialties/{id}/` | Get specialty details | Yes |
| PUT | `/api/doctors/specialties/{id}/` | Update specialty (full) | Yes |
| PATCH | `/api/doctors/specialties/{id}/` | Update specialty (partial) | Yes |
| DELETE | `/api/doctors/specialties/{id}/` | Delete specialty | Yes |

**Query Parameters for List:**
- `is_active`: Filter by active status
- `department`: Filter by department
- `search`: Search by name, code, description

### Doctor Profiles

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/doctors/profiles/` | List doctor profiles | Yes |
| POST | `/api/doctors/profiles/` | Create doctor profile | Yes |
| GET | `/api/doctors/profiles/{id}/` | Get doctor details | Yes |
| PUT | `/api/doctors/profiles/{id}/` | Update doctor (full) | Yes |
| PATCH | `/api/doctors/profiles/{id}/` | Update doctor (partial) | Yes |
| DELETE | `/api/doctors/profiles/{id}/` | Deactivate doctor | Yes |

**Query Parameters for List:**
- `specialty`: Filter by specialty name
- `status`: Filter by status (active, on_leave, inactive)
- `available`: Filter active doctors only
- `city`: Filter by city
- `min_rating`: Minimum average rating
- `min_fee`: Minimum consultation fee
- `max_fee`: Maximum consultation fee
- `search`: Search by name, license, qualifications

### Doctor Custom Actions

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/doctors/profiles/register/` | Register doctor with user account (OLD) | No |
| POST | `/api/doctors/profiles/create_with_user/` | Create doctor with auto-user creation (NEW) | Yes |
| GET | `/api/doctors/profiles/{id}/availability/` | Get doctor availability | Yes |
| POST | `/api/doctors/profiles/{id}/set_availability/` | Add availability slot | Yes |
| GET | `/api/doctors/profiles/statistics/` | Get doctor statistics | Yes |
| POST | `/api/doctors/profiles/{id}/activate/` | Activate doctor profile | Yes |
| POST | `/api/doctors/profiles/{id}/deactivate/` | Deactivate doctor profile | Yes |

#### Create Doctor with User (Recommended)

**Endpoint:** `POST /api/doctors/profiles/create_with_user/`

**Two Modes:**

**Mode 1: Auto-create user** (`create_user: true`)
```json
{
  "create_user": true,
  "email": "doctor@hospital.com",
  "password": "SecurePass123",
  "password_confirm": "SecurePass123",
  "first_name": "Dr. Rajesh",
  "last_name": "Kumar",
  "phone": "+919876543210",
  "role_ids": ["role-uuid"],
  "medical_license_number": "MED123456",
  "license_issuing_authority": "Medical Council of India",
  "license_issue_date": "2020-01-01",
  "license_expiry_date": "2030-01-01",
  "qualifications": "MBBS, MD - Cardiology",
  "specialty_ids": [1, 2],
  "years_of_experience": 5,
  "consultation_fee": 500.00,
  "consultation_duration": 30
}
```

**Mode 2: Link to existing user** (`create_user: false`)
```json
{
  "create_user": false,
  "user_id": "existing-user-uuid",
  "medical_license_number": "MED789012",
  "license_issuing_authority": "Medical Council of India",
  "license_issue_date": "2019-01-01",
  "license_expiry_date": "2029-01-01",
  "qualifications": "MBBS, MD",
  "specialty_ids": [1],
  "years_of_experience": 3,
  "consultation_fee": 300.00
}
```

---

## Patient Management Endpoints

**Base URL:** `/api/patients/`

### Patient Profiles

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/patients/profiles/` | List patient profiles | Yes |
| POST | `/api/patients/profiles/` | Create patient profile | Yes |
| GET | `/api/patients/profiles/{id}/` | Get patient details | Yes |
| PUT | `/api/patients/profiles/{id}/` | Update patient (full) | Yes |
| PATCH | `/api/patients/profiles/{id}/` | Update patient (partial) | Yes |
| DELETE | `/api/patients/profiles/{id}/` | Delete patient | Yes |

### Patient Custom Actions

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/patients/profiles/statistics/` | Get patient statistics | Yes |
| GET | `/api/patients/profiles/{id}/vitals/` | Get patient vitals history | Yes |
| POST | `/api/patients/profiles/{id}/add_vitals/` | Add vital signs | Yes |
| GET | `/api/patients/profiles/{id}/allergies/` | Get patient allergies | Yes |
| POST | `/api/patients/profiles/{id}/add_allergy/` | Add allergy | Yes |
| GET | `/api/patients/profiles/search_by_id/` | Search by patient ID | Yes |

### Patient Vitals

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/patients/vitals/` | List vitals | Yes |
| POST | `/api/patients/vitals/` | Create vital record | Yes |
| GET | `/api/patients/vitals/{id}/` | Get vital details | Yes |
| PUT | `/api/patients/vitals/{id}/` | Update vital (full) | Yes |
| PATCH | `/api/patients/vitals/{id}/` | Update vital (partial) | Yes |
| DELETE | `/api/patients/vitals/{id}/` | Delete vital | Yes |

### Patient Allergies

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/patients/allergies/` | List allergies | Yes |
| POST | `/api/patients/allergies/` | Create allergy record | Yes |
| GET | `/api/patients/allergies/{id}/` | Get allergy details | Yes |
| PUT | `/api/patients/allergies/{id}/` | Update allergy (full) | Yes |
| PATCH | `/api/patients/allergies/{id}/` | Update allergy (partial) | Yes |
| DELETE | `/api/patients/allergies/{id}/` | Delete allergy | Yes |

---

## Appointment Management Endpoints

**Base URL:** `/api/appointments/`

### Appointments

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/appointments/` | List appointments | Yes |
| POST | `/api/appointments/` | Create appointment | Yes |
| GET | `/api/appointments/{id}/` | Get appointment details | Yes |
| PUT | `/api/appointments/{id}/` | Update appointment (full) | Yes |
| PATCH | `/api/appointments/{id}/` | Update appointment (partial) | Yes |
| DELETE | `/api/appointments/{id}/` | Cancel appointment | Yes |

### Appointment Custom Actions

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/appointments/statistics/` | Get appointment statistics | Yes |
| GET | `/api/appointments/today/` | Get today's appointments | Yes |
| POST | `/api/appointments/{id}/confirm/` | Confirm appointment | Yes |
| POST | `/api/appointments/{id}/cancel/` | Cancel appointment | Yes |
| POST | `/api/appointments/{id}/complete/` | Mark appointment as completed | Yes |
| POST | `/api/appointments/{id}/no_show/` | Mark as no-show | Yes |
| POST | `/api/appointments/{id}/reschedule/` | Reschedule appointment | Yes |

---

## Payment Management Endpoints

**Base URL:** `/api/payments/`

### Payment Categories

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/payments/categories/` | List payment categories | Yes |
| POST | `/api/payments/categories/` | Create payment category (Admin) | Yes |
| GET | `/api/payments/categories/{id}/` | Get category details | Yes |
| PUT | `/api/payments/categories/{id}/` | Update category (full) | Yes |
| PATCH | `/api/payments/categories/{id}/` | Update category (partial) | Yes |
| DELETE | `/api/payments/categories/{id}/` | Delete category | Yes |

**Query Parameters for List:**
- `category_type`: Filter by category type (income, expense, refund, adjustment)
- `search`: Search by name, description

### Transactions

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/payments/transactions/` | List financial transactions | Yes |
| POST | `/api/payments/transactions/` | Create transaction | Yes |
| GET | `/api/payments/transactions/{id}/` | Get transaction details | Yes |
| PUT | `/api/payments/transactions/{id}/` | Update transaction (full) | Yes |
| PATCH | `/api/payments/transactions/{id}/` | Update transaction (partial) | Yes |
| DELETE | `/api/payments/transactions/{id}/` | Delete transaction | Yes |

**Query Parameters for List:**
- `transaction_type`: Filter by type (payment, refund, expense, adjustment)
- `payment_method`: Filter by payment method (cash, card, upi, etc.)
- `category`: Filter by payment category ID
- `date_from`: Transactions from date (YYYY-MM-DD)
- `date_to`: Transactions to date (YYYY-MM-DD)
- `min_amount`: Minimum transaction amount
- `max_amount`: Maximum transaction amount
- `is_reconciled`: Filter by reconciliation status

### Transaction Custom Actions

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/payments/transactions/statistics/` | Get transaction statistics (Admin) | Yes |
| POST | `/api/payments/transactions/{id}/reconcile/` | Mark transaction as reconciled (Admin) | Yes |

### Accounting Periods

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/payments/accounting-periods/` | List accounting periods | Yes |
| POST | `/api/payments/accounting-periods/` | Create accounting period (Admin) | Yes |
| GET | `/api/payments/accounting-periods/{id}/` | Get period details | Yes |
| PUT | `/api/payments/accounting-periods/{id}/` | Update period (full) | Yes |
| PATCH | `/api/payments/accounting-periods/{id}/` | Update period (partial) | Yes |
| DELETE | `/api/payments/accounting-periods/{id}/` | Delete period | Yes |

**Query Parameters for List:**
- `period_type`: Filter by period type (monthly, quarterly, annual)
- `is_closed`: Filter by closed status
- `date_from`: Periods starting from (YYYY-MM-DD)
- `date_to`: Periods ending by (YYYY-MM-DD)

### Accounting Period Custom Actions

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/payments/accounting-periods/{id}/recalculate/` | Recalculate financial summary (Admin) | Yes |
| POST | `/api/payments/accounting-periods/{id}/close/` | Close accounting period (Admin) | Yes |

---

## Order Management Endpoints

**Base URL:** `/api/orders/`

### Orders

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/orders/` | List orders | Yes |
| POST | `/api/orders/` | Create order | Yes |
| GET | `/api/orders/{id}/` | Get order details | Yes |
| PUT | `/api/orders/{id}/` | Update order (full) | Yes |
| PATCH | `/api/orders/{id}/` | Update order (partial) | Yes |
| DELETE | `/api/orders/{id}/` | Cancel order | Yes |

### Order Custom Actions

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/orders/statistics/` | Get order statistics | Yes |
| POST | `/api/orders/{id}/confirm/` | Confirm order | Yes |
| POST | `/api/orders/{id}/cancel/` | Cancel order | Yes |
| POST | `/api/orders/{id}/complete/` | Mark order as completed | Yes |

---

## URL Configuration Summary

All URLs are properly configured using Django REST Framework's `DefaultRouter`, which automatically generates the following URL patterns for each ViewSet:

### Standard CRUD URLs (Auto-generated by DefaultRouter)

For each registered ViewSet, the router creates:

```
GET    /{resource}/              -> list()
POST   /{resource}/              -> create()
GET    /{resource}/{id}/         -> retrieve()
PUT    /{resource}/{id}/         -> update()
PATCH  /{resource}/{id}/         -> partial_update()
DELETE /{resource}/{id}/         -> destroy()
```

### Custom Action URLs (Auto-generated from @action decorators)

For `@action(detail=False)`:
```
{METHOD}  /{resource}/{action_name}/
```

For `@action(detail=True)`:
```
{METHOD}  /{resource}/{id}/{action_name}/
```

---

## Authentication & Authorization

### Headers Required

All authenticated endpoints require:
```
Authorization: Bearer <jwt_access_token>
```

### Tenant Isolation

All operations are automatically filtered by the `tenant_id` extracted from your JWT token. You can only access resources belonging to your tenant.

### Permissions

Permissions are managed through the `HMSPermission` class, which checks JWT token permissions for each module:
- `hms.doctors.*` - Doctor module permissions
- `hms.patients.*` - Patient module permissions
- `hms.appointments.*` - Appointment module permissions
- `hms.payments.*` - Payment module permissions
- `hms.orders.*` - Order module permissions

---

## URL Configuration Files

### Auth URLs (`apps/auth/urls.py`)
- Authentication endpoints (login, logout, token management)
- User CRUD operations via `UserViewSet`
- Uses `DefaultRouter` for automatic URL generation

### Doctor URLs (`apps/doctors/urls.py`)
- Doctor profile management via `DoctorProfileViewSet`
- Specialty management via `SpecialtyViewSet`
- Uses `DefaultRouter` for automatic URL generation
- Custom actions: `create_with_user`, `availability`, `statistics`, etc.

### Other Module URLs
All other modules (patients, appointments, payments, orders) follow the same pattern:
- Standard CRUD operations via ViewSets
- Custom actions for specific functionality
- Automatic URL generation via `DefaultRouter`

---

## Testing Endpoints

### Example: List Users
```bash
curl -X GET "http://localhost:8000/api/auth/users/" \
  -H "Authorization: Bearer <your_token>"
```

### Example: Create Doctor with User
```bash
curl -X POST "http://localhost:8000/api/doctors/profiles/create_with_user/" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "create_user": true,
    "email": "doctor@hospital.com",
    "password": "SecurePass123",
    "password_confirm": "SecurePass123",
    "first_name": "Dr. Rajesh",
    "last_name": "Kumar",
    "medical_license_number": "MED123456",
    "license_issuing_authority": "Medical Council of India",
    "license_issue_date": "2020-01-01",
    "license_expiry_date": "2030-01-01",
    "qualifications": "MBBS, MD",
    "specialty_ids": [1],
    "years_of_experience": 5,
    "consultation_fee": 500.00
  }'
```

---

## Notes

- All endpoints use REST conventions
- All list endpoints support pagination
- All datetime fields use ISO 8601 format
- All UUID fields accept standard UUID format
- Error responses follow consistent format with `error` and `details` fields
