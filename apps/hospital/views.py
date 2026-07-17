import structlog
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.drf_auth import HMSPermission, IsAuthenticated
from common.responses import error_response, success_response
from common import error_codes

from .models import Hospital
from .serializers import (
    HospitalSerializer,
    HospitalUpdateSerializer,
    HospitalNavStyleSerializer,
    HospitalLetterheadSerializer,
)

log = structlog.get_logger(__name__)


def _get_or_create_hospital(request) -> Hospital:
    """
    Return the tenant's Hospital singleton, auto-creating a skeleton record
    on first access so the Settings page always has something to display.

    Uses the authenticated tenant_id from the JWT so every tenant gets its
    own Hospital row (the model's singleton guard prevents duplicates per DB,
    but in production each tenant runs against its own schema/DB).
    """
    tenant_id = getattr(request, 'tenant_id', None)
    hospital = Hospital.objects.filter(tenant_id=tenant_id).first()
    if hospital is not None:
        return hospital

    tenant_slug = getattr(request, 'tenant_slug', '') or ''

    # Build a human-readable default name from the slug ("city-hospital" → "City Hospital")
    default_name = tenant_slug.replace('-', ' ').replace('_', ' ').title() or 'Hospital'

    log.info(
        "hospital_config_auto_create",
        tenant_id=str(tenant_id) if tenant_id else None,
        default_name=default_name,
    )

    hospital = Hospital(
        tenant_id=tenant_id,
        name=default_name,
        type='hospital',
        email='admin@hospital.com',
        phone='0000000000',
        address='',
        city='',
        state='',
        country='India',
        pincode='000000',
        working_hours='24/7',
        has_emergency=True,
        has_pharmacy=True,
        has_laboratory=True,
    )
    # Bypass the singleton guard in Hospital.save() by calling Django's base
    # Model.save() directly — we already confirmed objects.first() is None.
    from django.db.models import Model as DjangoModel
    DjangoModel.save(hospital)
    return hospital


