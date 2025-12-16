# apps/nuviapi/views.py

import requests
import time
import uuid
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .utils import create_meta_user_data_payload


@csrf_exempt  # No CSRF token required for this endpoint
@require_POST
def nuvi_form_submit_api(request):
    """
    Handles Nuvi form submissions by:
    1. Sending data to Google Sheets
    2. Firing Meta Conversions API (CAPI) for tracking

    No authentication required.

    Expected POST parameters:
        - fname: First name
        - lname: Last name
        - email: Email address
        - phone: Phone number
        - services: Service type requested
        - date: Appointment/inquiry date
        - client_event_id: Unique event ID from client-side tracking

    Returns:
        JsonResponse with status and message
    """
    try:
        # Get form data from POST request
        form_data = request.POST.copy()

        # --- 1. HANDLE GOOGLE SHEET INTEGRATION ---

        # Create a payload for your Google Sheets service
        sheet_payload = {
            'fname': form_data.get('fname'),
            'lname': form_data.get('lname'),
            'email': form_data.get('email'),
            'phone': form_data.get('phone'),
            'services': form_data.get('services'),
            'date': form_data.get('date'),
        }

        # Send data to your Google Sheets API handler
        try:
            sheet_response = requests.post(
                settings.GOOGLE_SHEETS_API_URL,
                data=sheet_payload,
                timeout=10
            )

            if sheet_response.status_code != 200:
                # Log the error but allow CAPI to proceed
                print(f"WARNING: Google Sheet submission failed: {sheet_response.text}")
        except requests.exceptions.RequestException as e:
            # Log connection/timeout errors but don't fail the request
            print(f"ERROR: Could not connect to Google Sheets API: {e}")

        # --- 2. FIRE META CONVERSIONS API (CAPI) ---

        client_event_id = form_data.get('client_event_id')
        user_data_payload = create_meta_user_data_payload(form_data, request)

        capi_payload = {
            'data': [{
                'event_name': 'Lead',
                'event_time': int(time.time()),
                'event_source_url': request.build_absolute_uri(),
                'action_source': 'website',
                'custom_data': {
                    'service_type': form_data.get('services')
                },
                'event_id': client_event_id,
                'user_data': user_data_payload,
                'external_id': str(uuid.uuid4())
            }]
        }

        meta_url = f"https://graph.facebook.com/v19.0/{settings.META_PIXEL_ID}/events"

        try:
            capi_response = requests.post(
                meta_url,
                params={'access_token': settings.META_ACCESS_TOKEN},
                json=capi_payload,
                timeout=10
            )

            if capi_response.status_code != 200:
                # Log the CAPI error for internal review
                print(f"WARNING: Meta CAPI failed: {capi_response.text}")
        except requests.exceptions.RequestException as e:
            # Log connection/timeout errors but don't fail the request
            print(f"ERROR: Could not connect to Meta CAPI: {e}")

        # --- 3. RETURN SUCCESS RESPONSE ---
        return JsonResponse({
            'status': 'success',
            'message': 'Form submitted and tracked successfully.'
        }, status=200)

    except Exception as e:
        # Catch any unexpected errors
        print(f"CRITICAL ERROR in nuvi form submission: {e}")
        return JsonResponse({
            'status': 'error',
            'message': 'An internal error occurred.'
        }, status=500)
