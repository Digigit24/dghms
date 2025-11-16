# DigiHMS - SuperAdmin Integration Deployment Steps

## ✅ What Has Been Completed

All code changes for SuperAdmin integration have been implemented:

### 1. Common Infrastructure ✅
- JWT authentication middleware
- TenantUser class (non-database user)
- SuperAdmin & JWT authentication backends
- Custom admin site with tenant filtering
- Permission system with HMS-specific permissions
- Tenant and patient access mixins
- Authentication proxy views
- Custom login template

### 2. Model Refactoring ✅
**All models updated with:**
- `tenant_id` UUIDField for multi-tenancy
- User ForeignKeys replaced with `user_id` UUIDField
- Proper indexing for tenant_id
- Combined indexes for performance

**Updated Models:**
- ✅ PatientProfile, PatientVitals, PatientAllergy
- ✅ DoctorProfile, Specialty, DoctorAvailability
- ✅ Appointment, AppointmentType
- ✅ Hospital
- ✅ ProductCategory, PharmacyProduct, Cart, CartItem, PharmacyOrder, PharmacyOrderItem
- ✅ FeeType, Order, OrderItem, OrderFee
- ✅ PaymentCategory, Transaction, AccountingPeriod
- ✅ Visit, OPDBill, ProcedureMaster, ProcedurePackage, ProcedureBill, ProcedureBillItem, ClinicalNote, VisitFinding, VisitAttachment
- ✅ ServiceCategory, BaseService (and all child models)

### 3. Settings & Configuration ✅
- `common` app added to INSTALLED_APPS
- `accounts` app removed (commented out)
- AUTH_USER_MODEL removed
- JWT middleware configured
- SuperAdmin authentication backends
- CORS headers for tenant isolation
- DATABASE_URL support

### 4. Admin Interface ✅
- All admin classes use TenantModelAdmin
- tenant_id shown and auto-prefilled
- user_id fields instead of user ForeignKeys

---

## 🚀 Deployment Instructions

### Step 1: Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables

Create `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# Django Core
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database - Use DATABASE_URL (recommended)
DATABASE_URL=postgresql://user:password@localhost:5432/dghms_fresh

# SuperAdmin Integration (REQUIRED)
SUPERADMIN_URL=https://admin.celiyo.com
JWT_SECRET_KEY=<get-from-superadmin-team>
JWT_ALGORITHM=HS256

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,https://admin.celiyo.com
```

**IMPORTANT**: Get the correct `JWT_SECRET_KEY` from your SuperAdmin team - it MUST match!

### Step 3: Create Fresh Database

```bash
# Create new PostgreSQL database
createdb dghms_fresh

# Or use psql
psql -U postgres
CREATE DATABASE dghms_fresh;
\q
```

### Step 4: Create and Run Migrations

```bash
# Create migrations for all apps
python manage.py makemigrations

# Expected apps with migrations:
# - common (none, no models)
# - doctors
# - patients
# - appointments
# - hospital
# - pharmacy
# - orders
# - payments
# - opd
# - services

# Apply migrations
python manage.py migrate

# You should see migrations applied for:
# - Django built-ins (auth, contenttypes, sessions, admin)
# - All HMS apps with tenant_id
```

### Step 5: Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### Step 6: Test Authentication

```bash
# Start development server
python manage.py runserver 0.0.0.0:8002
```

Visit: `http://localhost:8002/admin/`

**Login with SuperAdmin credentials:**
1. Enter email and password from SuperAdmin
2. System proxies request to SuperAdmin API
3. JWT token validated
4. Session created with TenantUser
5. Admin panel accessible

---

## 🧪 Testing Checklist

### Authentication Tests
- [ ] Login with SuperAdmin credentials works
- [ ] Invalid credentials are rejected
- [ ] Users without HMS module are denied
- [ ] Session persists across page loads
- [ ] Logout clears session properly

### Tenant Isolation Tests
- [ ] Creating records auto-sets tenant_id
- [ ] tenant_id field is read-only in admin
- [ ] Different tenants cannot see each other's data
- [ ] Queries automatically filter by tenant_id

### Admin Interface Tests
- [ ] Static files load (CSS, JS, images)
- [ ] Custom login page displays
- [ ] Tenant info shows in admin
- [ ] All models visible in admin
- [ ] Creating records works
- [ ] tenant_id pre-filled automatically

### API Tests (with JWT)
```bash
# Get JWT token from SuperAdmin
TOKEN="your-jwt-token-here"

# Test API endpoint
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8002/api/patients/
```