class HospitalConfigView(generics.RetrieveUpdateAPIView):
    """
    Hospital Configuration View

    GET:        Retrieve hospital configuration — auto-creates defaults on first access.
    PUT/PATCH:  Update hospital configuration (requires hms.hospital.edit_config permission).
    """
    queryset = Hospital.objects.all()

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return HospitalUpdateSerializer
        return HospitalSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        hms_perm = HMSPermission()
        hms_perm.hms_module = 'hospital'
        hms_perm.action_permission_map = {
            'update': 'edit_config',
            'partial_update': 'edit_config',
        }
        return [hms_perm]

    def get_object(self) -> Hospital:
        """Always returns a Hospital instance, creating defaults if necessary."""
        return _get_or_create_hospital(self.request)

    def retrieve(self, request, *args, **kwargs):
        """GET /api/hospital/config/ — returns the singleton, creating it if absent."""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response({
                'success': True,
                'data': serializer.data,
            })
        except Exception as exc:
            log.error("hospital_config_retrieve_failed", error=str(exc))
            return Response({
                'success': False,
                'error': str(exc),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        """PATCH/PUT /api/hospital/config/ — updates (or creates-then-updates) the singleton."""
        partial = kwargs.pop('partial', False)
        try:
            instance = self.get_object()
        except Exception as exc:
            log.error("hospital_config_update_get_failed", error=str(exc))
            return Response({
                'success': False,
                'error': str(exc),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response({
            'success': True,
            'message': 'Hospital configuration updated successfully',
            'data': HospitalSerializer(instance).data,
        })


class HospitalNavStyleView(APIView):
    """
    Tenant-wide navigation style preference.

    GET:   Any authenticated tenant user can read which nav layout to render
           (horizontal top nav vs vertical sidebar) — shared across the whole
           tenant, not per-user.
    PATCH: Only users with ``hms.hospital.edit_config`` permission (the same
           permission that already gates the rest of hospital config writes —
           see ``HospitalConfigView``) can change it.
    """
    hms_module = 'hospital'
    action_permission_map = {
        'partial_update': 'edit_config',
    }

    def get_permissions(self):
        # HMSPermission.has_permission() falls back to method-based action
        # inference when view.action is unset (plain APIView, no router):
        # PATCH -> 'partial_update' -> action_permission_map -> 'edit_config'.
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        hms_perm = HMSPermission()
        hms_perm.hms_module = 'hospital'
        hms_perm.action_permission_map = {'partial_update': 'edit_config'}
        return [hms_perm]

    @extend_schema(
        summary="Get tenant nav style",
        description=(
            "Returns the tenant-wide UI navigation preference: whether the "
            "frontend should render a horizontal top nav or the classic "
            "vertical sidebar. This is shared across every user of the "
            "tenant (stored on the Hospital singleton), not a per-user "
            "setting. Auto-creates the Hospital row on first access."
        ),
        responses={200: HospitalNavStyleSerializer},
        tags=["Hospital"],
    )
    def get(self, request, *args, **kwargs):
        """GET /api/hospital/config/nav-style/"""
        try:
            instance = _get_or_create_hospital(request)
        except Exception as exc:
            log.error("hospital_nav_style_retrieve_failed", error=str(exc))
            return error_response(
                code=error_codes.INTERNAL_SERVER_ERROR,
                message="Unable to retrieve hospital configuration.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        serializer = HospitalNavStyleSerializer(instance)
        return success_response(data=serializer.data)

    @extend_schema(
        summary="Update tenant nav style",
        description=(
            "Sets the tenant-wide navigation layout preference — "
            "'horizontal' (top nav) or 'vertical' (sidebar). Shared across "
            "every user of the tenant. Requires the "
            "hms.hospital.edit_config permission (admin-level tenant config "
            "write, same gate as the rest of hospital settings)."
        ),
        request=HospitalNavStyleSerializer,
        responses={200: HospitalNavStyleSerializer},
        examples=[
            OpenApiExample(
                "Switch to vertical sidebar",
                value={"nav_style": "vertical"},
                request_only=True,
            ),
        ],
        tags=["Hospital"],
    )
    def patch(self, request, *args, **kwargs):
        """PATCH /api/hospital/config/nav-style/"""
        nav_style = request.data.get('nav_style')
        valid_choices = {choice[0] for choice in Hospital._meta.get_field('nav_style').choices}

        if nav_style not in valid_choices:
            return error_response(
                code=error_codes.VALIDATION_ERROR,
                message=(
                    f"'nav_style' must be one of {sorted(valid_choices)}."
                ),
                status=status.HTTP_400_BAD_REQUEST,
                field="nav_style",
            )

        try:
            instance = _get_or_create_hospital(request)
        except Exception as exc:
            log.error("hospital_nav_style_update_get_failed", error=str(exc))
            return error_response(
                code=error_codes.INTERNAL_SERVER_ERROR,
                message="Unable to retrieve hospital configuration.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        instance.nav_style = nav_style
        instance.save(update_fields=['nav_style', 'updated_at'])

        log.info(
            "hospital_nav_style_updated",
            tenant_id=str(getattr(request, 'tenant_id', None)),
            user_id=str(getattr(request, 'user_id', None)),
            nav_style=nav_style,
        )

        serializer = HospitalNavStyleSerializer(instance)
        return success_response(
            data=serializer.data,
            message="Navigation style updated successfully.",
        )


def _validate_letterhead_config(payload: dict):
    """
    Validate a client-supplied ``letterhead_config`` payload against the
    schema documented on ``Hospital.letterhead_config`` (apps/hospital/models.py).

    Returns ``(cleaned_config, None)`` on success or ``(None, error_response_kwargs)``
    on the first validation failure, where ``error_response_kwargs`` is a dict
    of kwargs ready to pass to ``common.responses.error_response``.
    """
    if not isinstance(payload, dict):
        return None, {
            "message": "'letterhead' must be a JSON object.",
            "field": "letterhead",
        }

    required_keys = {
        "show_logo", "logo_url", "show_badge", "badge_url",
        "alignment", "show_hairline", "text_lines",
    }
    missing = required_keys - set(payload.keys())
    if missing:
        return None, {
            "message": f"Missing required letterhead fields: {sorted(missing)}.",
            "field": ",".join(sorted(missing)),
        }

    if not isinstance(payload["show_logo"], bool):
        return None, {"message": "'show_logo' must be a boolean.", "field": "show_logo"}
    if not isinstance(payload["show_badge"], bool):
        return None, {"message": "'show_badge' must be a boolean.", "field": "show_badge"}
    if not isinstance(payload["show_hairline"], bool):
        return None, {"message": "'show_hairline' must be a boolean.", "field": "show_hairline"}

    if not isinstance(payload["logo_url"], str):
        return None, {"message": "'logo_url' must be a string.", "field": "logo_url"}
    if not isinstance(payload["badge_url"], str):
        return None, {"message": "'badge_url' must be a string.", "field": "badge_url"}

    if payload["alignment"] not in Hospital.LETTERHEAD_ALIGNMENTS:
        return None, {
            "message": f"'alignment' must be one of {list(Hospital.LETTERHEAD_ALIGNMENTS)}.",
            "field": "alignment",
        }

    text_lines = payload["text_lines"]
    if not isinstance(text_lines, list):
        return None, {"message": "'text_lines' must be a list.", "field": "text_lines"}

    line_required_keys = {"id", "text", "style", "enabled", "order"}
    for idx, line in enumerate(text_lines):
        if not isinstance(line, dict):
            return None, {
                "message": f"'text_lines[{idx}]' must be an object.",
                "field": f"text_lines[{idx}]",
            }
        missing_line_keys = line_required_keys - set(line.keys())
        if missing_line_keys:
            return None, {
                "message": (
                    f"'text_lines[{idx}]' is missing required keys: "
                    f"{sorted(missing_line_keys)}."
                ),
                "field": f"text_lines[{idx}]",
            }
        if not isinstance(line["id"], str) or not line["id"].strip():
            return None, {
                "message": f"'text_lines[{idx}].id' must be a non-empty string.",
                "field": f"text_lines[{idx}].id",
            }
        if not isinstance(line["text"], str):
            return None, {
                "message": f"'text_lines[{idx}].text' must be a string.",
                "field": f"text_lines[{idx}].text",
            }
        if line["style"] not in Hospital.LETTERHEAD_TEXT_STYLES:
            return None, {
                "message": (
                    f"'text_lines[{idx}].style' must be one of "
                    f"{list(Hospital.LETTERHEAD_TEXT_STYLES)}."
                ),
                "field": f"text_lines[{idx}].style",
            }
        if not isinstance(line["enabled"], bool):
            return None, {
                "message": f"'text_lines[{idx}].enabled' must be a boolean.",
                "field": f"text_lines[{idx}].enabled",
            }
        if not isinstance(line["order"], int) or isinstance(line["order"], bool):
            return None, {
                "message": f"'text_lines[{idx}].order' must be an integer.",
                "field": f"text_lines[{idx}].order",
            }

    return payload, None


class HospitalLetterheadView(APIView):
    """
    Tenant-wide print letterhead configuration (Letterhead Designer).

    GET:   Any authenticated tenant user can read the letterhead layout used
           to render the header block (logo, accreditation badge, hospital
           text lines, hairline rule) on every printed clinical/IPD form.
           Shared across the whole tenant, not per-user. If the tenant hasn't
           configured a letterhead yet, returns a computed default seeded
           from the Hospital's existing fields (name, address, email, phone,
           registration_number, logo) — see
           ``Hospital.get_default_letterhead_config()``.
    PATCH: Only users with ``hms.hospital.edit_config`` permission (the same
           permission that already gates the rest of hospital config writes —
           see ``HospitalConfigView`` / ``HospitalNavStyleView``) can change it.
           Validates the full schema server-side and returns a 400
           VALIDATION_ERROR envelope on any malformed payload.
    """
    hms_module = 'hospital'
    action_permission_map = {
        'partial_update': 'edit_config',
    }

    def get_permissions(self):
        # Same pattern as HospitalNavStyleView: HMSPermission falls back to
        # method-based action inference when view.action is unset (plain
        # APIView, no router): PATCH -> 'partial_update' -> 'edit_config'.
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        hms_perm = HMSPermission()
        hms_perm.hms_module = 'hospital'
        hms_perm.action_permission_map = {'partial_update': 'edit_config'}
        return [hms_perm]

    @extend_schema(
        summary="Get tenant print letterhead config",
        description=(
            "Returns the tenant-wide print letterhead layout (logo, "
            "accreditation badge, hospital name/address/contact text lines, "
            "hairline rule) used to render the header of every printed "
            "clinical/IPD form. Shared across every user of the tenant, not "
            "a per-user setting. If the tenant hasn't configured a "
            "letterhead yet, a sensible default computed from the "
            "hospital's existing profile fields (name, address, email, "
            "phone, registration number, logo) is returned instead of an "
            "empty object. Auto-creates the Hospital row on first access."
        ),
        responses={200: HospitalLetterheadSerializer},
        tags=["Hospital"],
    )
    def get(self, request, *args, **kwargs):
        """GET /api/hospital/config/letterhead/"""
        try:
            instance = _get_or_create_hospital(request)
        except Exception as exc:
            log.error("hospital_letterhead_retrieve_failed", error=str(exc))
            return error_response(
                code=error_codes.INTERNAL_SERVER_ERROR,
                message="Unable to retrieve hospital configuration.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        config = instance.letterhead_config or instance.get_default_letterhead_config()
        serializer = HospitalLetterheadSerializer(config)
        return success_response(data={"letterhead": serializer.data})

    @extend_schema(
        summary="Update tenant print letterhead config",
        description=(
            "Sets the tenant-wide print letterhead layout used to render "
            "the header of every printed clinical/IPD form. Shared across "
            "every user of the tenant. The full letterhead object must be "
            "supplied under the 'letterhead' key and must conform to the "
            "documented schema (show_logo, logo_url, show_badge, badge_url, "
            "alignment, show_hairline, text_lines[]). Requires the "
            "hms.hospital.edit_config permission (admin-level tenant config "
            "write, same gate as the rest of hospital settings)."
        ),
        request=HospitalLetterheadSerializer,
        responses={200: HospitalLetterheadSerializer},
        examples=[
            OpenApiExample(
                "Update letterhead",
                value={
                    "letterhead": {
                        "show_logo": True,
                        "logo_url": "https://cdn.example.com/logo.png",
                        "show_badge": True,
                        "badge_url": "https://cdn.example.com/nabh-badge.png",
                        "alignment": "left",
                        "show_hairline": True,
                        "text_lines": [
                            {"id": "name", "text": "Rahane Hospital", "style": "title", "enabled": True, "order": 0},
                            {"id": "address", "text": "Indumati Complex, Pune", "style": "normal", "enabled": True, "order": 1},
                            {"id": "email", "text": "E-mail : rahanehospital@gmail.com", "style": "normal", "enabled": True, "order": 2},
                            {"id": "contact", "text": "8975105100   REG. No. : 619", "style": "normal", "enabled": True, "order": 3},
                        ],
                    }
                },
                request_only=True,
            ),
        ],
        tags=["Hospital"],
    )
    def patch(self, request, *args, **kwargs):
        """PATCH /api/hospital/config/letterhead/"""
        letterhead_payload = request.data.get('letterhead')

        if letterhead_payload is None:
            return error_response(
                code=error_codes.VALIDATION_ERROR,
                message="'letterhead' object is required.",
                status=status.HTTP_400_BAD_REQUEST,
                field="letterhead",
            )

        cleaned_config, err = _validate_letterhead_config(letterhead_payload)
        if err is not None:
            return error_response(
                code=error_codes.VALIDATION_ERROR,
                message=err["message"],
                status=status.HTTP_400_BAD_REQUEST,
                field=err["field"],
            )

        try:
            instance = _get_or_create_hospital(request)
        except Exception as exc:
            log.error("hospital_letterhead_update_get_failed", error=str(exc))
            return error_response(
                code=error_codes.INTERNAL_SERVER_ERROR,
                message="Unable to retrieve hospital configuration.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        instance.letterhead_config = cleaned_config
        instance.save(update_fields=['letterhead_config', 'updated_at'])

        log.info(
            "hospital_letterhead_updated",
            tenant_id=str(getattr(request, 'tenant_id', None)),
            user_id=str(getattr(request, 'user_id', None)),
            text_line_count=len(cleaned_config.get('text_lines', [])),
            show_logo=cleaned_config.get('show_logo'),
            show_badge=cleaned_config.get('show_badge'),
        )

        serializer = HospitalLetterheadSerializer(cleaned_config)
        return success_response(
            data={"letterhead": serializer.data},
            message="Letterhead configuration updated successfully.",
        )

