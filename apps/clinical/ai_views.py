"""AI-powered clinical form creator wizard API.

Endpoints live under ``/api/clinical/ai-wizard/`` and are backed by
``ClinicalFormGenerationRequest``. The AI produces a *draft* (see ``ai.py``)
which a human then applies. Applying:

  * ``create_form``      -> new ClinicalForm (staging) + reusable sections +
                            placements + fields + picklists + tabs.
  * ``update_form``      -> additively extend an existing form (add sections,
                            add fields to existing sections, add picklists,
                            merge tabs). The form is re-staged for review.
  * ``create_picklists`` -> only create reusable picklists.

Everything created/updated by the AI lands in ``staging`` status and must be
reviewed and published by a human.
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
    FormSectionPlacement,
)
from .serializers import (
    ApplyFormDraftSerializer,
    ClinicalFormGenerationRequestSerializer,
    ClinicalFormStructureSerializer,
    GenerateFormRequestSerializer,
    RegenerateFormRequestSerializer,
)

logger = structlog.get_logger(__name__)

_FIELD_TYPE_SET = {c[0] for c in ClinicalFormField.FieldType.choices}
_VALID_OPERATIONS = {"create_form", "update_form", "create_picklists"}


def _bust_form_cache(form_id: int):
    try:
        cache = CeliyoCache()
        cache.delete_pattern(f"clinical:form:{form_id}:*")
    except Exception as exc:
        logger.warning("form_cache_bust_failed", form_id=form_id, error=str(exc))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_picklists(picklists) -> tuple[bool, str]:
    if not isinstance(picklists, list) or not picklists:
        return False, "At least one picklist is required."
    for p in picklists:
        if not isinstance(p, dict) or not p.get("code"):
            return False, "A picklist is missing 'code'."
        items = p.get("items")
        if not isinstance(items, list) or not items:
            return False, f"Picklist '{p.get('code')}' must contain at least one item."
        for it in items:
            if not isinstance(it, dict) or not it.get("label"):
                return False, f"A picklist item in '{p.get('code')}' is missing 'label'."
    return True, ""


def _validate_sections(sections) -> tuple[bool, str]:
    if not isinstance(sections, list) or not sections:
        return False, "Draft must contain at least one section."
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
            fkey, ftype, label = field.get("field_key"), field.get("field_type"), field.get("label")
            if not fkey or not ftype or not label:
                return False, f"Field at section {s_idx}, index {f_idx} is missing required keys."
            if ftype not in _FIELD_TYPE_SET:
                return False, f"Field '{fkey}' has unsupported field_type '{ftype}'."
            if ftype in ("picklist", "multiselect") and not field.get("picklist_code"):
                return False, f"Field '{fkey}' of type '{ftype}' must reference a 'picklist_code'."
            if fkey in field_keys:
                return False, f"Duplicate field_key '{fkey}' across the form."
            field_keys.add(fkey)
    return True, ""


def _validate_draft(draft: dict) -> tuple[bool, str]:
    """Structural validation of an AI draft, branching on 'operation'."""
    if not isinstance(draft, dict):
        return False, "Generated draft is not a JSON object."

    operation = draft.get("operation", "create_form")
    if operation not in _VALID_OPERATIONS:
        return False, f"Unknown operation '{operation}'."

    if operation == "create_picklists":
        return _validate_picklists(draft.get("picklists"))

    if operation == "update_form":
        if not draft.get("target_form_code"):
            return False, "update_form requires 'target_form_code'."
    else:  # create_form
        if not draft.get("code"):
            return False, "create_form requires a form 'code'."

    ok, reason = _validate_sections(draft.get("sections"))
    if not ok:
        return False, reason

    if draft.get("picklists"):
        ok, reason = _validate_picklists(draft["picklists"])
        if not ok:
            return False, reason

    return True, ""


# ---------------------------------------------------------------------------
# Apply helpers (must run inside a transaction)
# ---------------------------------------------------------------------------

def _sync_picklists(draft_picklists, tenant_id, user_id, dry_run):
    """Reuse existing picklists by code; create the rest. Returns (map, plan)."""
    picklist_map: dict[str, ClinicalPicklist] = {}
    plan: list[dict] = []
    for p in draft_picklists or []:
        code = normalize_code(p.get("code", ""))
        if not code:
            continue
        existing = ClinicalPicklist.objects.filter(tenant_id=tenant_id, code=code).first()
        if existing:
            picklist_map[code] = existing
            plan.append({"code": code, "action": "existing", "id": existing.id})
            continue
        if dry_run:
            plan.append({"code": code, "action": "would_create", "items": len(p.get("items", []))})
            continue
        obj = ClinicalPicklist.objects.create(
            tenant_id=tenant_id,
            code=code,
            name=p.get("name", code),
            description=p.get("description", ""),
            created_by_user_id=user_id,
        )
        for i, item in enumerate(p.get("items", [])):
            value = (str(item.get("value") or item.get("label") or "")).strip()
            ClinicalPicklistItem.objects.create(
                tenant_id=tenant_id,
                picklist=obj,
                label=item.get("label", ""),
                label_mr=item.get("label_mr", ""),
                value=value,
                display_order=item.get("display_order", i),
                created_by_user_id=user_id,
            )
        picklist_map[code] = obj
        plan.append({"code": code, "action": "created", "id": obj.id})
    return picklist_map, plan


def _resolve_picklist(code, tenant_id, picklist_map):
    if not code:
        return None
    code = normalize_code(code)
    if code in picklist_map:
        return picklist_map[code]
    existing = ClinicalPicklist.objects.filter(tenant_id=tenant_id, code=code).first()
    if existing:
        picklist_map[code] = existing
    return existing


def _create_fields(section, field_drafts, tenant_id, user_id, picklist_map, skip_keys=None):
    """Create fields on a section, skipping field_keys already present."""
    skip = set(skip_keys or [])
    created = 0
    for f_order, fd in enumerate(field_drafts or []):
        fkey = normalize_code(fd.get("field_key", f"field_{f_order}"))
        if fkey in skip:
            continue
        pcode = fd.get("picklist_code")
        picklist = _resolve_picklist(pcode, tenant_id, picklist_map) if pcode else None
        ClinicalFormField.objects.create(
            tenant_id=tenant_id,
            section=section,
            field_key=fkey,
            field_type=fd.get("field_type"),
            label=fd.get("label", ""),
            label_mr=fd.get("label_mr", ""),
            help_text=fd.get("help_text", ""),
            display_order=fd.get("display_order", f_order),
            is_required=fd.get("is_required", False),
            is_read_only=fd.get("is_read_only", False),
            default_value=fd.get("default_value", None),
            config=fd.get("config") or {},
            picklist=picklist,
            created_by_user_id=user_id,
        )
        created += 1
    return created


def _section_code_for(form_code, raw_code):
    """Sections are reusable and tenant-unique; prefix with the form code."""
    prefixed = f"{form_code}_{raw_code}"
    return prefixed[:64]


def _create_section_with_placement(form, section_draft, order, tenant_id, user_id, picklist_map):
    raw_code = normalize_code(section_draft.get("code", f"section_{order}"))
    section = ClinicalFormSection.objects.create(
        tenant_id=tenant_id,
        code=_section_code_for(form.code, raw_code),
        title=section_draft.get("title", ""),
        description=section_draft.get("description", ""),
        config=section_draft.get("config") or {},
        created_by_user_id=user_id,
    )
    placement_config: dict = {}
    if section_draft.get("tab"):
        placement_config["tab"] = normalize_code(section_draft["tab"], max_length=40)
    FormSectionPlacement.objects.create(
        tenant_id=tenant_id,
        form=form,
        section=section,
        display_order=section_draft.get("display_order", order),
        is_collapsed=section_draft.get("is_collapsed", False),
        config=placement_config,
        created_by_user_id=user_id,
    )
    _create_fields(section, section_draft.get("fields", []), tenant_id, user_id, picklist_map)
    return section


def _merge_tabs(config: dict, draft: dict) -> dict:
    """Merge draft tabs into a form config (dedupe by key)."""
    tabs = draft.get("tabs")
    if not tabs:
        return config
    config = dict(config or {})
    existing = {t.get("key"): t for t in (config.get("tabs") or []) if isinstance(t, dict)}
    for t in tabs:
        if isinstance(t, dict) and t.get("key"):
            existing[normalize_code(t["key"], max_length=40)] = {**t, "key": normalize_code(t["key"], max_length=40)}
    config["tabs"] = list(existing.values())
    return config


# ---------------------------------------------------------------------------
# Apply dispatchers
# ---------------------------------------------------------------------------

def _apply_create_form(request, draft, generation_request, target_code, dry_run):
    tenant_id, user_id = request.tenant_id, request.user_id
    form_code = normalize_code(target_code or draft.get("code", "generated_form"))

    if ClinicalForm.objects.filter(tenant_id=tenant_id, code=form_code).exists():
        return None, {
            "code": error_codes.RECORD_ALREADY_EXISTS,
            "message": f"A form with code '{form_code}' already exists. Use update_form or a new code.",
            "status": status.HTTP_409_CONFLICT,
        }

    # Referenced picklists must be defined in the draft or already exist in the tenant.
    defined = {normalize_code(p.get("code", "")) for p in (draft.get("picklists") or [])}
    missing = set()
    for section in draft.get("sections", []):
        for field in section.get("fields", []):
            pc = field.get("picklist_code")
            if pc:
                pc = normalize_code(pc)
                if pc not in defined and not ClinicalPicklist.objects.filter(tenant_id=tenant_id, code=pc).exists():
                    missing.add(pc)
    if missing:
        return None, {
            "code": error_codes.INVALID_FORM_DRAFT,
            "message": f"Referenced picklists are not defined and do not exist: {sorted(missing)}.",
            "status": status.HTTP_400_BAD_REQUEST,
        }

    if dry_run:
        _, plan = _sync_picklists(draft.get("picklists"), tenant_id, user_id, dry_run=True)
        return {
            "operation": "create_form",
            "form_code": form_code,
            "form_name": draft.get("name"),
            "entity_type": draft.get("entity_type", generation_request.entity_type),
            "sections_count": len(draft.get("sections", [])),
            "fields_count": sum(len(s.get("fields", [])) for s in draft.get("sections", [])),
            "picklists": plan,
            "dry_run": True,
        }, None

    with transaction.atomic():
        picklist_map, plan = _sync_picklists(draft.get("picklists"), tenant_id, user_id, dry_run=False)
        config = _merge_tabs(draft.get("config") or {}, draft)
        form = ClinicalForm.objects.create(
            tenant_id=tenant_id,
            code=form_code,
            name=draft.get("name", form_code),
            description=draft.get("description", ""),
            entity_type=draft.get("entity_type", generation_request.entity_type),
            config=config,
            status=ClinicalForm.Status.STAGING,
            created_by_user_id=user_id,
        )
        for s_order, section_draft in enumerate(draft.get("sections", [])):
            _create_section_with_placement(form, section_draft, s_order, tenant_id, user_id, picklist_map)

        generation_request.status = ClinicalFormGenerationRequest.Status.APPLIED
        generation_request.applied_form = form
        generation_request.save(update_fields=["status", "applied_form", "updated_at"])

    _bust_form_cache(form.id)
    return {
        "operation": "create_form",
        "form_id": form.id,
        "form_code": form.code,
        "form_name": form.name,
        "entity_type": form.entity_type,
        "status": form.status,
        "structure_url": f"/api/clinical/forms/{form.id}/structure/",
        "picklists": plan,
        "generation_request_id": generation_request.id,
    }, None


def _apply_update_form(request, draft, generation_request, dry_run):
    tenant_id, user_id = request.tenant_id, request.user_id
    target = normalize_code(draft.get("target_form_code", ""))
    form = ClinicalForm.objects.filter(tenant_id=tenant_id, code=target).first()
    if not form:
        return None, {
            "code": error_codes.NOT_FOUND,
            "message": f"No form with code '{target}' exists in this tenant.",
            "status": status.HTTP_404_NOT_FOUND,
        }

    if dry_run:
        _, plan = _sync_picklists(draft.get("picklists"), tenant_id, user_id, dry_run=True)
        return {
            "operation": "update_form",
            "target_form_code": target,
            "sections_incoming": len(draft.get("sections", [])),
            "fields_incoming": sum(len(s.get("fields", [])) for s in draft.get("sections", [])),
            "picklists": plan,
            "note": "Additive: existing sections/fields are preserved; only new ones are added.",
            "dry_run": True,
        }, None

    with transaction.atomic():
        picklist_map, plan = _sync_picklists(draft.get("picklists"), tenant_id, user_id, dry_run=False)

        # Map existing sections on this form by both their stored code and the
        # unprefixed suffix, so the AI can reference them by the short code.
        placements = FormSectionPlacement.objects.filter(
            tenant_id=tenant_id, form=form
        ).select_related("section")
        existing_by_code: dict[str, ClinicalFormSection] = {}
        max_order = -1
        for pl in placements:
            existing_by_code[pl.section.code] = pl.section
            prefix = f"{form.code}_"
            if pl.section.code.startswith(prefix):
                existing_by_code[pl.section.code[len(prefix):]] = pl.section
            max_order = max(max_order, pl.display_order)

        added_sections = 0
        added_fields = 0
        for section_draft in draft.get("sections", []):
            raw = normalize_code(section_draft.get("code", ""))
            match = existing_by_code.get(raw) or existing_by_code.get(_section_code_for(form.code, raw))
            if match:
                existing_field_keys = set(
                    match.fields.filter(tenant_id=tenant_id).values_list("field_key", flat=True)
                )
                added_fields += _create_fields(
                    match, section_draft.get("fields", []), tenant_id, user_id, picklist_map,
                    skip_keys=existing_field_keys,
                )
            else:
                max_order += 1
                _create_section_with_placement(form, section_draft, max_order, tenant_id, user_id, picklist_map)
                added_sections += 1
                added_fields += len(section_draft.get("fields", []))

        # Merge tabs, re-stage for review, and bump version to bust caches.
        form.config = _merge_tabs(form.config or {}, draft)
        form.status = ClinicalForm.Status.STAGING
        form.version = (form.version or 1) + 1
        form.save(update_fields=["config", "status", "version", "updated_at"])

        generation_request.status = ClinicalFormGenerationRequest.Status.APPLIED
        generation_request.applied_form = form
        generation_request.save(update_fields=["status", "applied_form", "updated_at"])

    _bust_form_cache(form.id)
    return {
        "operation": "update_form",
        "form_id": form.id,
        "form_code": form.code,
        "status": form.status,
        "added_sections": added_sections,
        "added_fields": added_fields,
        "picklists": plan,
        "structure_url": f"/api/clinical/forms/{form.id}/structure/",
        "generation_request_id": generation_request.id,
    }, None


def _apply_picklists_only(request, draft, generation_request, dry_run):
    tenant_id, user_id = request.tenant_id, request.user_id
    if dry_run:
        _, plan = _sync_picklists(draft.get("picklists"), tenant_id, user_id, dry_run=True)
        return {"operation": "create_picklists", "picklists": plan, "dry_run": True}, None

    with transaction.atomic():
        _, plan = _sync_picklists(draft.get("picklists"), tenant_id, user_id, dry_run=False)
        generation_request.status = ClinicalFormGenerationRequest.Status.APPLIED
        generation_request.save(update_fields=["status", "updated_at"])
    return {"operation": "create_picklists", "picklists": plan}, None


def _apply_form_draft(request, generation_request, target_code, dry_run):
    """Apply a validated draft, dispatching on its operation."""
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

    operation = draft.get("operation", "create_form")
    if operation == "create_picklists":
        return _apply_picklists_only(request, draft, generation_request, dry_run)
    if operation == "update_form":
        return _apply_update_form(request, draft, generation_request, dry_run)
    return _apply_create_form(request, draft, generation_request, target_code, dry_run)


# ---------------------------------------------------------------------------
# ViewSet
# ---------------------------------------------------------------------------

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
        description=(
            "Send a natural-language prompt (and optionally an image via "
            "'image_data_url') to the model and store the generated draft."
        ),
        tags=["Clinical AI Wizard"],
        request=GenerateFormRequestSerializer,
        responses={201: ClinicalFormGenerationRequestSerializer},
    ),
)
class ClinicalFormAIWizardViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """AI clinical form creator wizard (create form / update form / picklists)."""

    queryset = ClinicalFormGenerationRequest.objects.all()
    serializer_class = ClinicalFormGenerationRequestSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        if not (
            check_permission(self.request, HMSPermissions.CLINICAL_VIEW)
            or check_permission(self.request, HMSPermissions.CLINICAL_CREATE)
            or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)
        ):
            raise PermissionDenied("No permission to view AI form drafts.")
        return super().get_queryset()

    def perform_create(self, serializer):
        raise NotImplementedError("Use the generate action via POST instead.")

    @extend_schema(
        summary="Generate a clinical form draft",
        description="Create a generation request and call the model to produce a draft.",
        tags=["Clinical AI Wizard"],
        request=GenerateFormRequestSerializer,
        responses={201: ClinicalFormGenerationRequestSerializer},
    )
    def create(self, request, *args, **kwargs):
        if not check_permission(request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to generate clinical forms.")

        payload = GenerateFormRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        # Optional image (data URL) for transcribing a photo/scan of a paper form.
        image_data_url = request.data.get("image_data_url") or None

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
            image_data_url=image_data_url,
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
        description=(
            "Apply the draft. Depending on the draft's 'operation' this creates a new "
            "staging form, additively updates an existing form, or creates picklists. "
            "Pass dry_run=true to preview without writing."
        ),
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

        # Attach the full structure for form operations.
        form_id = result.get("form_id")
        if form_id:
            form = ClinicalForm.objects.get(pk=form_id, tenant_id=request.tenant_id)
            result = {
                **result,
                "form": ClinicalFormStructureSerializer(form, context={"request": request}).data,
            }
        return action_response(message="AI draft applied.", data=result)

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
        generation_request.save(update_fields=["status", "error_message", "updated_at"])

        draft, error = generate_form_draft(
            prompt=generation_request.prompt,
            entity_type=generation_request.entity_type,
            extra_instructions=combined_extra,
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
        generation_request.extra_instructions = combined_extra
        generation_request.save(
            update_fields=["status", "generated_draft", "extra_instructions", "updated_at"]
        )

        return action_response(
            message="Draft regenerated.",
            data=ClinicalFormGenerationRequestSerializer(
                generation_request, context={"request": request}
            ).data,
        )