- [ ] JWT authentication works
- [ ] Tenant filtering works
- [ ] Permissions checked correctly
- [ ] Patients see only own records

---

## 📊 Database Schema

All tables now have:

```sql
-- Every table has tenant_id
tenant_id UUID NOT NULL
CREATE INDEX idx_<table>_tenant_id ON <table>(tenant_id);

-- User references are UUIDs
user_id UUID  -- For patient/doctor profiles
created_by_user_id UUID  -- For audit trails
recorded_by_user_id UUID  -- For medical records

-- Combined indexes for performance
CREATE INDEX idx_<table>_tenant_status ON <table>(tenant_id, status);
```

---

## 🔗 SuperAdmin Integration Points

### Required SuperAdmin Setup

Work with SuperAdmin team to:

1. **Create Tenant**
   - Hospital name and slug
   - Enable 'hms' module
   - Get database URL

2. **Create Users**
   - Staff users (doctors, nurses, admin)
   - Set appropriate roles and permissions
   - Enable HMS module access

3. **Configure Permissions**
   ```json
   {
     "hms.patients.view": "all",
     "hms.patients.create": true,
     "hms.doctors.view": "all",
     "hms.appointments.create": true
   }
   ```

4. **Get JWT Secret**
   - Must match exactly between SuperAdmin and HMS
   - Add to `.env` as `JWT_SECRET_KEY`

### API Endpoints Used

DigiHMS calls these SuperAdmin endpoints:

- `POST /api/auth/login/` - Login authentication
- `GET /api/users/me/` - Get current user (optional)

SuperAdmin JWT payload structure:
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "tenant_id": "tenant-uuid",
  "tenant_slug": "hospital-name",
  "user_type": "staff|patient",
  "is_patient": false,
  "is_super_admin": false,
  "permissions": {
    "hms.patients.view": "all"
  },
  "enabled_modules": ["hms"]
}
```

---

## 🐛 Common Issues & Solutions

### Issue: "JWT_SECRET_KEY not configured"
**Solution**: Add JWT_SECRET_KEY to .env file (must match SuperAdmin)

### Issue: "HMS module not enabled for this user"
**Solution**: Contact SuperAdmin team to enable HMS module for tenant

### Issue: "No tenant_id in request"
**Solution**: Ensure JWT middleware is in MIDDLEWARE setting

### Issue: "ModuleNotFoundError: No module named 'django'"
**Solution**: Activate virtual environment and install requirements

### Issue: "OperationalError: database does not exist"
**Solution**: Create database: `createdb dghms_fresh`

### Issue: Migrations fail with "relation already exists"
**Solution**: Using fresh database, all old migrations deleted

### Issue: Admin static files not loading
**Solution**: Run `python manage.py collectstatic`

---

## 📁 Key Files Reference

### Configuration
- `hms/settings.py` - Main settings (JWT, auth backends, CORS)
- `.env` - Environment variables (JWT_SECRET_KEY, DATABASE_URL)
- `common/middleware.py` - JWT validation
- `common/auth_backends.py` - TenantUser, authentication

### Models
- `apps/patients/models.py` - Patient, Vitals, Allergy (with tenant_id)
- `apps/doctors/models.py` - Doctor, Specialty, Availability (with tenant_id)
- All other app models updated similarly

### Admin
- `common/admin_site.py` - TenantModelAdmin base class
- `apps/patients/admin.py` - Patient admin (uses TenantModelAdmin)
- `apps/doctors/admin.py` - Doctor admin (uses TenantModelAdmin)

### Templates
- `templates/admin/login.html` - Custom login with SuperAdmin proxy

---

## ✨ Features Enabled

### Multi-Tenancy
- ✅ Complete data isolation by tenant_id
- ✅ Automatic tenant filtering
- ✅ Automatic tenant_id on create

### User Management
- ✅ Centralized user management via SuperAdmin
- ✅ No local User model
- ✅ UUID-based user references

### Authentication
- ✅ JWT-based API authentication
- ✅ Session-based admin authentication
- ✅ Permission system from JWT tokens

### Patient Portal Support
- ✅ is_patient flag in JWT
- ✅ PatientAccessMixin restricts to own records
- ✅ Ready for patient portal frontend

---

## 📞 Support

For issues or questions:

1. Check this deployment guide
2. Review `MIGRATION_GUIDE.md` for detailed migration info
3. Review `common/README.md` for code examples
4. Check SuperAdmin team for JWT/tenant setup

---

**Status**: Ready for deployment! All code complete, migrations pending first run.

**Last Updated**: 2025-11-16
