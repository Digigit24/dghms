# User Management & Doctor Creation API Documentation

This document describes the new user management and doctor creation features that integrate with the SuperAdmin Django application.

## Table of Contents
- [Overview](#overview)
- [Authentication](#authentication)
- [User CRUD Operations](#user-crud-operations)
- [Doctor Creation with Auto-User Creation](#doctor-creation-with-auto-user-creation)
- [Examples](#examples)

---

## Overview

The HMS application now supports full user management capabilities by leveraging the SuperAdmin API. All user operations are proxied to the SuperAdmin Django application with proper tenant isolation.

### Key Features:
- ✅ Create, Read, Update, Delete users in your tenant
- ✅ Auto-create user accounts when creating doctor profiles
- ✅ Automatic tenant isolation (users are scoped to your logged-in tenant)
- ✅ Role assignment support
- ✅ Comprehensive error handling

---

## Authentication

All endpoints require JWT authentication. Include the JWT token in the Authorization header:

```bash
Authorization: Bearer <your_jwt_access_token>
```

The tenant_id is automatically extracted from your JWT token.

---

## User CRUD Operations

Base URL: `/api/auth/users/`

### 1. List Users

Get all users in your tenant.

**Endpoint:** `GET /api/auth/users/`

**Query Parameters:**
- `page` (integer): Page number
- `page_size` (integer): Items per page (default: 20, max: 100)
- `search` (string): Search by email/name
- `is_active` (boolean): Filter by active status
- `role_id` (UUID): Filter by role
- `ordering` (string): Order by field (e.g., 'email', '-date_joined')

**Example Request:**
```bash
curl -X GET "http://localhost:8000/api/auth/users/?page=1&page_size=20&is_active=true" \
  -H "Authorization: Bearer <your_token>"
```

**Example Response:**
```json
{
  "count": 42,
  "next": "http://localhost:8000/api/auth/users/?page=2",
  "previous": null,
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "doctor@hospital.com",
      "phone": "+919876543210",
      "first_name": "John",
      "last_name": "Doe",
      "tenant": "tenant-uuid",
      "tenant_name": "ABC Hospital",
      "roles": [...],
      "is_active": true,
      "date_joined": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

### 2. Create User

Create a new user in your tenant.

**Endpoint:** `POST /api/auth/users/`

**Request Body:**
```json
{
  "email": "newdoctor@hospital.com",
  "password": "SecurePass123",
  "password_confirm": "SecurePass123",
  "first_name": "Jane",
  "last_name": "Smith",
  "phone": "+919876543211",
  "role_ids": ["role-uuid-1", "role-uuid-2"],
  "timezone": "Asia/Kolkata"
}
```

**Required Fields:**
- `email` (string): Valid email address
- `password` (string): Minimum 8 characters
- `password_confirm` (string): Must match password
- `first_name` (string): User's first name

**Optional Fields:**
- `last_name` (string)
- `phone` (string)
- `role_ids` (array of UUIDs): Roles to assign
- `timezone` (string): Default is 'Asia/Kolkata'

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/auth/users/" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newdoctor@hospital.com",
    "password": "SecurePass123",
    "password_confirm": "SecurePass123",
    "first_name": "Jane",
    "last_name": "Smith",
    "phone": "+919876543211"
  }'
```

**Success Response (201 Created):**
```json
{
  "id": "new-user-uuid",
  "email": "newdoctor@hospital.com",
  "first_name": "Jane",
  "last_name": "Smith",
  "phone": "+919876543211",
  "tenant": "tenant-uuid",
  "is_active": true,
  "date_joined": "2024-01-20T14:25:00Z"
}
```

---

### 3. Get User Details

Retrieve details of a specific user.

**Endpoint:** `GET /api/auth/users/{user_id}/`

**Example Request:**
```bash
curl -X GET "http://localhost:8000/api/auth/users/550e8400-e29b-41d4-a716-446655440000/" \
  -H "Authorization: Bearer <your_token>"
```

---

### 4. Update User

Update user information.

**Endpoint:** `PATCH /api/auth/users/{user_id}/` (partial update)
**Endpoint:** `PUT /api/auth/users/{user_id}/` (full update)

**Request Body (PATCH):**
```json
{
  "first_name": "Jane Updated",
  "phone": "+919876543299"
}
```

**Example Request:**
```bash
curl -X PATCH "http://localhost:8000/api/auth/users/550e8400-e29b-41d4-a716-446655440000/" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Jane Updated",
    "phone": "+919876543299"
  }'
```

---

### 5. Delete User

Soft delete a user (sets is_active=False).

**Endpoint:** `DELETE /api/auth/users/{user_id}/`

**Example Request:**
```bash
curl -X DELETE "http://localhost:8000/api/auth/users/550e8400-e29b-41d4-a716-446655440000/" \
  -H "Authorization: Bearer <your_token>"
```

**Success Response (204 No Content):**
```json
{
  "message": "User deleted successfully"
}
```

---

### 6. Assign Roles to User

Assign roles to a user.

**Endpoint:** `POST /api/auth/users/{user_id}/assign_roles/`

**Request Body:**
```json
{
  "role_ids": ["role-uuid-1", "role-uuid-2"]
}
```

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/auth/users/550e8400-e29b-41d4-a716-446655440000/assign_roles/" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "role_ids": ["role-uuid-1", "role-uuid-2"]
  }'
```

---

## Doctor Creation with Auto-User Creation

The doctor creation endpoint now supports automatically creating user accounts in SuperAdmin.

### Endpoint: Create Doctor with User

**URL:** `POST /api/doctors/create_with_user/`

This endpoint supports two modes:

#### Mode 1: Create User + Doctor Profile (Auto-Creation)

Set `create_user: true` to automatically create a user account in SuperAdmin before creating the doctor profile.

**Request Body:**
```json
{
  "create_user": true,
  "email": "doctor@hospital.com",
  "password": "SecurePass123",
  "password_confirm": "SecurePass123",
  "first_name": "Dr. Rajesh",
  "last_name": "Kumar",
  "phone": "+919876543210",
  "role_ids": ["doctor-role-uuid"],
  "timezone": "Asia/Kolkata",
  "medical_license_number": "MED123456",
  "license_issuing_authority": "Medical Council of India",
  "license_issue_date": "2020-01-01",
  "license_expiry_date": "2030-01-01",
  "qualifications": "MBBS, MD - Cardiology",
  "specialty_ids": [1, 2],
  "years_of_experience": 5,
  "consultation_fee": 500.00,
  "consultation_duration": 30,
  "is_available_online": true,
  "is_available_offline": true,
  "status": "active",
  "languages_spoken": "English, Hindi, Marathi"
}
```

**Required Fields (when create_user=true):**
- `email`, `password`, `password_confirm`, `first_name`
- `medical_license_number`, `license_issuing_authority`, `license_issue_date`, `license_expiry_date`, `qualifications`

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/doctors/create_with_user/" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "create_user": true,
    "email": "doctor@hospital.com",
    "password": "SecurePass123",
    "password_confirm": "SecurePass123",
    "first_name": "Dr. Rajesh",
    "last_name": "Kumar",
    "phone": "+919876543210",
    "medical_license_number": "MED123456",
    "license_issuing_authority": "Medical Council of India",
    "license_issue_date": "2020-01-01",
    "license_expiry_date": "2030-01-01",
    "qualifications": "MBBS, MD - Cardiology",
    "specialty_ids": [1],
    "years_of_experience": 5,
    "consultation_fee": 500.00,
    "consultation_duration": 30
  }'
```

**Success Response (201 Created):**
```json
{
  "success": true,
  "message": "Doctor profile created successfully (user auto-created)",
  "data": {
    "id": 1,
    "user_id": "new-user-uuid",
    "medical_license_number": "MED123456",
    "qualifications": "MBBS, MD - Cardiology",
    "specialties": [...],
    "years_of_experience": 5,
    "consultation_fee": "500.00",
    "status": "active",
    ...
  }
}
```

---

#### Mode 2: Link to Existing User

Set `create_user: false` and provide `user_id` to link the doctor profile to an existing user.

**Request Body:**
```json
{
  "create_user": false,
  "user_id": "existing-user-uuid",
  "medical_license_number": "MED789012",
  "license_issuing_authority": "Medical Council of India",
  "license_issue_date": "2019-01-01",
  "license_expiry_date": "2029-01-01",
  "qualifications": "MBBS, MD - General Medicine",
  "specialty_ids": [1],
  "years_of_experience": 3,
  "consultation_fee": 300.00,
  "consultation_duration": 30,
  "is_available_online": true,
  "is_available_offline": true,
  "status": "active"
}
```

**Required Fields (when create_user=false):**
- `user_id` (UUID of existing user)
- `medical_license_number`, `license_issuing_authority`, `license_issue_date`, `license_expiry_date`, `qualifications`

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/doctors/create_with_user/" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "create_user": false,
    "user_id": "existing-user-uuid",
    "medical_license_number": "MED789012",
    "license_issuing_authority": "Medical Council of India",
    "license_issue_date": "2019-01-01",
    "license_expiry_date": "2029-01-01",
    "qualifications": "MBBS, MD - General Medicine",
    "specialty_ids": [1],
    "years_of_experience": 3,
    "consultation_fee": 300.00
  }'
```

---

## Error Handling

All endpoints return consistent error responses:

**Validation Error (400 Bad Request):**
```json
{
  "success": false,
  "errors": {
    "email": ["This field is required"],
    "password": ["Passwords don't match"]
  }
}
```

**SuperAdmin API Error (500 Internal Server Error):**
```json
{
  "success": false,
  "error": "User creation failed in SuperAdmin",
  "details": "Email already exists",
  "response_data": {...}
}
```

**Partial Success (User created, Doctor failed):**
```json
{
  "success": false,
  "error": "Doctor profile creation failed",
  "details": "Database error details...",
  "note": "User was created successfully with ID: user-uuid, but doctor profile failed. You can retry creating the doctor profile using this user_id."
}
```

---

## Integration Flow

### Complete Doctor Onboarding Flow

1. **Admin creates user account (optional if using auto-creation):**
   ```
   POST /api/auth/users/
   → Get user_id
   ```

2. **Create doctor profile with auto-user creation:**
   ```
   POST /api/doctors/create_with_user/
   {
     "create_user": true,
     "email": "...",
     "password": "...",
     ...doctor details...
   }
   ```

3. **User can now login:**
   ```
   POST /api/auth/login/
   {
     "email": "doctor@hospital.com",
     "password": "SecurePass123"
   }
   ```

---

## Notes

- All operations are tenant-isolated (automatically filtered by your JWT token's tenant_id)
- Passwords must be at least 8 characters
- User emails must be unique across the entire SuperAdmin system
- Doctor license numbers must be unique within your tenant
- All date fields use ISO 8601 format (YYYY-MM-DD)
- Timezone defaults to 'Asia/Kolkata'

---

## Frontend Integration

### Example: Create Doctor with User (JavaScript/Fetch)

```javascript
const createDoctorWithUser = async (doctorData) => {
  const response = await fetch('http://localhost:8000/api/doctors/create_with_user/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      create_user: true,
      email: doctorData.email,
      password: doctorData.password,
      password_confirm: doctorData.password,
      first_name: doctorData.firstName,
      last_name: doctorData.lastName,
      phone: doctorData.phone,
      medical_license_number: doctorData.licenseNumber,
      license_issuing_authority: doctorData.issuingAuthority,
      license_issue_date: doctorData.issueDate,
      license_expiry_date: doctorData.expiryDate,
      qualifications: doctorData.qualifications,
      specialty_ids: doctorData.specialtyIds,
      years_of_experience: doctorData.experience,
      consultation_fee: doctorData.consultationFee,
      consultation_duration: 30,
      is_available_online: true,
      is_available_offline: true,
      status: 'active'
    })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Doctor creation failed');
  }

  return await response.json();
};

// Usage
try {
  const result = await createDoctorWithUser({
    email: 'doctor@hospital.com',
    password: 'SecurePass123',
    firstName: 'Rajesh',
    lastName: 'Kumar',
    phone: '+919876543210',
    licenseNumber: 'MED123456',
    issuingAuthority: 'Medical Council of India',
    issueDate: '2020-01-01',
    expiryDate: '2030-01-01',
    qualifications: 'MBBS, MD',
    specialtyIds: [1, 2],
    experience: 5,
    consultationFee: 500
  });

  console.log('Doctor created:', result.data);
} catch (error) {
  console.error('Error:', error.message);
}
```

---

## Support

For issues or questions, please refer to the main HMS documentation or contact the development team.
