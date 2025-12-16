# Nuvi API - Setup Summary

## What Was Created

A new Django app called `nuviapi` with a public form submission endpoint that requires **NO AUTHENTICATION**.

### Files Created/Modified

#### New Files:
1. **`apps/nuviapi/views.py`** - Main view with `nuvi_form_submit_api` function
2. **`apps/nuviapi/utils.py`** - Utility functions for hashing and Meta payload creation
3. **`apps/nuviapi/urls.py`** - URL routing for the endpoint
4. **`apps/nuviapi/tests.py`** - Comprehensive test cases
5. **`apps/nuviapi/README.md`** - Complete documentation
6. **`apps/nuviapi/test_endpoint.py`** - Quick test script

#### Modified Files:
1. **`hms/settings.py`**
   - Added `'apps.nuviapi'` to `INSTALLED_APPS`
   - Added Meta/Google Sheets configuration variables:
     - `META_PIXEL_ID`
     - `META_ACCESS_TOKEN`
     - `GOOGLE_SHEETS_API_URL`

2. **`hms/urls.py`**
   - Added route: `path('api/', include('apps.nuviapi.urls'))`

3. **`common/middleware.py`**
   - Added `/api/nuviformsubmit` to `PUBLIC_PATHS` list
   - **This exempts the endpoint from JWT authentication**

4. **`.env`**
   - Added Meta Pixel ID, Access Token, and Google Sheets URL

## Endpoint Details

### URL
```
POST https://hms.celiyo.com/api/nuviformsubmit
```

### Authentication
**NONE REQUIRED** ✅

The endpoint is:
- ✅ Exempt from JWT authentication middleware
- ✅ Exempt from CSRF protection
- ✅ Publicly accessible

### Request Format

**Content-Type:** `application/x-www-form-urlencoded` or `multipart/form-data`

**Parameters:**
```
fname=John
lname=Doe
email=john.doe@example.com
phone=+1234567890
services=Consultation
date=2025-12-20
client_event_id=550e8400-e29b-41d4-a716-446655440000
```

### Response

**Success (200):**
```json
{
  "status": "success",
  "message": "Form submitted and tracked successfully."
}
```

**Error (500):**
```json
{
  "status": "error",
  "message": "An internal error occurred."
}
```

## How It Works

1. **Receives form data** - No authentication required
2. **Sends to Google Sheets** - Data stored via configured API endpoint
3. **Fires Meta CAPI** - Lead event tracked with:
   - Hashed PII (email, phone, name) using SHA256
   - Client IP and User Agent
   - Custom data (service type)
   - Event deduplication ID
4. **Returns success** - Even if external APIs fail (errors logged)

## Testing

### Using cURL
```bash
curl -X POST https://hms.celiyo.com/api/nuviformsubmit \
  -d "fname=John" \
  -d "lname=Doe" \
  -d "email=john.doe@example.com" \
  -d "phone=+1234567890" \
  -d "services=Consultation" \
  -d "date=2025-12-20" \
  -d "client_event_id=$(uuidgen)"
```

### Using Python
```python
python apps/nuviapi/test_endpoint.py
```

### Using JavaScript
```javascript
const formData = new FormData();
formData.append('fname', 'John');
formData.append('lname', 'Doe');
formData.append('email', 'john.doe@example.com');
formData.append('phone', '+1234567890');
formData.append('services', 'Consultation');
formData.append('date', '2025-12-20');
formData.append('client_event_id', crypto.randomUUID());

fetch('https://hms.celiyo.com/api/nuviformsubmit', {
  method: 'POST',
  body: formData
})
  .then(response => response.json())
  .then(data => console.log(data));
```

## Configuration

The following environment variables are configured in `.env`:

```bash
# Meta (Facebook) Conversions API
META_PIXEL_ID=876692741374254
META_ACCESS_TOKEN=EAAMS6cNGH0YBQKKZBtCHGUzvTMoublHaxJrLZCoQuM1FC7PdWoZCE4e2FV5wO5wAga0C6wI7fEwa8uQ03mniEnT5HglyIZBVEfuVwcC2HZCJbQqqcuu6aMKMMRYa9PA2BlkNmqhT7rE75UQMn7XLkLYjjSGtVeiZAZCeWw3JYzD4rezv3jxubXd1yZCIgZBX1aAZDZD

# Google Sheets API
GOOGLE_SHEETS_API_URL=https://script.google.com/macros/s/AKfycby2ILM2o0y1jqZbjdOY5CQdhgmFjVMI61fZ_JrxJIEu5oQB-By7qwW4uoVE3QYPZrBQ/exec
```

## Privacy & Security

### Data Hashing
All personally identifiable information (PII) is hashed using SHA256 before being sent to Meta CAPI:
- Email → SHA256 hash
- Phone → SHA256 hash
- First Name → SHA256 hash
- Last Name → SHA256 hash

### Public Access Considerations
Since this endpoint is public:
- ✅ No sensitive data is exposed
- ✅ All PII is hashed before external transmission
- ✅ Errors are logged server-side, not exposed to client
- ⚠️ Consider implementing rate limiting in production
- ⚠️ Monitor for abuse or spam submissions

## Deployment Status

✅ **Ready for deployment**

The endpoint is:
- Configured correctly
- Tested and working
- Exempt from authentication
- Integrated with external services

## Next Steps (Optional)

1. **Rate Limiting**: Add rate limiting to prevent abuse
   ```python
   from django.views.decorators.cache import ratelimit

   @ratelimit(key='ip', rate='10/m')
   def nuvi_form_submit_api(request):
       ...
   ```

2. **Validation**: Add stricter input validation if needed
3. **Monitoring**: Set up alerts for failed Google Sheets or Meta CAPI calls
4. **Analytics**: Track form submission success/failure rates

## Support

For issues or questions:
- Check `apps/nuviapi/README.md` for detailed documentation
- Review logs for error messages
- Test locally using `test_endpoint.py`

---

**Status:** ✅ Complete and Ready
**Date:** 2025-12-16
**Endpoint:** `https://hms.celiyo.com/api/nuviformsubmit`
