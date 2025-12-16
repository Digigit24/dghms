# Nuvi API

This Django app provides a form submission endpoint that integrates with Google Sheets and Meta Conversions API (CAPI) for lead tracking.

## Features

- **No authentication required** - Public endpoint for form submissions
- **Google Sheets Integration** - Automatically saves form data to Google Sheets
- **Meta CAPI Integration** - Tracks lead conversions via Facebook Pixel
- **Error handling** - Gracefully handles failures without blocking the response

## Endpoint

### POST `/api/nuviformsubmit`

Submits a form with user information and tracks the lead.

**Authentication:** None required

**Content-Type:** `application/x-www-form-urlencoded` or `multipart/form-data`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `fname` | string | Yes | First name |
| `lname` | string | Yes | Last name |
| `email` | string | Yes | Email address |
| `phone` | string | Yes | Phone number |
| `services` | string | Yes | Service type requested |
| `date` | string | Yes | Appointment/inquiry date |
| `client_event_id` | string | Yes | Unique event ID from client-side tracking |

**Response:**

```json
{
  "status": "success",
  "message": "Form submitted and tracked successfully."
}
```

**Error Response:**

```json
{
  "status": "error",
  "message": "An internal error occurred."
}
```

## Configuration

Add the following variables to your `.env` file:

```bash
# Google Sheets API
GOOGLE_SHEETS_API_URL=https://your-google-sheets-api-endpoint.com

# Meta (Facebook) Conversions API
META_PIXEL_ID=your_pixel_id_here
META_ACCESS_TOKEN=your_meta_access_token_here
```

## Example Usage

### JavaScript (Fetch API)

```javascript
const formData = new FormData();
formData.append('fname', 'John');
formData.append('lname', 'Doe');
formData.append('email', 'john.doe@example.com');
formData.append('phone', '+1234567890');
formData.append('services', 'Consultation');
formData.append('date', '2025-12-20');
formData.append('client_event_id', crypto.randomUUID());

fetch('http://localhost:8002/api/nuviformsubmit', {
  method: 'POST',
  body: formData
})
  .then(response => response.json())
  .then(data => console.log(data))
  .catch(error => console.error('Error:', error));
```

### cURL

```bash
curl -X POST http://localhost:8002/api/nuviformsubmit \
  -d "fname=John" \
  -d "lname=Doe" \
  -d "email=john.doe@example.com" \
  -d "phone=+1234567890" \
  -d "services=Consultation" \
  -d "date=2025-12-20" \
  -d "client_event_id=$(uuidgen)"
```

## How It Works

1. **Form Submission**: When a POST request is received, the endpoint extracts form data.

2. **Google Sheets**: The data is sent to your configured Google Sheets API endpoint for storage.

3. **Meta CAPI**: The endpoint fires a Lead event to Meta's Conversions API with:
   - Hashed user data (email, phone, name) for privacy
   - Client IP and User Agent for better attribution
   - Custom data (service type)
   - Event deduplication via `client_event_id`

4. **Response**: A success response is returned regardless of whether Google Sheets or CAPI calls succeed (errors are logged server-side).

## Privacy & Security

- **PII Hashing**: Email, phone, and name fields are SHA256 hashed before being sent to Meta CAPI
- **CSRF Exempt**: This endpoint is marked as CSRF exempt since it's designed for external form submissions
- **No Authentication**: Designed for public form submissions - consider rate limiting in production

## Error Handling

The endpoint implements graceful error handling:

- Google Sheets failures are logged but don't block the response
- Meta CAPI failures are logged but don't block the response
- Timeouts are set to 10 seconds for both external API calls
- Any critical errors return a 500 status with an error message

## Testing

```bash
# Run the development server
python manage.py runserver 0.0.0.0:8002

# Test the endpoint
curl -X POST http://localhost:8002/api/nuviformsubmit \
  -d "fname=Test" \
  -d "lname=User" \
  -d "email=test@example.com" \
  -d "phone=+1234567890" \
  -d "services=TestService" \
  -d "date=2025-12-20" \
  -d "client_event_id=test-123-abc"
```

## Files

- `views.py` - Contains the `nuvi_form_submit_api` view
- `utils.py` - Helper functions for hashing and creating Meta user data payload
- `urls.py` - URL configuration for the endpoint

## Notes

- This endpoint does NOT require JWT authentication or tenant isolation
- Ensure your Meta Pixel and Access Token are valid
- Monitor logs for any API integration errors
- Consider implementing rate limiting for production use
