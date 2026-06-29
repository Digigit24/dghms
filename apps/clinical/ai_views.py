"""AI-powered clinical form creator wizard API.

Endpoints live under ``/api/clinical/ai/`` and are backed by
``ClinicalFormGenerationRequest``.
"""

from __future__ import annotations

import structlog
from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from common import error_codes
from common.cache import CeliyoCache
from common.drf_auth import HMSPermission
from common.mixins import TenantViewSetMixin
from common.pagination import StandardPagination
from common.permissions import HMSPermissions, IsTenantAuthenticated, check_permission
from common.responses import action_response, error_response

from .ai import generate_form_draft, normalize_code
from .models import (
    ClinicalForm,
    ClinicalFormField,
    ClinicalFormGenerationRequest,
    ClinicalFormSection,
    ClinicalPicklist,
    ClinicalPicklistItem,
)
from .serializers import (
    ApplyFormDraftSerializer,
    ClinicalFormGenerationRequestSerializer,
    ClinicalFormStructureSerializer,
    GenerateFormRequestSerializer,
    RegenerateFormRequestSerializer,
)

logger = structlog.get_logger(__name__)


def _bust_form_cache(form_id: int):
    try:
        cache = CeliyoCache()
        cache.delete_pattern(f"clinical:form:{form_id}:*")
    except Exception as exc:
        logger.warning("form_cache_bust_failed", form_id=form_id, error=str(exc))


def _validate_draft(draft: dict) -> tuple[bool, str]:
    """Lightweight structural validation of the AI-generated draft."""
    if not isinstance(draft, dict):
        return False, "Generated draft is not a JSON object."

    code = draft.get("code")
    if not code:
        return False, "Generated draft is missing 'code'."

    sections = draft.get("sections")
    if not isinstance(sections, list) or not sections:
        return False, "Generated draft must contain at least one section."

    field_keys: set[str] = set()
    for s_idx, section in enumerate(sections):
        if not isinstance(section, dict):
            return False, f"Section at index {s_idx} is not an object."
        if not section.get("code"):
            return False, f"Section at index {s_idx} is missing 'code'."
        fields = section.get("fields")
        if not isinstance(fields, list) or not fields:
            return False, f"Section '{section.get('code')}' must contain at least one field."
        for f_idx, field in enumerate(fields):
            if not isinstance(field, dict):
                return False, f"Field at section {s_idx}, index {f_idx} is not an object."
            fkey = field.get("field_key")
            ftype = field.get("field_type")
            label = field.get("label")
            if not fkey or not ftype or not label:
                return False, f"Field at section {s_idx}, index {f_idx} is missing required keys."
            if ftype not in [c[0] for c in ClinicalFormField.FieldType.choices]:
                return False, f"Field '{fkey}' has unsupported field_type '{ftype}'."
            if ftype in (ClinicalFormField.FieldType.PICKLIST, ClinicalFormField.FieldType.MULTISELECT):
                if not field.get("picklist_code"):
                    return False, f"Field '{fkey}' of type '{ftype}' must reference a 'picklist_code'."
            if fkey in field_keys:
                return False, f"Duplicate field_key '{fkey}' across form."
            field_keys.add(fkey)

    return True, ""


