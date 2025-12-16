# apps/nuviapi/views.py

import requests
import time
import uuid
import logging
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .utils import create_meta_user_data_payload

# Set up logger
logger = logging.getLogger('nuviapi')
logger.setLevel(logging.DEBUG)


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
    # Log incoming request
    logger.info("="*80)
    logger.info(f"[NUVI API] Incoming request from {request.META.get('REMOTE_ADDR')}")
    logger.info(f"[NUVI API] Method: {request.method}")
    logger.info(f"[NUVI API] Path: {request.path}")
    logger.info(f"[NUVI API] User Agent: {request.META.get('HTTP_USER_AGENT')}")

    try:
        # Get form data from POST request
        form_data = request.POST.copy()

        # Log received form data (excluding sensitive info in production)
        logger.debug(f"[NUVI API] Form data received:")
        logger.debug(f"  - fname: {form_data.get('fname', 'N/A')}")
        logger.debug(f"  - lname: {form_data.get('lname', 'N/A')}")
        logger.debug(f"  - email: {form_data.get('email', 'N/A')[:3]}***") # Partial for privacy
        logger.debug(f"  - phone: {form_data.get('phone', 'N/A')[:3]}***") # Partial for privacy
        logger.debug(f"  - services: {form_data.get('services', 'N/A')}")
        logger.debug(f"  - date: {form_data.get('date', 'N/A')}")
        logger.debug(f"  - client_event_id: {form_data.get('client_event_id', 'N/A')}")

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
        logger.info("[NUVI API] Step 1: Sending data to Google Sheets...")
        logger.debug(f"[NUVI API] Google Sheets URL: {settings.GOOGLE_SHEETS_API_URL}")

        try:
            sheet_response = requests.post(
                settings.GOOGLE_SHEETS_API_URL,
                data=sheet_payload,
                timeout=10
            )

            if sheet_response.status_code == 200:
                logger.info(f"[NUVI API] ✅ Google Sheets: SUCCESS (Status: {sheet_response.status_code})")
                logger.debug(f"[NUVI API] Google Sheets Response: {sheet_response.text[:200]}")
            else:
                logger.warning(f"[NUVI API] ⚠️ Google Sheets: FAILED (Status: {sheet_response.status_code})")
                logger.warning(f"[NUVI API] Google Sheets Error: {sheet_response.text}")
        except requests.exceptions.Timeout as e:
            logger.error(f"[NUVI API] ❌ Google Sheets: TIMEOUT after 10s - {e}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[NUVI API] ❌ Google Sheets: CONNECTION ERROR - {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[NUVI API] ❌ Google Sheets: REQUEST ERROR - {e}")

        # --- 2. FIRE META CONVERSIONS API (CAPI) ---

        logger.info("[NUVI API] Step 2: Preparing Meta CAPI payload...")

        client_event_id = form_data.get('client_event_id')
        user_data_payload = create_meta_user_data_payload(form_data, request)

        logger.debug(f"[NUVI API] Meta CAPI - Event ID: {client_event_id}")
        logger.debug(f"[NUVI API] Meta CAPI - User data has {len(user_data_payload)} fields")

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

        logger.info("[NUVI API] Step 3: Firing Meta CAPI...")
        logger.debug(f"[NUVI API] Meta URL: {meta_url}")
        logger.debug(f"[NUVI API] Meta Pixel ID: {settings.META_PIXEL_ID}")

        try:
            capi_response = requests.post(
                meta_url,
                params={'access_token': settings.META_ACCESS_TOKEN},
                json=capi_payload,
                timeout=10
            )

            if capi_response.status_code == 200:
                logger.info(f"[NUVI API] ✅ Meta CAPI: SUCCESS (Status: {capi_response.status_code})")
                logger.debug(f"[NUVI API] Meta CAPI Response: {capi_response.text}")
            else:
                logger.warning(f"[NUVI API] ⚠️ Meta CAPI: FAILED (Status: {capi_response.status_code})")
                logger.warning(f"[NUVI API] Meta CAPI Error: {capi_response.text}")
        except requests.exceptions.Timeout as e:
            logger.error(f"[NUVI API] ❌ Meta CAPI: TIMEOUT after 10s - {e}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[NUVI API] ❌ Meta CAPI: CONNECTION ERROR - {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[NUVI API] ❌ Meta CAPI: REQUEST ERROR - {e}")

        # --- 3. RETURN SUCCESS RESPONSE ---
        logger.info("[NUVI API] ✅ Request completed successfully")
        logger.info("="*80)

        return JsonResponse({
            'status': 'success',
            'message': 'Form submitted and tracked successfully.'
        }, status=200)

    except Exception as e:
        # Catch any unexpected errors
        logger.critical("="*80)
        logger.critical(f"[NUVI API] ❌ CRITICAL ERROR in form submission")
        logger.critical(f"[NUVI API] Error Type: {type(e).__name__}")
        logger.critical(f"[NUVI API] Error Message: {str(e)}")
        logger.critical(f"[NUVI API] Error Details:", exc_info=True)
        logger.critical("="*80)

        return JsonResponse({
            'status': 'error',
            'message': 'An internal error occurred.'
        }, status=500)
