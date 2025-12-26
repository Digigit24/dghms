# Nakshatra API

This Django app provides a form submission endpoint that integrates with a Custom API and Meta Conversions API (CAPI) for lead tracking. It is based on the Nuvi API structure but modified for Nakshatra's requirements.

## Features

- **No authentication required** - Public endpoint for form submissions
- **Custom API Integration** - Automatically saves form data to a custom API endpoint
- **Meta CAPI Integration** - Tracks lead conversions via Facebook Pixel (using Nakshatra credentials)
- **Error handling** - Gracefully handles failures without blocking the response
- **CSRF exempt** - No CSRF token required for external form submissions

## Endpoint

### POST `/api/nakshatra/submit/`

Submits a form with user information and tracks the lead.

**Authentication:** None required

**Content-Type:** `application/x-www-form-urlencoded` or `multipart/form-data`

**Parameters:**

| Parameter         | Type   | Required | Description                               |
| ----------------- | ------ | -------- | ----------------------------------------- |
| `fname`           | string | Yes      | First name                                |
| `lname`           | string | Yes      | Last name                                 |
| `email`           | string | Yes      | Email address                             |
| `phone`           | string | Yes      | Phone number                              |
| `services`        | string | Yes      | Service type requested                    |
| `date`            | string | Yes      | Appointment/inquiry date                  |
| `client_event_id` | string | Yes      | Unique event ID from client-side tracking |

**Response:**

```json
{
  "status": "success",
  "message": "Form submitted and tracked successfully."
}
```

## Configuration

The following variables are configured in `hms/settings.py`:

```python
# Nakshatra API Settings
NAKSHATRA_PIXAL_ID = '2606290336403133'
NAKSHTRA_ACCESS_TOKEN = 'EAARJZClCxRhgBQWF7OH80ZCaQUaQ1M2ZAHCCq1BAEolUwAUZB1UqWWnQuzrGwXZBF7nzPrjXW7uc8NcpL2JZCNwPb7ZCrkTaxMQViuchzzvDzuDxzXHdIny7jFlG4j0Lcg78ZC6rZCwATOTXZCkZAaCJ9m9cMUUPRei7goJL6trL72ytoxDjjwuaMuSfZBrbEX3LkAZDZD'
NAKSHATRA_API_ENDPOINT = 'https://forms.thedigitechsolutions.com/api/forms/submit/09f77c2c-a501-4b0b-b96d-552efe7145d5'
```

## How It Works

1. **Form Submission**: When a POST request is received, the endpoint extracts form data.
2. **Custom API**: The data is sent to the configured custom API endpoint as JSON.
3. **Meta CAPI**: The endpoint fires a Lead event to Meta's Conversions API with:
   - Hashed user data (email, phone, name)
   - Client IP and User Agent
   - Custom data (service type)
   - Event deduplication via `client_event_id`
4. **Response**: A success response is returned regardless of whether external API calls succeed.

## Testing

Use the provided `test_nakshatra.py` script to test the endpoint:

```bash
python apps/nakshatra_api/test_nakshatra.py
```