def _apply_form_draft(
    request,
    generation_request: ClinicalFormGenerationRequest,
    target_code: str | None,
    dry_run: bool,
) -> tuple[dict | None, dict | None]:
    """Migrate a completed draft into real clinical forms.

    Returns ``(result_data, error_response_kwargs)``. Exactly one is non-None.
    """
    draft = generation_request.generated_draft
    if not draft:
        return None, {
            "code": error_codes.INVALID_FORM_DRAFT,
            "message": "This generation request has no draft to apply.",
            "status": status.HTTP_400_BAD_REQUEST,
        }

    valid, reason = _validate_draft(draft)
    if not valid:
        return None, {
            "code": error_codes.INVALID_FORM_DRAFT,
            "message": reason,
            "status": status.HTTP_400_BAD_REQUEST,
        }

    tenant_id = request.tenant_id
    user_id = request.user_id

    form_code = normalize_code(target_code or draft.get("code", "generated_form"))

    existing_form = ClinicalForm.objects.filter(tenant_id=tenant_id, code=form_code).first()
    if existing_form:
        return None, {
            "code": error_codes.RECORD_ALREADY_EXISTS,
            "message": f"A form with code '{form_code}' already exists in this tenant.",
            "status": status.HTTP_409_CONFLICT,
        }

    # Pre-flight: resolve existing picklists and build the dry-run plan.
    # New picklists are NOT created here — they are created inside the atomic
    # block below so that any failure rolls everything back atomically.
    picklist_map: dict[str, ClinicalPicklist] = {}
    picklist_plan: list[dict] = []
    draft_picklists = draft.get("picklists") or []
    draft_picklist_codes = {
        normalize_code(p.get("code", "")) for p in draft_picklists if normalize_code(p.get("code", ""))
    }

    for p_draft in draft_picklists:
        p_code = normalize_code(p_draft.get("code", ""))
        if not p_code:
            continue
        existing = ClinicalPicklist.objects.filter(tenant_id=tenant_id, code=p_code).first()
        if existing:
            picklist_map[p_code] = existing
            picklist_plan.append({"code": p_code, "action": "existing", "id": existing.id})
        elif dry_run:
            picklist_plan.append({"code": p_code, "action": "would_create", "items": len(p_draft.get("items", []))})
        # Non-dry_run new picklists are intentionally deferred to the atomic block.

    # Verify all referenced picklists exist (or are defined in the draft).
    missing_picklists: set[str] = set()
    for section in draft.get("sections", []):
        for field in section.get("fields", []):
            p_code = field.get("picklist_code")
            if p_code and p_code not in picklist_map and p_code not in draft_picklist_codes:
                missing_picklists.add(p_code)
    if missing_picklists:
        return None, {
            "code": error_codes.INVALID_FORM_DRAFT,
            "message": f"Referenced picklists are not defined: {sorted(missing_picklists)}.",
            "status": status.HTTP_400_BAD_REQUEST,
        }

    if dry_run:
        preview = {
            "form_code": form_code,
            "form_name": draft.get("name"),
            "entity_type": draft.get("entity_type", generation_request.entity_type),
            "sections_count": len(draft.get("sections", [])),
            "fields_count": sum(len(s.get("fields", [])) for s in draft.get("sections", [])),
            "picklists": picklist_plan,
            "dry_run": True,
        }
        return preview, None

    # All writes — including picklists — happen inside a single atomic block so
    # that any failure rolls back everything cleanly (no orphaned picklists).
    with transaction.atomic():
        # Create/reuse picklists inside the transaction so partial failures roll back.
        for p_draft in draft_picklists:
            p_code = normalize_code(p_draft.get("code", ""))
            if not p_code or p_code in picklist_map:
                # Already resolved above (existing picklist) or empty code — skip.
                continue
            picklist_obj = ClinicalPicklist.objects.create(
                tenant_id=tenant_id,
                code=p_code,
                name=p_draft.get("name", p_code),
                description=p_draft.get("description", ""),
                created_by_user_id=user_id,
            )
            for i, item in enumerate(p_draft.get("items", [])):
                ClinicalPicklistItem.objects.create(
                    tenant_id=tenant_id,
                    picklist=picklist_obj,
                    label=item.get("label", ""),
                    value=item.get("value", ""),
                    display_order=item.get("display_order", i),
                    created_by_user_id=user_id,
                )
            picklist_map[p_code] = picklist_obj
            picklist_plan.append({"code": p_code, "action": "created", "id": picklist_obj.id})

        # AI-generated forms start in STAGING — an admin must explicitly publish.
        form = ClinicalForm.objects.create(
            tenant_id=tenant_id,
            code=form_code,
            name=draft.get("name", form_code),
            description=draft.get("description", ""),
            entity_type=draft.get("entity_type", generation_request.entity_type),
            config=draft.get("config") or {},
            status=ClinicalForm.Status.STAGING,
            created_by_user_id=user_id,
        )

        for s_order, section_draft in enumerate(draft.get("sections", [])):
            section = ClinicalFormSection.objects.create(
                tenant_id=tenant_id,
                form=form,
                code=normalize_code(section_draft.get("code", f"section_{s_order}")),
                title=section_draft.get("title", ""),
                description=section_draft.get("description", ""),
                display_order=section_draft.get("display_order", s_order),
                is_collapsed=section_draft.get("is_collapsed", False),
                config=section_draft.get("config") or {},
                created_by_user_id=user_id,
            )
            for f_order, field_draft in enumerate(section_draft.get("fields", [])):
                ftype = field_draft.get("field_type")
                p_code = field_draft.get("picklist_code")
                picklist = picklist_map.get(p_code) if p_code else None
                ClinicalFormField.objects.create(
                    tenant_id=tenant_id,
                    section=section,
                    field_key=normalize_code(field_draft.get("field_key", f"field_{f_order}")),
                    field_type=ftype,
                    label=field_draft.get("label", ""),
                    help_text=field_draft.get("help_text", ""),
                    display_order=field_draft.get("display_order", f_order),
                    is_required=field_draft.get("is_required", False),
                    is_read_only=field_draft.get("is_read_only", False),
                    default_value=field_draft.get("default_value", None),
                    config=field_draft.get("config") or {},
                    picklist=picklist,
                    created_by_user_id=user_id,
                )

        generation_request.status = ClinicalFormGenerationRequest.Status.APPLIED
        generation_request.applied_form = form
        generation_request.save(update_fields=["status", "applied_form", "updated_at"])

    _bust_form_cache(form.id)

    result = {
        "form_id": form.id,
        "form_code": form.code,
        "form_name": form.name,
        "entity_type": form.entity_type,
        "status": form.status,
        "structure_url": f"/api/clinical/forms/{form.id}/structure/",
        "picklists": picklist_plan,
        "generation_request_id": generation_request.id,
    }
    return result, None


