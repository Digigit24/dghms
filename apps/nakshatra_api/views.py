# apps/nakshatra_api/views.py

import requests
import time
import uuid
import logging
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import viewsets, filters, status as drf_status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from .utils import create_meta_user_data_payload
from .models import NakshatraLead
from .serializers import (
    NakshatraLeadSerializer,
    NakshatraLeadListSerializer,
    NakshatraLeadCreateSerializer
)

# Set up logger
logger = logging.getLogger('nakshatra_api')
logger.setLevel(logging.DEBUG)


@csrf_exempt  # No CSRF token required for this endpoint
@require_POST
def nakshatra_form_submit_api(request):
    """
    Handles Nakshatra form submissions by:
    1. Sending data to a custom API endpoint
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
    logger.info(f"[NAKSHATRA API] Incoming request from {request.META.get('REMOTE_ADDR')}")
    logger.info(f"[NAKSHATRA API] Method: {request.method}")
    logger.info(f"[NAKSHATRA API] Path: {request.path}")
    logger.info(f"[NAKSHATRA API] User Agent: {request.META.get('HTTP_USER_AGENT')}")

    try:
        # Get form data from POST request
        form_data = request.POST.copy()

        # Log received form data (excluding sensitive info in production)
        logger.debug(f"[NAKSHATRA API] Form data received:")
        logger.debug(f"  - fname: {form_data.get('fname', 'N/A')}")
        logger.debug(f"  - lname: {form_data.get('lname', 'N/A')}")
        logger.debug(f"  - email: {form_data.get('email', 'N/A')[:3]}***") # Partial for privacy
        logger.debug(f"  - phone: {form_data.get('phone', 'N/A')[:3]}***") # Partial for privacy
        logger.debug(f"  - services: {form_data.get('services', 'N/A')}")
        logger.debug(f"  - date: {form_data.get('date', 'N/A')}")
        logger.debug(f"  - client_event_id: {form_data.get('client_event_id', 'N/A')}")

        # --- 0. SAVE LEAD TO DATABASE ---
        logger.info("[NAKSHATRA API] Step 0: Saving lead to database...")

        # Get client IP and user agent
        client_ip = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        # Initialize lead object (will be saved after API calls)
        lead_data = {
            'first_name': form_data.get('fname', ''),
            'last_name': form_data.get('lname', ''),
            'email': form_data.get('email', ''),
            'phone': form_data.get('phone', ''),
            'services': form_data.get('services', ''),
            'appointment_date': form_data.get('date', ''),
            'client_event_id': form_data.get('client_event_id'),
            'ip_address': client_ip,
            'user_agent': user_agent,
            'custom_api_status': 'pending',
            'meta_capi_status': 'pending',
        }

        # Create lead record
        lead = NakshatraLead.objects.create(**lead_data)
        logger.info(f"[NAKSHATRA API] ✅ Lead saved to database with ID: {lead.id}")

        # --- 1. HANDLE CUSTOM API INTEGRATION ---

        # Create a payload for your custom API service
        custom_payload = {
            'fname': form_data.get('fname'),
            'lname': form_data.get('lname'),
            'email': form_data.get('email'),
            'phone': form_data.get('phone'),
            'services': form_data.get('services'),
            'date': form_data.get('date'),
        }

        # Send data to your custom API endpoint
        logger.info("[NAKSHATRA API] Step 1: Sending data to custom API...")
        logger.debug(f"[NAKSHATRA API] Custom API URL: {settings.NAKSHATRA_API_ENDPOINT}")

        try:
            custom_response = requests.post(
                settings.NAKSHATRA_API_ENDPOINT,
                json=custom_payload, # Sending as JSON as requested/standard for custom APIs
                timeout=10
            )

            if custom_response.status_code == 200:
                logger.info(f"[NAKSHATRA API] ✅ Custom API: SUCCESS (Status: {custom_response.status_code})")
                logger.debug(f"[NAKSHATRA API] Custom API Response: {custom_response.text[:200]}")
                # Update lead status
                lead.custom_api_status = 'success'
                lead.custom_api_response = custom_response.text[:500]  # Store first 500 chars
                lead.save(update_fields=['custom_api_status', 'custom_api_response'])
            else:
                logger.warning(f"[NAKSHATRA API] ⚠️ Custom API: FAILED (Status: {custom_response.status_code})")
                logger.warning(f"[NAKSHATRA API] Custom API Error: {custom_response.text}")
                # Update lead status
                lead.custom_api_status = 'failed'
                lead.custom_api_response = f"Status {custom_response.status_code}: {custom_response.text[:500]}"
                lead.save(update_fields=['custom_api_status', 'custom_api_response'])
        except requests.exceptions.Timeout as e:
            logger.error(f"[NAKSHATRA API] ❌ Custom API: TIMEOUT after 10s - {e}")
            lead.custom_api_status = 'error'
            lead.custom_api_response = f"Timeout: {str(e)}"
            lead.save(update_fields=['custom_api_status', 'custom_api_response'])
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[NAKSHATRA API] ❌ Custom API: CONNECTION ERROR - {e}")
            lead.custom_api_status = 'error'
            lead.custom_api_response = f"Connection Error: {str(e)}"
            lead.save(update_fields=['custom_api_status', 'custom_api_response'])
        except requests.exceptions.RequestException as e:
            logger.error(f"[NAKSHATRA API] ❌ Custom API: REQUEST ERROR - {e}")
            lead.custom_api_status = 'error'
            lead.custom_api_response = f"Request Error: {str(e)}"
            lead.save(update_fields=['custom_api_status', 'custom_api_response'])

        # --- 2. FIRE META CONVERSIONS API (CAPI) ---

        logger.info("[NAKSHATRA API] Step 2: Preparing Meta CAPI payload...")

        client_event_id = form_data.get('client_event_id')
        user_data_payload = create_meta_user_data_payload(form_data, request)

        logger.debug(f"[NAKSHATRA API] Meta CAPI - Event ID: {client_event_id}")
        logger.debug(f"[NAKSHATRA API] Meta CAPI - User data has {len(user_data_payload)} fields")

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

        # Meta API URL (v19.0 as used in settings, but user mentioned it in curl)
        meta_url = f"https://graph.facebook.com/v19.0/{settings.NAKSHATRA_PIXAL_ID}/events"

        logger.info("[NAKSHATRA API] Step 3: Firing Meta CAPI...")
        logger.debug(f"[NAKSHATRA API] Meta URL: {meta_url}")
        logger.debug(f"[NAKSHATRA API] Meta Pixel ID: {settings.NAKSHATRA_PIXAL_ID}")

        try:
            capi_response = requests.post(
                meta_url,
                params={'access_token': settings.NAKSHTRA_ACCESS_TOKEN},
                json=capi_payload,
                timeout=10
            )

            if capi_response.status_code == 200:
                logger.info(f"[NAKSHATRA API] ✅ Meta CAPI: SUCCESS (Status: {capi_response.status_code})")
                logger.debug(f"[NAKSHATRA API] Meta CAPI Response: {capi_response.text}")
                # Update lead status
                lead.meta_capi_status = 'success'
                lead.meta_capi_response = capi_response.text[:500]  # Store first 500 chars
                lead.save(update_fields=['meta_capi_status', 'meta_capi_response'])
            else:
                logger.warning(f"[NAKSHATRA API] ⚠️ Meta CAPI: FAILED (Status: {capi_response.status_code})")
                logger.warning(f"[NAKSHATRA API] Meta CAPI Error: {capi_response.text}")
                # Update lead status
                lead.meta_capi_status = 'failed'
                lead.meta_capi_response = f"Status {capi_response.status_code}: {capi_response.text[:500]}"
                lead.save(update_fields=['meta_capi_status', 'meta_capi_response'])
        except requests.exceptions.Timeout as e:
            logger.error(f"[NAKSHATRA API] ❌ Meta CAPI: TIMEOUT after 10s - {e}")
            lead.meta_capi_status = 'error'
            lead.meta_capi_response = f"Timeout: {str(e)}"
            lead.save(update_fields=['meta_capi_status', 'meta_capi_response'])
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[NAKSHATRA API] ❌ Meta CAPI: CONNECTION ERROR - {e}")
            lead.meta_capi_status = 'error'
            lead.meta_capi_response = f"Connection Error: {str(e)}"
            lead.save(update_fields=['meta_capi_status', 'meta_capi_response'])
        except requests.exceptions.RequestException as e:
            logger.error(f"[NAKSHATRA API] ❌ Meta CAPI: REQUEST ERROR - {e}")
            lead.meta_capi_status = 'error'
            lead.meta_capi_response = f"Request Error: {str(e)}"
            lead.save(update_fields=['meta_capi_status', 'meta_capi_response'])

        # --- 3. RETURN SUCCESS RESPONSE ---
        logger.info("[NAKSHATRA API] ✅ Request completed successfully")
        logger.info("="*80)

        return JsonResponse({
            'status': 'success',
            'message': 'Form submitted and tracked successfully.'
        }, status=200)

    except Exception as e:
        # Catch any unexpected errors
        logger.critical("="*80)
        logger.critical(f"[NAKSHATRA API] ❌ CRITICAL ERROR in form submission")
        logger.critical(f"[NAKSHATRA API] Error Type: {type(e).__name__}")
        logger.critical(f"[NAKSHATRA API] Error Message: {str(e)}")
        logger.critical(f"[NAKSHATRA API] Error Details:", exc_info=True)
        logger.critical("="*80)

        return JsonResponse({
            'status': 'error',
            'message': 'An internal error occurred.'
        }, status=500)


# --- VIEWSET FOR MANAGING LEADS ---

class NakshatraLeadViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing Nakshatra leads.

    This is a read-only viewset - leads are created via the form submission endpoint.
    Provides list and retrieve operations for viewing stored leads.

    **Authentication**: Public endpoint (no authentication required)
    **Permissions**: AllowAny (for now - can be restricted later)

    Endpoints:
    - GET /api/nakshatra/leads/ - List all leads
    - GET /api/nakshatra/leads/{id}/ - Retrieve a specific lead
    """

    queryset = NakshatraLead.objects.all()
    permission_classes = [AllowAny]  # Public access - can be restricted later
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    # Filtering
    filterset_fields = ['custom_api_status', 'meta_capi_status', 'services']

    # Search
    search_fields = ['first_name', 'last_name', 'email', 'phone', 'services']

    # Ordering
    ordering_fields = ['created_at', 'first_name', 'last_name']
    ordering = ['-created_at']  # Default ordering

    def get_serializer_class(self):
        """Use different serializers for list and detail views"""
        if self.action == 'list':
            return NakshatraLeadListSerializer
        return NakshatraLeadSerializer

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Get statistics about leads.

        Returns counts of leads by status and total leads.

        Example: GET /api/nakshatra/leads/stats/
        """
        from django.db.models import Count, Q

        total_leads = NakshatraLead.objects.count()

        # Count by custom API status
        custom_api_stats = NakshatraLead.objects.values('custom_api_status').annotate(
            count=Count('id')
        )

        # Count by Meta CAPI status
        meta_capi_stats = NakshatraLead.objects.values('meta_capi_status').annotate(
            count=Count('id')
        )

        # Count successfully processed leads
        successful_leads = NakshatraLead.objects.filter(
            custom_api_status='success',
            meta_capi_status='success'
        ).count()

        # Count failed leads
        failed_leads = NakshatraLead.objects.filter(
            Q(custom_api_status='failed') | Q(custom_api_status='error') |
            Q(meta_capi_status='failed') | Q(meta_capi_status='error')
        ).count()

        return Response({
            'total_leads': total_leads,
            'successful_leads': successful_leads,
            'failed_leads': failed_leads,
            'custom_api_status': {item['custom_api_status']: item['count'] for item in custom_api_stats},
            'meta_capi_status': {item['meta_capi_status']: item['count'] for item in meta_capi_stats},
        })
