import structlog
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.drf_auth import HMSPermission, IsAuthenticated
from common.cache import CeliyoCache
from common.responses import error_response, success_response
from common import error_codes

from .models import Hospital
from .serializers import (
    HospitalSerializer,
    HospitalUpdateSerializer,
    HospitalNavStyleSerializer,
    HospitalLetterheadSerializer,
    with_letterhead_defaults,
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
        if 'inventory_config' in serializer.validated_data:
            # Reconcile persisted expiry alerts immediately so list/summary
            # endpoints agree with the newly configured tenant threshold.
            from apps.inventory.models import InventoryItem
            from apps.inventory.services.expiry import get_tenant_default_expiry_alert_days
            from apps.inventory.views import _check_and_update_alerts

            tenant_default = get_tenant_default_expiry_alert_days(request.tenant_id)
            for item in InventoryItem.objects.select_related("category").filter(
                tenant_id=request.tenant_id,
                is_active=True,
            ):
                _check_and_update_alerts(
                    item,
                    request.tenant_id,
                    tenant_default=tenant_default,
                )
            cache = CeliyoCache()
            cache.delete_pattern(f"inventory:dashboard:*:{request.tenant_id}:*")
            cache.delete_pattern(f"inventory:alerts:{request.tenant_id}:*")

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

    normalized = with_letterhead_defaults(payload)

    def validate_image_slot(slot, field_name):
        if not isinstance(slot, dict):
            return {"message": f"'{field_name}' must be an object.", "field": field_name}
        required = {"enabled", "url", "width_px", "height_px"}
        missing_slot_keys = required - set(slot)
        if missing_slot_keys:
            return {
                "message": f"'{field_name}' is missing required keys: {sorted(missing_slot_keys)}.",
                "field": field_name,
            }
        if not isinstance(slot["enabled"], bool):
            return {
                "message": f"'{field_name}.enabled' must be a boolean.",
                "field": f"{field_name}.enabled",
            }
        if not isinstance(slot["url"], str):
            return {
                "message": f"'{field_name}.url' must be a string.",
                "field": f"{field_name}.url",
            }
        for size_key in ("width_px", "height_px"):
            size = slot[size_key]
            if isinstance(size, bool) or not isinstance(size, int) or not 16 <= size <= 240:
                return {
                    "message": f"'{field_name}.{size_key}' must be an integer from 16 to 240.",
                    "field": f"{field_name}.{size_key}",
                }
        return None

    for image_field in ("left_image", "right_image"):
        image_error = validate_image_slot(normalized[image_field], image_field)
        if image_error:
            return None, image_error

    text_lines = payload["text_lines"]
    if not isinstance(text_lines, list):
        return None, {"message": "'text_lines' must be a list.", "field": "text_lines"}

    def validate_styled_lines(lines, field_name):
        if not isinstance(lines, list):
            return {
                "message": f"'{field_name}' must be a list.",
                "field": field_name,
            }

        line_required_keys = {"id", "text", "style", "enabled", "order"}
        for idx, line in enumerate(lines):
            if not isinstance(line, dict):
                return {
                    "message": f"'{field_name}[{idx}]' must be an object.",
                    "field": f"{field_name}[{idx}]",
                }
            missing_line_keys = line_required_keys - set(line.keys())
            if missing_line_keys:
                return {
                    "message": (
                        f"'{field_name}[{idx}]' is missing required keys: "
                        f"{sorted(missing_line_keys)}."
                    ),
                    "field": f"{field_name}[{idx}]",
                }
            if not isinstance(line["id"], str) or not line["id"].strip():
                return {
                    "message": f"'{field_name}[{idx}].id' must be a non-empty string.",
                    "field": f"{field_name}[{idx}].id",
                }
            if not isinstance(line["text"], str):
                return {
                    "message": f"'{field_name}[{idx}].text' must be a string.",
                    "field": f"{field_name}[{idx}].text",
                }
            if line["style"] not in Hospital.LETTERHEAD_TEXT_STYLES:
                return {
                    "message": (
                        f"'{field_name}[{idx}].style' must be one of "
                        f"{list(Hospital.LETTERHEAD_TEXT_STYLES)}."
                    ),
                    "field": f"{field_name}[{idx}].style",
                }
            if not isinstance(line["enabled"], bool):
                return {
                    "message": f"'{field_name}[{idx}].enabled' must be a boolean.",
                    "field": f"{field_name}[{idx}].enabled",
                }
            if not isinstance(line["order"], int) or isinstance(line["order"], bool):
                return {
                    "message": f"'{field_name}[{idx}].order' must be an integer.",
                    "field": f"{field_name}[{idx}].order",
                }
        return None

    line_error = validate_styled_lines(text_lines, "text_lines")
    if line_error:
        return None, line_error

    layout_mode = payload.get("layout_mode", "simple")
    if layout_mode not in Hospital.LETTERHEAD_LAYOUT_MODES:
        return None, {
            "message": f"'layout_mode' must be one of {list(Hospital.LETTERHEAD_LAYOUT_MODES)}.",
            "field": "layout_mode",
        }

    right_column_lines = payload.get("right_column_lines", [])
    line_error = validate_styled_lines(right_column_lines, "right_column_lines")
    if line_error:
        return None, line_error

    background_pattern_url = payload.get("background_pattern_url")
    if background_pattern_url is not None and not isinstance(background_pattern_url, str):
        return None, {
            "message": "'background_pattern_url' must be a string or null.",
            "field": "background_pattern_url",
        }

    info_bar = payload.get(
        "info_bar",
        {
            "enabled": False,
            "background_color": "#1e3a5f",
            "text_color": "#ffffff",
            "lines": [],
        },
    )
    if not isinstance(info_bar, dict):
        return None, {"message": "'info_bar' must be an object.", "field": "info_bar"}
    info_required = {"enabled", "background_color", "text_color", "lines"}
    missing_info = info_required - set(info_bar)
    if missing_info:
        return None, {
            "message": f"'info_bar' is missing required keys: {sorted(missing_info)}.",
            "field": "info_bar",
        }
    if not isinstance(info_bar["enabled"], bool):
        return None, {
            "message": "'info_bar.enabled' must be a boolean.",
            "field": "info_bar.enabled",
        }

    import re
    for color_key in ("background_color", "text_color"):
        color = info_bar[color_key]
        if not isinstance(color, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None:
            return None, {
                "message": f"'info_bar.{color_key}' must be a six-digit hex colour.",
                "field": f"info_bar.{color_key}",
            }
    if not isinstance(info_bar["lines"], list):
        return None, {
            "message": "'info_bar.lines' must be a list.",
            "field": "info_bar.lines",
        }
    for idx, line in enumerate(info_bar["lines"]):
        if not isinstance(line, dict):
            return None, {
                "message": f"'info_bar.lines[{idx}]' must be an object.",
                "field": f"info_bar.lines[{idx}]",
            }
        missing_line_keys = {"id", "text", "align"} - set(line)
        if missing_line_keys:
            return None, {
                "message": (
                    f"'info_bar.lines[{idx}]' is missing required keys: "
                    f"{sorted(missing_line_keys)}."
                ),
                "field": f"info_bar.lines[{idx}]",
            }
        if not isinstance(line["id"], str) or not line["id"].strip():
            return None, {
                "message": f"'info_bar.lines[{idx}].id' must be a non-empty string.",
                "field": f"info_bar.lines[{idx}].id",
            }
        if not isinstance(line["text"], str):
            return None, {
                "message": f"'info_bar.lines[{idx}].text' must be a string.",
                "field": f"info_bar.lines[{idx}].text",
            }
        if line["align"] not in Hospital.LETTERHEAD_INFO_ALIGNMENTS:
            return None, {
                "message": (
                    f"'info_bar.lines[{idx}].align' must be one of "
                    f"{list(Hospital.LETTERHEAD_INFO_ALIGNMENTS)}."
                ),
                "field": f"info_bar.lines[{idx}].align",
            }

    cleaned = dict(normalized)
    cleaned.update(
        {
            "layout_mode": layout_mode,
            "right_column_lines": right_column_lines,
            "background_pattern_url": background_pattern_url,
            "info_bar": info_bar,
        }
    )
    return cleaned, None


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

        config = with_letterhead_defaults(
            instance.letterhead_config or instance.get_default_letterhead_config()
        )
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
            "left_image, right_image, alignment, show_hairline, text_lines[]). "
            "Image slots accept enabled/url/width_px/height_px and preserve "
            "the legacy logo/badge fields for backward compatibility. Requires the "
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
                        "left_image": {
                            "enabled": True,
                            "url": "https://cdn.example.com/logo.png",
                            "width_px": 150,
                            "height_px": 52,
                        },
                        "right_image": {
                            "enabled": True,
                            "url": "https://cdn.example.com/nabh-badge.png",
                            "width_px": 72,
                            "height_px": 72,
                        },
                        "alignment": "center",
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