@extend_schema_view(
    list=extend_schema(
        summary="List AI form generation requests",
        description="List previous AI clinical form drafts for the current tenant.",
        tags=["Clinical AI Wizard"],
        responses={200: ClinicalFormGenerationRequestSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve an AI form generation request",
        description="Get a single generation request including its generated draft.",
        tags=["Clinical AI Wizard"],
        responses={200: ClinicalFormGenerationRequestSerializer},
    ),
    create=extend_schema(
        summary="Generate a clinical form draft",
        description="Send a natural-language prompt to OpenAI and store the generated form draft.",
        tags=["Clinical AI Wizard"],
        request=GenerateFormRequestSerializer,
        responses={201: ClinicalFormGenerationRequestSerializer},
    ),
)
class ClinicalFormAIWizardViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """AI clinical form creator wizard.

    - ``POST /api/clinical/ai/`` generates a new draft.
    - ``GET /api/clinical/ai/`` lists generation requests.
    - ``GET /api/clinical/ai/<id>/`` retrieves a request.
    - ``POST /api/clinical/ai/<id>/apply/`` migrates the draft to real forms.
    - ``POST /api/clinical/ai/<id>/regenerate/`` regenerates the draft.
    """

    queryset = ClinicalFormGenerationRequest.objects.all()
    serializer_class = ClinicalFormGenerationRequestSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        if not (check_permission(self.request, HMSPermissions.CLINICAL_VIEW) or check_permission(self.request, HMSPermissions.CLINICAL_CREATE) or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)):
            raise PermissionDenied("No permission to view AI form drafts.")
        return super().get_queryset()

    def perform_create(self, serializer):
        raise NotImplementedError("Use the generate action via POST instead.")

    @extend_schema(
        summary="Generate a clinical form draft",
        description="Create a generation request and call OpenAI to produce a form draft.",
        tags=["Clinical AI Wizard"],
        request=GenerateFormRequestSerializer,
        responses={201: ClinicalFormGenerationRequestSerializer},
    )
    def create(self, request, *args, **kwargs):
        if not check_permission(request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to generate clinical forms.")

        payload = GenerateFormRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        generation_request = ClinicalFormGenerationRequest.objects.create(
            tenant_id=request.tenant_id,
            prompt=payload.validated_data["prompt"],
            extra_instructions=payload.validated_data.get("extra_instructions", ""),
            entity_type=payload.validated_data.get("entity_type", ClinicalForm.EntityType.GENERIC),
            status=ClinicalFormGenerationRequest.Status.PENDING,
            created_by_user_id=request.user_id,
        )

        draft, error = generate_form_draft(
            prompt=generation_request.prompt,
            entity_type=generation_request.entity_type,
            extra_instructions=generation_request.extra_instructions,
        )

        if error:
            generation_request.status = ClinicalFormGenerationRequest.Status.FAILED
            generation_request.error_message = error
            generation_request.save(update_fields=["status", "error_message", "updated_at"])
            return error_response(
                code=error_codes.AI_GENERATION_FAILED,
                message=error,
                status=status.HTTP_502_BAD_GATEWAY,
            )

        generation_request.status = ClinicalFormGenerationRequest.Status.COMPLETED
        generation_request.generated_draft = draft
        generation_request.save(update_fields=["status", "generated_draft", "updated_at"])

        return action_response(
            message="Clinical form draft generated successfully.",
            data=ClinicalFormGenerationRequestSerializer(
                generation_request, context={"request": request}
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Apply an AI-generated form draft",
        description="Migrate the draft into real ClinicalForm, sections, fields and picklists.",
        tags=["Clinical AI Wizard"],
        request=ApplyFormDraftSerializer,
        responses={200: ClinicalFormStructureSerializer},
    )
    @action(detail=True, methods=["post"], url_path="apply")
    def apply(self, request, pk=None):
        if not check_permission(request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to apply clinical form drafts.")

        generation_request = self.get_object()
        payload = ApplyFormDraftSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        if (
            generation_request.status == ClinicalFormGenerationRequest.Status.APPLIED
            and not payload.validated_data.get("dry_run")
        ):
            return error_response(
                code=error_codes.DRAFT_ALREADY_APPLIED,
                message="This draft has already been applied. Regenerate or clone it instead.",
                status=status.HTTP_409_CONFLICT,
            )

        result, err = _apply_form_draft(
            request,
            generation_request,
            target_code=payload.validated_data.get("target_code") or None,
            dry_run=payload.validated_data.get("dry_run", False),
        )
        if err:
            return error_response(**err)

        if payload.validated_data.get("dry_run"):
            return action_response(
                message="Dry-run completed. No records were created.",
                data=result,
            )

        form = ClinicalForm.objects.get(pk=result["form_id"], tenant_id=request.tenant_id)
        return action_response(
            message="Clinical form created from AI draft.",
            data={
                **result,
                "form": ClinicalFormStructureSerializer(form, context={"request": request}).data,
            },
        )

    @extend_schema(
        summary="Regenerate an AI form draft",
        description="Resubmit the original prompt with optional extra instructions and update the draft.",
        tags=["Clinical AI Wizard"],
        request=RegenerateFormRequestSerializer,
        responses={200: ClinicalFormGenerationRequestSerializer},
    )
    @action(detail=True, methods=["post"], url_path="regenerate")
    def regenerate(self, request, pk=None):
        if not check_permission(request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to regenerate clinical form drafts.")

        generation_request = self.get_object()
        payload = RegenerateFormRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        extra = payload.validated_data.get("extra_instructions", "").strip()
        combined_extra = generation_request.extra_instructions
        if extra:
            combined_extra = f"{combined_extra}\n\nAdditional revision: {extra}".strip()

        generation_request.status = ClinicalFormGenerationRequest.Status.PENDING
        generation_request.error_message = ""
