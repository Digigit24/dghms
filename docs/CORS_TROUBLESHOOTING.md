# CORS Troubleshooting Guide

## Understanding the CORS Error

CORS (Cross-Origin Resource Sharing) errors occur when your **frontend** (running on one domain) tries to make requests to your **backend** (running on a different domain) and the backend doesn't allow it.

### Why It Works Locally But Not in Production

**Locally:**
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000` or `http://127.0.0.1:8000`
- Your `.env` file includes these in `CORS_ALLOWED_ORIGINS`

**Production:**
- Frontend: `https://your-frontend-domain.com` (example)
- Backend: `https://your-backend-domain.com` (example)
- Your server's `.env` likely **doesn't** include the production frontend URL

## Quick Fix Options

### Option 1: Add Production Frontend URL (Recommended)

On your **production server**, update the `.env` file:

```bash
# Edit .env file on your server
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com,https://admin.celiyo.com

# If you also use www subdomain:
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com,https://www.your-frontend-domain.com,https://admin.celiyo.com
```

**Steps:**
1. SSH into your production server
2. Navigate to your Django project directory
3. Edit the `.env` file: `nano .env` or `vim .env`
4. Update `CORS_ALLOWED_ORIGINS` with your frontend URL
5. Restart your Django application:
   ```bash
   # If using systemd
   sudo systemctl restart your-django-service

   # If using gunicorn directly
   pkill gunicorn && gunicorn hms.wsgi:application

   # If using Docker
   docker-compose restart
   ```

### Option 2: Temporarily Allow All Origins (Testing Only)

**⚠️ WARNING: Only use this for testing! Not recommended for production.**

```bash
# In your .env file
CORS_ALLOW_ALL_ORIGINS=True
```

Then restart your Django server.

## Common CORS Issues and Solutions

### 1. Protocol Mismatch (http vs https)

**Error:** CORS error even after adding domain

**Cause:** You added `http://your-domain.com` but your frontend uses `https://your-domain.com`

**Solution:** Add BOTH protocols:
```bash
CORS_ALLOWED_ORIGINS=http://your-domain.com,https://your-domain.com
```

### 2. Missing www Subdomain

**Error:** Works on `your-domain.com` but not `www.your-domain.com`

**Solution:** Add both versions:
```bash
CORS_ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com
```

### 3. Trailing Slash

**Error:** CORS error with subtle differences

**Solution:** Django's CORS middleware is strict about URLs. Do NOT include trailing slashes:
```bash
# ✅ Correct
CORS_ALLOWED_ORIGINS=https://your-domain.com

# ❌ Wrong
CORS_ALLOWED_ORIGINS=https://your-domain.com/
```

### 4. Port Numbers

If your frontend runs on a specific port (e.g., `https://your-domain.com:3000`), include it:
```bash
CORS_ALLOWED_ORIGINS=https://your-domain.com:3000,https://your-domain.com
```

## Environment Variable Format

The `CORS_ALLOWED_ORIGINS` variable expects a **comma-separated list** (no spaces):

```bash
# ✅ Correct
CORS_ALLOWED_ORIGINS=https://frontend.com,https://admin.com,https://api.com

# ❌ Wrong (spaces cause issues)
CORS_ALLOWED_ORIGINS=https://frontend.com, https://admin.com, https://api.com

# ❌ Wrong (quotes not needed)
CORS_ALLOWED_ORIGINS="https://frontend.com,https://admin.com"
```

## Verifying CORS Configuration

### 1. Check Django Logs

Start your Django server and watch the logs:
```bash
# Check logs for CORS headers
tail -f /path/to/django/logs/django.log
```

### 2. Check Browser Console

Open browser DevTools (F12) → Console tab. CORS errors look like:
```
Access to fetch at 'https://your-backend.com/api/...' from origin 'https://your-frontend.com'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present...
```

### 3. Test with cURL

From your terminal:
```bash
curl -H "Origin: https://your-frontend.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization" \
  -X OPTIONS \
  --verbose \
  https://your-backend.com/api/appointments/
```

Look for these headers in the response:
- `Access-Control-Allow-Origin: https://your-frontend.com`
- `Access-Control-Allow-Credentials: true`
- `Access-Control-Allow-Methods: DELETE, GET, OPTIONS, PATCH, POST, PUT`

## Production Deployment Checklist

When deploying to production, ensure:

- [ ] `.env` file exists on the server
- [ ] `CORS_ALLOWED_ORIGINS` includes your production frontend URL(s)
- [ ] Protocol matches (http vs https)
- [ ] Port numbers included if needed
- [ ] Both www and non-www versions included if applicable
- [ ] `ALLOWED_HOSTS` includes your backend domain
- [ ] `CSRF_TRUSTED_ORIGINS` includes your frontend domain
- [ ] Django service restarted after changing `.env`

## Example Production Configuration

### Frontend
- URL: `https://hms.example.com`
- Running on: Vercel/Netlify/Custom server

### Backend
- URL: `https://api.example.com`
- Running on: Ubuntu server with Gunicorn + Nginx

### Backend `.env` File
```bash
# Django Settings
SECRET_KEY=your-production-secret-key
DEBUG=False
ALLOWED_HOSTS=api.example.com,www.api.example.com
CSRF_TRUSTED_ORIGINS=https://hms.example.com,https://api.example.com

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/hms_prod

# SuperAdmin
SUPERADMIN_URL=https://admin.celiyo.com
JWT_SECRET_KEY=your-jwt-secret-matching-superadmin
JWT_ALGORITHM=HS256

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOWED_ORIGINS=https://hms.example.com,https://admin.celiyo.com,https://api.example.com
```

## Still Having Issues?

1. **Check Django is running:**
   ```bash
   ps aux | grep gunicorn
   # or
   systemctl status your-django-service
   ```

2. **Check nginx configuration** (if using nginx):
   ```bash
   sudo nginx -t
   sudo cat /etc/nginx/sites-available/your-site
   ```

3. **Check firewall rules:**
   ```bash
   sudo ufw status
   ```

4. **Verify environment variables are loaded:**
   ```python
   # In Django shell
   python manage.py shell

   >>> from django.conf import settings
   >>> print(settings.CORS_ALLOWED_ORIGINS)
   >>> print(settings.CORS_ALLOW_ALL_ORIGINS)
   ```

5. **Check for reverse proxy issues:**
   If using nginx/Apache, ensure proxy headers are set:
   ```nginx
   # In nginx config
   proxy_set_header Host $host;
   proxy_set_header X-Real-IP $remote_addr;
   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   proxy_set_header X-Forwarded-Proto $scheme;
   ```

## Need More Help?

If you're still experiencing CORS issues:

1. Share the exact CORS error from browser console
2. Share your frontend URL
3. Share your backend URL
4. Share relevant parts of your `.env` file (without secrets)
5. Share the output of the cURL test above

## References

- [Django CORS Headers Documentation](https://github.com/adamchainz/django-cors-headers)
- [MDN CORS Guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
- [Understanding CORS](https://web.dev/cross-origin-resource-sharing/)
