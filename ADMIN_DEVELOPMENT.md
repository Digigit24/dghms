# Django Admin Development Setup

## Issue: tenant_id IntegrityError in Local Development

If you're getting `IntegrityError: null value in column "tenant_id"` when creating patients or other records in Django admin, it's because your local development environment doesn't have the JWT authentication that provides tenant_id automatically.

## Solution: Add DEFAULT_TENANT_ID to settings.py

### Step 1: Find Your Tenant ID

You need to get a valid tenant UUID from your database. Run this command:

```bash
python manage.py shell
```

Then:

```python
from apps.auth.models import Tenant  # or wherever your Tenant model is
tenant = Tenant.objects.first()
print(f"Your tenant ID: {tenant.id}")
```

Or if you don't have a Tenant model, create a UUID:

```python
import uuid
print(f"Generated UUID: {uuid.uuid4()}")
```

### Step 2: Add to settings.py

Add this line to your `settings.py` (preferably in a development-only section):

```python
# For local development: Django admin tenant_id fallback
DEFAULT_TENANT_ID = 'your-uuid-here'  # Replace with actual UUID
```

Example:
```python
# Development settings
if DEBUG:
    DEFAULT_TENANT_ID = '123e4567-e89b-12d3-a456-426614174000'
```

### Step 3: Restart Django Server

```bash
python manage.py runserver
```

Now when you create patients or other records in Django admin at `http://127.0.0.1:8000/admin/`, the system will:

1. First try to get tenant_id from session (production)
2. Then try to get from JWT user (production)
3. Fall back to `DEFAULT_TENANT_ID` (development only)

## Production Notes

⚠️ **IMPORTANT**: `DEFAULT_TENANT_ID` should **ONLY** be used in development!

In production:
- Remove or comment out `DEFAULT_TENANT_ID`
- Ensure proper JWT authentication is set up
- tenant_id will be extracted from authenticated user's session/token

## Checking Logs

The system logs tenant_id extraction attempts. Check your Django logs for:

```
[TenantModelAdmin] Got tenant_id from session: <uuid>
[TenantModelAdmin] Got tenant_id from user: <uuid>
[TenantModelAdmin] Using DEFAULT_TENANT_ID from settings: <uuid>
[TenantModelAdmin] No tenant_id available! ...
```

This helps debug authentication issues.

## Alternative: Proper Authentication Setup

Instead of using `DEFAULT_TENANT_ID`, you can set up proper authentication by logging in through your SuperAdmin system first, which will set the session correctly.

Check `common/admin_site.py` - the `HMSAdminSite.login()` method redirects to SuperAdmin URL for authentication.
