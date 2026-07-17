"""API views for the clinical forms and records app."""

import hashlib
import json
import structlog
import uuid
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from common import error_codes
from common.cache import CeliyoCache
from common.drf_auth import HMSPermission
from common.permissions import HMSPermissions, IsTenantAuthenticated, check_permission
from common.mixins import CachedFormStructureMixin, PatientAccessMixin, TenantViewSetMixin
from common.pagination import StandardPagination
from common.responses import action_response, error_response

from .filters import (
    ClinicalFormFilter,
    ClinicalFormSectionFilter,
    ClinicalPicklistItemFilter,
    ClinicalRecordFilter,
)
from .models import (
    ClinicalDocumentInstance,
    ClinicalDocumentTemplate,
    ClinicalFieldValue,
    ClinicalForm,
    ClinicalFormField,
    ClinicalFormGroup,
    ClinicalFormGroupItem,
    ClinicalFormSection,
    ClinicalFormTemplate,
    ClinicalPicklist,
    ClinicalPicklistGroup,
    ClinicalPicklistGroupMembership,
    ClinicalPicklistItem,
    ClinicalPrintTemplate,
    ClinicalRecord,
    ClinicalRecordAuditLog,
    FormSectionPlacement,
    MrdChecklistLine,
    SavedFormSnapshot,
    UserFormPreference,
)
from .serializers import (
    ClinicalDocumentInstanceSerializer,
    ClinicalDocumentTemplateSerializer,
    ClinicalFieldValueSerializer,
    ClinicalFormFieldSerializer,
    ClinicalFormGroupItemSerializer,
    ClinicalFormGroupSerializer,
    ClinicalFormSerializer,
    ClinicalFormSectionWriteSerializer,
    ClinicalFormStructureSerializer,
    ClinicalPicklistGroupMembershipSerializer,
    ClinicalPicklistGroupSerializer,
    ClinicalPicklistItemSerializer,
    ClinicalPicklistSerializer,
    ClinicalPrintTemplateSerializer,
    ClinicalFormTemplateSerializer,
    ClinicalRecordDetailSerializer,
    ClinicalRecordListSerializer,
    ClinicalRecordWriteSerializer,
    FormSectionPlacementSerializer,
    FieldValueBulkUpsertSerializer,
    MrdChecklistLineSerializer,
    SavedFormSnapshotSerializer,
    UserFormPreferenceSerializer,
    coerce_field_value,
)


CLINICAL_ENCOUNTER_CONTENT_TYPES = {
    "opd_visit": ("opd", "visit"),
    "opd.visit": ("opd", "visit"),
    "ipd_admission": ("ipd", "admission"),
    "ipd.admission": ("ipd", "admission"),
}

logger = structlog.get_logger(__name__)

_SYSTEM_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _audit(
    tenant_id,
    record_id,
    action,
    user_id,
    metadata=None,
):
    """Persist an audit entry without making the clinical write broker-dependent."""
    try:
        ClinicalRecordAuditLog.objects.create(
            tenant_id=tenant_id,
            record_id=record_id,
            action=action,
            user_id=user_id,
            metadata=metadata or {},
            created_by_user_id=user_id,
        )
    except Exception as exc:
        # The primary clinical write has already succeeded.  Audit storage is
        # best-effort here and must never turn a Redis/DB outage into a 500.
        logger.error(
            "clinical_audit_log_create_failed",
            tenant_id=str(tenant_id),
            record_id=record_id,
            action=action,
            error=str(exc),
        )


def _field_value_to_plain(value_obj):
    """Return the typed value stored on a ClinicalFieldValue as JSON-friendly data."""
    field_type = value_obj.field.field_type
    if field_type == ClinicalFormField.FieldType.NUMBER:
        return float(value_obj.value_number) if value_obj.value_number is not None else None
    if field_type == ClinicalFormField.FieldType.BOOLEAN:
        return value_obj.value_boolean
    if field_type == ClinicalFormField.FieldType.DATE:
        return value_obj.value_date.isoformat() if value_obj.value_date else None
    if field_type == ClinicalFormField.FieldType.DATETIME:
        return value_obj.value_datetime.isoformat() if value_obj.value_datetime else None
    if field_type == ClinicalFormField.FieldType.TIME:
        return value_obj.value_time.isoformat() if value_obj.value_time else None
    if field_type in (
        ClinicalFormField.FieldType.GRID,
        ClinicalFormField.FieldType.MULTISELECT,
        ClinicalFormField.FieldType.DATA_REF,
    ):
        return value_obj.value_json
    if value_obj.picklist_item_id:
        return value_obj.picklist_item.label
    return value_obj.value_text


def _prescription_row_key(row, index):
    if not isinstance(row, dict):
        return f"row:{index}"
    return str(
        row.get("row_id")
        or row.get("id")
        or row.get("client_id")
        or f"{index}:{row.get('medicine_name') or row.get('medicine') or row.get('drug_name') or ''}"
    )


def _grid_quantity(value):
    from decimal import Decimal, InvalidOperation

    if value in (None, ""):
        return Decimal("1.00")
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("1.00")
    return quantity if quantity > 0 else Decimal("1.00")


def _sync_prescription_grid_to_pharmacy(record, field, rows, user_id):
    """Reconcile a prescription GRID field into pharmacy Prescription/PrescriptionItem."""
    if field.field_type != ClinicalFormField.FieldType.GRID:
        return None
    if (field.section.config or {}).get("role") != "prescription":
        return None
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        rows = []

    from apps.pharmacy.models import Prescription, PrescriptionItem
    from apps.pharmacy.serializers import PrescriptionSerializer

    encounter_type = record.encounter_type
    if encounter_type not in CLINICAL_ENCOUNTER_CONTENT_TYPES:
        return None

    content_type = PrescriptionSerializer.resolve_encounter_type(encounter_type)
    defaults = {
        "tenant_id": record.tenant_id,
        "content_type": content_type,
        "object_id": record.encounter_id,
        "created_by_user_id": user_id,
    }
    if content_type.app_label == "opd" and content_type.model == "visit":
        defaults["visit_id"] = record.encounter_id

    prescription = (
        Prescription.objects.filter(
            tenant_id=record.tenant_id,
            content_type=content_type,
            object_id=record.encounter_id,
        )
        .order_by("-created_at")
        .first()
    )
    if prescription is None:
        prescription = Prescription.objects.create(**defaults)
    if prescription.visit_id is None and defaults.get("visit_id"):
        prescription.visit_id = defaults["visit_id"]
        prescription.save(update_fields=["visit", "updated_at"])

    existing_items = list(
        PrescriptionItem.objects.filter(
            tenant_id=record.tenant_id,
            prescription=prescription,
        ).order_by("created_at", "id")
    )
    existing_by_key = {}
    for index, item in enumerate(existing_items):
        if item.source_row_key:
            existing_by_key[item.source_row_key] = item
        existing_by_key[f"{index}:{item.medicine_name or ''}"] = item

    seen_item_ids = set()
    for index, raw_row in enumerate(rows):
        row = raw_row if isinstance(raw_row, dict) else {}
        medicine_name = (
            row.get("medicine_name")
            or row.get("medicine")
            or row.get("drug_name")
            or row.get("name")
            or ""
        )
        medicine_name = str(medicine_name).strip()
        if not medicine_name:
            continue

        row_key = _prescription_row_key(row, index)
        fallback_key = f"{index}:{medicine_name}"
        item = existing_by_key.get(row_key) or existing_by_key.get(fallback_key)
        defaults = {
            "inventory_item": None,
            "source_row_key": row_key,
            "medicine_name": medicine_name,
            "dosage": str(row.get("dosage") or row.get("dose") or ""),
            "frequency": str(row.get("frequency") or ""),
            "duration": str(row.get("duration") or ""),
            "quantity": _grid_quantity(row.get("quantity")),
        }
        if item is None:
            item = PrescriptionItem.objects.create(
                tenant_id=record.tenant_id,
                prescription=prescription,
                **defaults,
            )
        elif not item.is_dispensed:
            for attr, value in defaults.items():
                setattr(item, attr, value)
            item.save(
                update_fields=[
                    "inventory_item",
                    "source_row_key",
                    "medicine_name",
                    "dosage",
                    "frequency",
                    "duration",
                    "quantity",
                    "updated_at",
                ]
            )
        seen_item_ids.add(item.id)

    PrescriptionItem.objects.filter(
        tenant_id=record.tenant_id,
        prescription=prescription,
    ).exclude(id__in=seen_item_ids).filter(is_dispensed=False).delete()

    prescription.recalculate_status()
    prescription.save(update_fields=["status", "updated_at"])
    return prescription


def _investigation_ids_from_grid_rows(rows):
    if rows is None:
        return []
    if not isinstance(rows, list):
        return []
    ids = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = row.get("investigation_id")
        if value in (None, ""):
            continue
        ids.append(value)
    return ids


def _order_investigations_for_record(record, investigation_ids, tenant_id, user_id):
    """Idempotently create DiagnosticOrders for a clinical record encounter."""
    if not isinstance(investigation_ids, list) or not investigation_ids:
        return {
            "error": error_codes.INVALID_PAYLOAD,
            "message": "investigation_ids must be a non-empty list.",
            "status": status.HTTP_400_BAD_REQUEST,
        }

    try:
        normalized_ids = sorted({int(value) for value in investigation_ids})
    except (TypeError, ValueError):
        return {
            "error": error_codes.INVALID_PAYLOAD,
            "message": "investigation_ids must contain integer IDs.",
            "status": status.HTTP_400_BAD_REQUEST,
        }

    encounter_key = str(record.encounter_type or "").lower()
    if encounter_key not in CLINICAL_ENCOUNTER_CONTENT_TYPES:
        return {
            "error": error_codes.INVALID_PAYLOAD,
            "message": f"Unsupported encounter_type '{record.encounter_type}'.",
            "status": status.HTTP_400_BAD_REQUEST,
        }

    from apps.diagnostics.models import DiagnosticOrder, Investigation, Requisition
    from apps.diagnostics.serializers import RequisitionSerializer

    app_label, model_name = CLINICAL_ENCOUNTER_CONTENT_TYPES[encounter_key]
    content_type = ContentType.objects.get(app_label=app_label, model=model_name)
    try:
        encounter = content_type.get_object_for_this_type(
            id=record.encounter_id,
            tenant_id=tenant_id,
        )
    except content_type.model_class().DoesNotExist:
        return {
            "error": error_codes.RECORD_NOT_FOUND,
            "message": "Encounter not found.",
            "status": status.HTTP_404_NOT_FOUND,
        }

    patient = getattr(encounter, "patient", None)
    if patient is None:
        return {
            "error": error_codes.INVALID_PAYLOAD,
            "message": "Encounter does not expose a patient.",
            "status": status.HTTP_400_BAD_REQUEST,
        }

    investigations = {
        investigation.id: investigation
        for investigation in Investigation.objects.filter(
            tenant_id=tenant_id,
            id__in=normalized_ids,
            is_active=True,
        )
    }
    missing = sorted(set(normalized_ids) - set(investigations.keys()))
    if missing:
        return {
            "error": error_codes.RECORD_NOT_FOUND,
            "message": f"Investigation(s) not found: {missing}.",
            "status": status.HTTP_404_NOT_FOUND,
        }

    with transaction.atomic():
        requisition = (
            Requisition.objects.filter(
                tenant_id=tenant_id,
                content_type=content_type,
                object_id=record.encounter_id,
                requisition_type="investigation",
            )
            .exclude(status="cancelled")
            .order_by("-created_at")
            .first()
        )
        if requisition is None:
            requisition = Requisition.objects.create(
                tenant_id=tenant_id,
                content_type=content_type,
                object_id=record.encounter_id,
                requisition_type="investigation",
                patient=patient,
                requesting_doctor_id=user_id,
                clinical_notes=f"Created from clinical record {record.id}",
            )

        existing_ids = set(
            DiagnosticOrder.objects.filter(
                tenant_id=tenant_id,
                requisition=requisition,
                investigation_id__in=normalized_ids,
            ).values_list("investigation_id", flat=True)
        )
        created_orders = []
        for investigation_id in normalized_ids:
            if investigation_id in existing_ids:
                continue
            investigation = investigations[investigation_id]
            created_orders.append(
                DiagnosticOrder.objects.create(
                    tenant_id=tenant_id,
                    requisition=requisition,
                    investigation=investigation,
                    price=investigation.base_charge,
                    status="pending",
                )
            )

    return {
        "requisition": requisition,
        "requisition_data": RequisitionSerializer(requisition).data,
        "created_order_ids": [order.id for order in created_orders],
        "existing_investigation_ids": sorted(existing_ids),
    }


def _sync_investigation_grid_to_diagnostics(record, field, rows, user_id):
    """Convert an investigation GRID field into DiagnosticOrder rows."""
    if field.field_type != ClinicalFormField.FieldType.GRID:
        return None
    if (field.section.config or {}).get("role") != "investigation":
        return None
    investigation_ids = _investigation_ids_from_grid_rows(rows)
    if not investigation_ids:
        return None
    result = _order_investigations_for_record(
        record=record,
        investigation_ids=investigation_ids,
        tenant_id=record.tenant_id,
        user_id=user_id,
    )
    if result and "error" in result:
        raise ValidationError({"investigations": result["message"]})
    return result


# ---------------------------------------------------------------------------
# ClinicalForm
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List clinical forms",
        description="List clinical form templates for the current tenant.",
        tags=["Clinical Forms"],
        responses={200: ClinicalFormSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve a clinical form",
        description="Retrieve a single clinical form template.",
        tags=["Clinical Forms"],
        responses={200: ClinicalFormSerializer},
    ),
    create=extend_schema(
        summary="Create a clinical form",
        description="Create a new clinical form template.",
        tags=["Clinical Forms"],
        responses={201: ClinicalFormSerializer},
    ),
    update=extend_schema(
        summary="Update a clinical form",
        description="Replace a clinical form template.",
        tags=["Clinical Forms"],
        responses={200: ClinicalFormSerializer},
    ),
    partial_update=extend_schema(
        summary="Patch a clinical form",
        description="Partially update a clinical form template.",
        tags=["Clinical Forms"],
        responses={200: ClinicalFormSerializer},
    ),
    destroy=extend_schema(
        summary="Delete a clinical form",
        description="Delete a clinical form template. System forms are protected.",
        tags=["Clinical Forms"],
        responses={204: None},
    ),
)
class ClinicalFormViewSet(
    CachedFormStructureMixin,
    TenantViewSetMixin,
    viewsets.ModelViewSet,
):
    """CRUD for reusable clinical form templates."""

    queryset = ClinicalForm.objects.all()
    serializer_class = ClinicalFormSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_class = ClinicalFormFilter
    search_fields = ["code", "name"]
    ordering_fields = ["created_at", "name", "version"]
    ordering = ["-created_at"]

    def get_queryset(self):
        # Permission is enforced by HMSPermission class (has_permission + has_object_permission).
        # Allow access if the user has CLINICAL_VIEW *or* any write permission on clinical
        # (avoids the common mis-config where create was granted but view was forgotten).
        can_access = (
            check_permission(self.request, HMSPermissions.CLINICAL_VIEW)
            or check_permission(self.request, HMSPermissions.CLINICAL_CREATE)
            or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)
        )
        if not can_access:
            raise PermissionDenied("No permission to view clinical forms.")
        tenant_id = self.request.tenant_id
        system_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        return ClinicalForm.objects.filter(
            Q(tenant_id=tenant_id) | Q(tenant_id=system_tenant_id, is_system=True)
        )

    def list(self, request, *args, **kwargs):
        cache = CeliyoCache()
        params_hash = hashlib.md5(
            request.query_params.urlencode().encode()
        ).hexdigest()[:12]
        cache_key = f"clinical:forms:{request.tenant_id}:{params_hash}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, ttl=600)
        return response

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create clinical forms.")
        serializer.save(created_by_user_id=self.request.user_id)
        CeliyoCache().delete_pattern(f"clinical:forms:{self.request.tenant_id}:*")

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update clinical forms.")
        if serializer.instance.is_system:
            raise PermissionDenied("System forms cannot be modified.")
        serializer.save()
        CeliyoCache().delete_pattern(f"clinical:forms:{self.request.tenant_id}:*")

    def _set_form_status(self, request, new_status, message):
        """Transition a form's lifecycle status (publish / stage / archive)."""
        if not check_permission(request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to change form status.")
        form = self.get_object()
        if form.is_system:
            raise PermissionDenied("System forms cannot be changed.")
        form.status = new_status
        form.version = (form.version or 1) + 1
        form.save(update_fields=["status", "version", "updated_at"])
        cache = CeliyoCache()
        cache.delete_pattern(f"clinical:forms:{request.tenant_id}:*")
        cache.delete_pattern(f"clinical:form:{form.id}:*")
        return action_response(
            message=message,
            data=ClinicalFormSerializer(form, context={"request": request}).data,
        )

    @extend_schema(
        summary="Publish a clinical form",
        description="Move a draft/staging form to 'published' so it becomes available for encounters.",
        tags=["Clinical Forms"],
        responses={200: ClinicalFormSerializer},
    )
    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        return self._set_form_status(request, ClinicalForm.Status.PUBLISHED, "Form published.")

    @extend_schema(
        summary="Send a form back to staging",
        description="Move a form to 'staging' for review (e.g. after AI edits).",
        tags=["Clinical Forms"],
        responses={200: ClinicalFormSerializer},
    )
    @action(detail=True, methods=["post"], url_path="stage")
    def stage(self, request, pk=None):
        return self._set_form_status(request, ClinicalForm.Status.STAGING, "Form moved to staging.")

    @extend_schema(
        summary="Archive a clinical form",
        description="Archive a form (e.g. discard an AI-generated draft you do not want).",
        tags=["Clinical Forms"],
        responses={200: ClinicalFormSerializer},
    )
    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        return self._set_form_status(request, ClinicalForm.Status.ARCHIVED, "Form archived.")

    @extend_schema(
        summary="List or create placements for a form",
        description="Attach reusable section definitions to this form, or list current placements.",
        tags=["Clinical Forms"],
        request=FormSectionPlacementSerializer,
        responses={200: FormSectionPlacementSerializer(many=True), 201: FormSectionPlacementSerializer},
    )
    @action(detail=True, methods=["get", "post"], url_path="placements")
    def placements(self, request, pk=None):
        form = self.get_object()
        if request.method.lower() == "get":
            placements = form.section_placements.filter(is_active=True).select_related("section").order_by("display_order", "id")
            return action_response(
                message="Form placements.",
                data=FormSectionPlacementSerializer(placements, many=True, context={"request": request}).data,
            )

        if not check_permission(request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create form placements.")
        serializer = FormSectionPlacementSerializer(data={**request.data, "form": form.id}, context={"request": request})
        serializer.is_valid(raise_exception=True)
        placement = serializer.save(created_by_user_id=request.user_id)
        self._bust_form_cache(form.id)
        return action_response(
            message="Form placement created.",
            data=FormSectionPlacementSerializer(placement, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="List forms for an encounter with filled state",
        description="Resolve forms for an encounter type, grouped for drawers/left rail, with completed/filled state.",
        tags=["Clinical Runtime"],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path=r"encounters/(?P<encounter_type>[^/.]+)/(?P<encounter_id>[^/.]+)/forms",
    )
    def encounter_forms(self, request, encounter_type=None, encounter_id=None):
        tenant_id = request.tenant_id
        system_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        forms = ClinicalForm.objects.filter(
            Q(tenant_id=tenant_id) | Q(tenant_id=system_tenant_id, is_system=True),
            Q(entity_type=encounter_type) | Q(entity_type=ClinicalForm.EntityType.GENERIC),
            is_active=True,
        )
        # Group every record by form so repeatable forms expose all occurrences.
        records_by_form: dict[int, list] = {}
        for record in ClinicalRecord.objects.filter(
            tenant_id=tenant_id,
            encounter_type=encounter_type,
            encounter_id=encounter_id,
            form_id__in=forms.values("id"),
            is_active=True,
        ).order_by("occurrence_index", "id"):
            records_by_form.setdefault(record.form_id, []).append(record)

        data = []
        for form in forms.order_by("name", "id"):
            form_records = records_by_form.get(form.id, [])
            # The latest occurrence is the "active" one for the form tile.
            latest = form_records[-1] if form_records else None
            occurrences = [
                {
                    "record_id": r.id,
                    "occurrence_index": r.occurrence_index,
                    "status": r.status,
                    "is_locked": r.is_locked,
                    "created_at": r.created_at,
                }
                for r in form_records
            ]
            data.append(
                {
                    "form": ClinicalFormSerializer(form, context={"request": request}).data,
                    "filled": bool(latest),
                    "completed": bool(latest and latest.status == ClinicalRecord.Status.COMPLETED),
                    "record_id": latest.id if latest else None,
                    "record_status": latest.status if latest else None,
                    "repeatable": bool((form.config or {}).get("repeatable")),
                    "occurrences": occurrences,
                }
            )
        return action_response(message="Encounter forms.", data=data)

    @extend_schema(
        summary="Resolve MRD checklist for an encounter",
        description="Computes Available / Missing / Not Applicable from completed records and document instances.",
        tags=["Clinical Runtime"],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path=r"encounters/(?P<encounter_type>[^/.]+)/(?P<encounter_id>[^/.]+)/mrd-checklist",
    )
    def mrd_checklist(self, request, encounter_type=None, encounter_id=None):
        tenant_id = request.tenant_id
        system_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        lines = MrdChecklistLine.objects.filter(
            Q(tenant_id=tenant_id) | Q(tenant_id=system_tenant_id, is_system=True),
            is_active=True,
        ).order_by("bucket", "display_order", "id")
        completed_form_codes = set(
            ClinicalRecord.objects.filter(
                tenant_id=tenant_id,
                encounter_type=encounter_type,
                encounter_id=encounter_id,
                status=ClinicalRecord.Status.COMPLETED,
                is_active=True,
            ).values_list("form__code", flat=True)
        )
        document_codes = set(
            ClinicalDocumentInstance.objects.filter(
                tenant_id=tenant_id,
                encounter_type=encounter_type,
                encounter_id=encounter_id,
                is_active=True,
            ).values_list("template__code", flat=True)
        )
        data = []
        for line in lines:
            applicable = not line.applicable_entity_types or encounter_type in line.applicable_entity_types
            if not applicable:
                state = "not_applicable"
            elif line.source_type == MrdChecklistLine.SourceType.FORM:
                state = "available" if line.source_code in completed_form_codes else "missing"
            elif line.source_type == MrdChecklistLine.SourceType.DOCUMENT:
                state = "available" if line.source_code in document_codes else "missing"
            else:
                state = "missing"
            data.append({**MrdChecklistLineSerializer(line, context={"request": request}).data, "state": state})
        return action_response(message="MRD checklist.", data=data)

    @extend_schema(
        summary="Pull field values from another encounter form",
        description=(
            "Return values from the latest completed/in-progress record for source_form "
            "within the same encounter. Query with source_form=<code>&fields=<csv>."
        ),
        tags=["Clinical Runtime"],
        parameters=[
            OpenApiParameter("source_form", str, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("fields", str, OpenApiParameter.QUERY, required=True),
        ],
        responses={200: dict},
    )
    @action(
        detail=False,
        methods=["get"],
        url_path=r"encounters/(?P<encounter_type>[^/.]+)/(?P<encounter_id>[^/.]+)/pull",
    )
    def pull(self, request, encounter_type=None, encounter_id=None):
        if not check_permission(request, HMSPermissions.CLINICAL_VIEW):
            raise PermissionDenied("No permission to view clinical records.")

        source_form_code = (request.query_params.get("source_form") or "").strip()
        field_keys = [
            key.strip()
            for key in (request.query_params.get("fields") or "").split(",")
            if key.strip()
        ]
        if not source_form_code or not field_keys:
            return error_response(
                code=error_codes.INVALID_PAYLOAD,
                message="source_form and fields query parameters are required.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        system_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        form = ClinicalForm.objects.filter(
            Q(tenant_id=request.tenant_id) | Q(tenant_id=system_tenant_id, is_system=True),
            code=source_form_code,
            is_active=True,
        ).first()
        if form is None:
            return error_response(
                code=error_codes.FORM_NOT_FOUND,
                message="Source form not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        record = (
            ClinicalRecord.objects.filter(
                tenant_id=request.tenant_id,
                form=form,
                encounter_type=encounter_type,
                encounter_id=encounter_id,
                is_active=True,
                status__in=[ClinicalRecord.Status.IN_PROGRESS, ClinicalRecord.Status.COMPLETED],
            )
            .order_by("-updated_at", "-id")
            .first()
        )
        if record is None:
            return action_response(message="No source record found.", data={})

        values = (
            ClinicalFieldValue.objects.filter(
                tenant_id=request.tenant_id,
                record=record,
                field__field_key__in=field_keys,
                is_active=True,
            )
            .select_related("field", "picklist_item")
            .order_by("field__display_order", "id")
        )
        data = {key: None for key in field_keys}
        for value_obj in values:
            data[value_obj.field.field_key] = _field_value_to_plain(value_obj)

        return action_response(message="Pulled field values.", data=data)

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete clinical forms.")
        if instance.is_system:
            raise PermissionDenied("System forms cannot be deleted.")
        tenant_id = self.request.tenant_id
        super().perform_destroy(instance)
        CeliyoCache().delete_pattern(f"clinical:forms:{tenant_id}:*")

    @extend_schema(
        summary="Get cached form structure",
        description="Return the full form with sections and fields. Cached under ``clinical:form:<id>:v<version>``.",
        tags=["Clinical Forms"],
        responses={200: ClinicalFormStructureSerializer},
    )
    @action(detail=True, methods=["get"], url_path="structure")
    def structure(self, request, pk=None):
        """Return the cached form structure (sections + fields)."""
        form = self.get_object()
        cache_key = f"clinical:form:{form.id}:v{form.version}"
        cache = CeliyoCache()

        try:
            cached = cache.get(cache_key)
        except Exception as exc:
            logger.warning(
                "clinical_form_structure_cache_read_failed",
                form_id=form.id,
                error=str(exc),
            )
            cached = None
        if cached is not None:
            logger.info("clinical_form_structure_cache_hit", form_id=form.id)
            return action_response(message="Form structure.", data=cached)

        serializer = ClinicalFormStructureSerializer(form)
        data = serializer.data
        try:
            cache.set(cache_key, data, ttl=3600)
            logger.info("clinical_form_structure_cache_set", form_id=form.id)
        except Exception as exc:
            logger.warning(
                "clinical_form_structure_cache_write_failed",
                form_id=form.id,
                error=str(exc),
            )
        return action_response(message="Form structure.", data=data)


# ---------------------------------------------------------------------------
# ClinicalFormSection
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List form sections",
        description="List sections for forms in the current tenant.",
        tags=["Clinical Form Sections"],
        responses={200: ClinicalFormSectionWriteSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve a form section",
        description="Retrieve a single form section.",
        tags=["Clinical Form Sections"],
        responses={200: ClinicalFormSectionWriteSerializer},
    ),
    create=extend_schema(
        summary="Create a form section",
        description="Add a section to a clinical form.",
        tags=["Clinical Form Sections"],
        responses={201: ClinicalFormSectionWriteSerializer},
    ),
    update=extend_schema(
        summary="Update a form section",
        description="Replace a form section.",
        tags=["Clinical Form Sections"],
        responses={200: ClinicalFormSectionWriteSerializer},
    ),
    partial_update=extend_schema(
        summary="Patch a form section",
        description="Partially update a form section.",
        tags=["Clinical Form Sections"],
        responses={200: ClinicalFormSectionWriteSerializer},
    ),
    destroy=extend_schema(
        summary="Delete a form section",
        description="Delete a form section.",
        tags=["Clinical Form Sections"],
        responses={204: None},
    ),
)
class ClinicalFormSectionViewSet(
    CachedFormStructureMixin,
    TenantViewSetMixin,
    viewsets.ModelViewSet,
):
    """CRUD for clinical form sections."""

    queryset = ClinicalFormSection.objects.all()
    serializer_class = ClinicalFormSectionWriteSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    # ?form=<id> resolves via FormSectionPlacement (the section model has no
    # direct FK to form) — see ClinicalFormSectionFilter for details.
    filterset_class = ClinicalFormSectionFilter

    def get_queryset(self):
        if not (check_permission(self.request, HMSPermissions.CLINICAL_VIEW) or check_permission(self.request, HMSPermissions.CLINICAL_CREATE) or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)):
            raise PermissionDenied("No permission to view form sections.")
        return super().get_queryset()

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create form sections.")
        serializer.save(created_by_user_id=self.request.user_id)
        for form_id in serializer.instance.form_placements.values_list("form_id", flat=True):
            self._bust_form_cache(form_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update form sections.")
        serializer.save()
        for form_id in serializer.instance.form_placements.values_list("form_id", flat=True):
            self._bust_form_cache(form_id)

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete form sections.")
        form_ids = list(instance.form_placements.values_list("form_id", flat=True))
        super().perform_destroy(instance)
        for form_id in form_ids:
            self._bust_form_cache(form_id)


# ---------------------------------------------------------------------------
# ClinicalFormField
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List form fields",
        description="List fields for sections in the current tenant.",
        tags=["Clinical Form Fields"],
        responses={200: ClinicalFormFieldSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve a form field",
        description="Retrieve a single form field.",
        tags=["Clinical Form Fields"],
        responses={200: ClinicalFormFieldSerializer},
    ),
    create=extend_schema(
        summary="Create a form field",
        description="Add a field to a form section.",
        tags=["Clinical Form Fields"],
        responses={201: ClinicalFormFieldSerializer},
    ),
    update=extend_schema(
        summary="Update a form field",
        description="Replace a form field.",
        tags=["Clinical Form Fields"],
        responses={200: ClinicalFormFieldSerializer},
    ),
    partial_update=extend_schema(
        summary="Patch a form field",
        description="Partially update a form field.",
        tags=["Clinical Form Fields"],
        responses={200: ClinicalFormFieldSerializer},
    ),
    destroy=extend_schema(
        summary="Delete a form field",
        description="Delete a form field.",
        tags=["Clinical Form Fields"],
        responses={204: None},
    ),
)
class ClinicalFormFieldViewSet(
    CachedFormStructureMixin,
    TenantViewSetMixin,
    viewsets.ModelViewSet,
):
    """CRUD for clinical form fields."""

    queryset = ClinicalFormField.objects.select_related("section", "picklist")
    serializer_class = ClinicalFormFieldSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["section"]

    def get_queryset(self):
        if not (check_permission(self.request, HMSPermissions.CLINICAL_VIEW) or check_permission(self.request, HMSPermissions.CLINICAL_CREATE) or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)):
            raise PermissionDenied("No permission to view form fields.")
        return super().get_queryset()

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create form fields.")
        serializer.save(created_by_user_id=self.request.user_id)
        for form_id in serializer.instance.section.form_placements.values_list("form_id", flat=True):
            self._bust_form_cache(form_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update form fields.")
        serializer.save()
        for form_id in serializer.instance.section.form_placements.values_list("form_id", flat=True):
            self._bust_form_cache(form_id)

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete form fields.")
        form_ids = list(instance.section.form_placements.values_list("form_id", flat=True))
        super().perform_destroy(instance)
        for form_id in form_ids:
            self._bust_form_cache(form_id)


# ---------------------------------------------------------------------------
# ClinicalPicklist
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List picklists",
        description="List reusable picklists for the current tenant.",
        tags=["Clinical Picklists"],
        responses={200: ClinicalPicklistSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve a picklist",
        description="Retrieve a picklist including its items.",
        tags=["Clinical Picklists"],
        responses={200: ClinicalPicklistSerializer},
    ),
    create=extend_schema(
        summary="Create a picklist",
        description="Create a new reusable picklist.",
        tags=["Clinical Picklists"],
        responses={201: ClinicalPicklistSerializer},
    ),
    update=extend_schema(
        summary="Update a picklist",
        description="Replace a picklist.",
        tags=["Clinical Picklists"],
        responses={200: ClinicalPicklistSerializer},
    ),
    partial_update=extend_schema(
        summary="Patch a picklist",
        description="Partially update a picklist.",
        tags=["Clinical Picklists"],
        responses={200: ClinicalPicklistSerializer},
    ),
    destroy=extend_schema(
        summary="Delete a picklist",
        description="Delete a picklist. System picklists are protected.",
        tags=["Clinical Picklists"],
        responses={204: None},
    ),
)
class ClinicalPicklistViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for reusable picklists."""

    queryset = ClinicalPicklist.objects.prefetch_related("items")
    serializer_class = ClinicalPicklistSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination

    def get_queryset(self):
        if not (check_permission(self.request, HMSPermissions.CLINICAL_VIEW) or check_permission(self.request, HMSPermissions.CLINICAL_CREATE) or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)):
            raise PermissionDenied("No permission to view picklists.")
        queryset = super().get_queryset()
        code = self.request.query_params.get("code")
        if code:
            queryset = queryset.filter(code=code)
        return queryset

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create picklists.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update picklists.")
        if serializer.instance.is_system:
            raise PermissionDenied("System picklists cannot be modified.")
        serializer.save()

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete picklists.")
        if instance.is_system:
            raise PermissionDenied("System picklists cannot be deleted.")
        super().perform_destroy(instance)

    @extend_schema(
        summary="List picklist items",
        description="Return the items belonging to this picklist.",
        tags=["Clinical Picklists"],
        responses={200: ClinicalPicklistItemSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="items")
    def items(self, request, pk=None):
        """
        Nested read of picklist items.
        Fetches the picklist by pk regardless of tenant (system picklists may
        have a different tenant_id), then returns only the items that belong
        to this tenant OR items from system picklists.
        """
        try:
            picklist = ClinicalPicklist.objects.get(pk=pk)
        except ClinicalPicklist.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("Picklist not found.")

        # Allow access if this tenant owns the picklist OR it is a system picklist
        if not picklist.is_system and str(picklist.tenant_id) != str(request.tenant_id):
            from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
            raise DRFPermissionDenied("You do not have access to this picklist.")

        # Return tenant-specific items first; fall back to any active items for system lists
        items_qs = picklist.items.filter(is_active=True)
        if not picklist.is_system:
            items_qs = items_qs.filter(tenant_id=request.tenant_id)

        serializer = ClinicalPicklistItemSerializer(items_qs.order_by("display_order"), many=True)
        return action_response(message="Picklist items.", data=serializer.data)


# ---------------------------------------------------------------------------
# ClinicalPicklistItem
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List picklist items",
        description="List picklist items for the current tenant.",
        tags=["Clinical Picklist Items"],
        responses={200: ClinicalPicklistItemSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve a picklist item",
        description="Retrieve a single picklist item.",
        tags=["Clinical Picklist Items"],
        responses={200: ClinicalPicklistItemSerializer},
    ),
    create=extend_schema(
        summary="Create a picklist item",
        description="Add an item to a picklist.",
        tags=["Clinical Picklist Items"],
        responses={201: ClinicalPicklistItemSerializer},
    ),
    update=extend_schema(
        summary="Update a picklist item",
        description="Replace a picklist item.",
        tags=["Clinical Picklist Items"],
        responses={200: ClinicalPicklistItemSerializer},
    ),
    partial_update=extend_schema(
        summary="Patch a picklist item",
        description="Partially update a picklist item.",
        tags=["Clinical Picklist Items"],
        responses={200: ClinicalPicklistItemSerializer},
    ),
    destroy=extend_schema(
        summary="Delete a picklist item",
        description="Delete a picklist item.",
        tags=["Clinical Picklist Items"],
        responses={204: None},
    ),
)
class ClinicalPicklistItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for picklist items."""

    queryset = ClinicalPicklistItem.objects.select_related("picklist")
    serializer_class = ClinicalPicklistItemSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_class = ClinicalPicklistItemFilter

    def get_queryset(self):
        if not (check_permission(self.request, HMSPermissions.CLINICAL_VIEW) or check_permission(self.request, HMSPermissions.CLINICAL_CREATE) or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)):
            raise PermissionDenied("No permission to view picklist items.")
        return super().get_queryset()

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create picklist items.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update picklist items.")
        serializer.save()

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete picklist items.")
        super().perform_destroy(instance)


class FormSectionPlacementViewSet(CachedFormStructureMixin, TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for form-section placements."""

    queryset = FormSectionPlacement.objects.select_related("form", "section")
    serializer_class = FormSectionPlacementSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["form", "section"]

    def get_queryset(self):
        if not (check_permission(self.request, HMSPermissions.CLINICAL_VIEW) or check_permission(self.request, HMSPermissions.CLINICAL_CREATE) or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)):
            raise PermissionDenied("No permission to view form placements.")
        return super().get_queryset()

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create form placements.")
        serializer.save(created_by_user_id=self.request.user_id)
        self._bust_form_cache(serializer.instance.form_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update form placements.")
        old_form_id = serializer.instance.form_id
        serializer.save()
        self._bust_form_cache(old_form_id)
        self._bust_form_cache(serializer.instance.form_id)

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete form placements.")
        form_id = instance.form_id
        super().perform_destroy(instance)
        self._bust_form_cache(form_id)


class ClinicalFormGroupViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for clinical form groups."""

    queryset = ClinicalFormGroup.objects.prefetch_related("items__form")
    serializer_class = ClinicalFormGroupSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["group_type", "entity_type", "parent"]

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create form groups.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update form groups.")
        serializer.save()


class ClinicalFormGroupItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for clinical form group items."""

    queryset = ClinicalFormGroupItem.objects.select_related("group", "form")
    serializer_class = ClinicalFormGroupItemSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["group", "form"]

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create form group items.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update form group items.")
        serializer.save()


class ClinicalPicklistGroupViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for clinical picklist groups."""

    queryset = ClinicalPicklistGroup.objects.prefetch_related("memberships__picklist")
    serializer_class = ClinicalPicklistGroupSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create picklist groups.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update picklist groups.")
        serializer.save()


class ClinicalPicklistGroupMembershipViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for picklist group memberships."""

    queryset = ClinicalPicklistGroupMembership.objects.select_related("group", "picklist")
    serializer_class = ClinicalPicklistGroupMembershipSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["group", "picklist"]

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create picklist group memberships.")
        serializer.save(created_by_user_id=self.request.user_id)


class ClinicalDocumentTemplateViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for document templates."""

    queryset = ClinicalDocumentTemplate.objects.all()
    serializer_class = ClinicalDocumentTemplateSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["doc_type", "bucket", "is_system"]

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create document templates.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update document templates.")
        serializer.save()


class ClinicalDocumentInstanceViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for generated/printed document instances."""

    queryset = ClinicalDocumentInstance.objects.select_related("template")
    serializer_class = ClinicalDocumentInstanceSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["template", "encounter_type", "encounter_id", "status"]

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create document instances.")
        serializer.save(created_by_user_id=self.request.user_id)


class ClinicalPrintTemplateViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for print templates."""

    queryset = ClinicalPrintTemplate.objects.all()
    serializer_class = ClinicalPrintTemplateSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["target_type", "target_code", "layout", "language"]

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create print templates.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update print templates.")
        serializer.save()


class MrdChecklistLineViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for MRD checklist line configuration."""

    queryset = MrdChecklistLine.objects.all()
    serializer_class = MrdChecklistLineSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["bucket", "source_type", "source_code"]

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create MRD checklist lines.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update MRD checklist lines.")
        serializer.save()


# ---------------------------------------------------------------------------
# ClinicalRecord
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List clinical records",
        description="List clinical records for the current tenant. Patients see only their own records.",
        tags=["Clinical Records"],
        responses={200: ClinicalRecordListSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve a clinical record",
        description="Retrieve a record with its field values.",
        tags=["Clinical Records"],
        responses={200: ClinicalRecordDetailSerializer},
    ),
    create=extend_schema(
        summary="Create a clinical record",
        description="Create a clinical record for an encounter.",
        tags=["Clinical Records"],
        responses={201: ClinicalRecordDetailSerializer},
    ),
    update=extend_schema(
        summary="Update a clinical record",
        description="Update encounter linkage or active flag. Use bulk_upsert_values to change field data.",
        tags=["Clinical Records"],
        responses={200: ClinicalRecordDetailSerializer},
    ),
    partial_update=extend_schema(
        summary="Patch a clinical record",
        description="Partially update a clinical record.",
        tags=["Clinical Records"],
        responses={200: ClinicalRecordDetailSerializer},
    ),
    destroy=extend_schema(
        summary="Delete a clinical record",
        description="Delete a clinical record.",
        tags=["Clinical Records"],
        responses={204: None},
    ),
)
class ClinicalRecordViewSet(
    PatientAccessMixin,
    TenantViewSetMixin,
    viewsets.ModelViewSet,
):
    """CRUD and workflow actions for clinical record instances."""

    queryset = ClinicalRecord.objects.select_related("form").prefetch_related(
        "field_values__field"
    )
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_class = ClinicalRecordFilter
    search_fields = ["encounter_type", "form__code", "form__name"]
    ordering_fields = ["created_at", "updated_at", "status"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action in ["list"]:
            return ClinicalRecordListSerializer
        if self.action in ["update", "partial_update"]:
            return ClinicalRecordWriteSerializer
        return ClinicalRecordDetailSerializer

    def get_queryset(self):
        if not (check_permission(self.request, HMSPermissions.CLINICAL_VIEW) or check_permission(self.request, HMSPermissions.CLINICAL_CREATE) or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)):
            raise PermissionDenied("No permission to view clinical records.")
        return super().get_queryset()

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create clinical records.")
        form = serializer.validated_data.get("form")
        # The structure serializer can contain UUID/datetime objects (e.g. from
        # nested .values() lookups). ClinicalRecord.structure_snapshot is a plain
        # JSONField, so round-trip through DjangoJSONEncoder to make it JSON-safe.
        structure_snapshot = None
        if form:
            raw_snapshot = ClinicalFormStructureSerializer(form, context={"request": self.request}).data
            structure_snapshot = json.loads(json.dumps(raw_snapshot, cls=DjangoJSONEncoder))

        # Repeatable forms (e.g. round notes, monitoring charts) may have many
        # records per encounter. Assign the next 1-based occurrence_index on the
        # server so "Create Next Round" is race-safe and clients need not send it.
        repeatable = bool((form.config or {}).get("repeatable")) if form else False
        occurrence_index = 1
        if repeatable:
            last = (
                ClinicalRecord.objects.filter(
                    tenant_id=self.request.tenant_id,
                    form=form,
                    encounter_type=serializer.validated_data.get("encounter_type"),
                    encounter_id=serializer.validated_data.get("encounter_id"),
                )
                .order_by("-occurrence_index")
                .values_list("occurrence_index", flat=True)
                .first()
            )
            occurrence_index = (last or 0) + 1

        record = serializer.save(
            created_by_user_id=self.request.user_id,
            form_version=form.version if form else 1,
            structure_snapshot=structure_snapshot,
            occurrence_index=occurrence_index,
        )

        # Seed any field bound to the occurrence index (e.g. round_number) so the
        # round number shows immediately without a manual edit. Sections are
        # reusable and attached to forms via FormSectionPlacement, so resolve the
        # form's sections through its placements.
        if form is not None:
            section_ids = list(
                FormSectionPlacement.objects.filter(form=form, is_active=True).values_list("section_id", flat=True)
            )
            if section_ids:
                for field in ClinicalFormField.objects.filter(section_id__in=section_ids, is_active=True):
                    if (field.config or {}).get("bind") == "occurrence_index":
                        ClinicalFieldValue.objects.update_or_create(
                            tenant_id=record.tenant_id,
                            record=record,
                            field=field,
                            defaults={
                                "value_number": occurrence_index,
                                "created_by_user_id": self.request.user_id,
                            },
                        )

        _audit(
            tenant_id=record.tenant_id,
            record_id=record.id,
            action=ClinicalRecordAuditLog.Action.CREATED,
            user_id=self.request.user_id,
            metadata={"form_id": record.form_id, "encounter_type": record.encounter_type, "encounter_id": record.encounter_id, "occurrence_index": occurrence_index},
        )

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update clinical records.")
        if serializer.instance.is_locked:
            raise PermissionDenied("Record is locked and cannot be modified.")
        record = serializer.save()
        _audit(
            tenant_id=record.tenant_id,
            record_id=record.id,
            action=ClinicalRecordAuditLog.Action.UPDATED,
            user_id=self.request.user_id,
            metadata={"form_id": record.form_id, "version": record.version},
        )

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete clinical records.")
        if instance.is_locked:
            raise PermissionDenied("Record is locked and cannot be deleted.")
        super().perform_destroy(instance)

    @extend_schema(
        summary="Lock a clinical record",
        description="Lock the record so further edits are blocked.",
        tags=["Clinical Records"],
        responses={200: ClinicalRecordDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="lock")
    def lock(self, request, pk=None):
        """Lock the record."""
        if not check_permission(request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to lock records.")
        record = self.get_object()
        if record.is_locked:
            return error_response(
                code=error_codes.RECORD_ALREADY_LOCKED,
                message="Record is already locked.",
                status=status.HTTP_409_CONFLICT,
            )
        record.is_locked = True
        record.locked_by_user_id = request.user_id
        record.locked_at = timezone.now()
        record.status = ClinicalRecord.Status.LOCKED
        record.save(update_fields=["is_locked", "locked_by_user_id", "locked_at", "status", "updated_at"])
        _audit(
            tenant_id=record.tenant_id,
            record_id=record.id,
            action=ClinicalRecordAuditLog.Action.LOCKED,
            user_id=request.user_id,
            metadata={"form_id": record.form_id},
        )
        return action_response(
            message="Record locked.",
            data=ClinicalRecordDetailSerializer(record, context={"request": request}).data,
        )

    @extend_schema(
        summary="Unlock a clinical record",
        description="Unlock the record for further editing.",
        tags=["Clinical Records"],
        responses={200: ClinicalRecordDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="unlock")
    def unlock(self, request, pk=None):
        """Unlock the record."""
        if not check_permission(request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to unlock records.")
        record = self.get_object()
        if not record.is_locked:
            return error_response(
                code=error_codes.VALIDATION_ERROR,
                message="Record is not locked.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        record.is_locked = False
        record.locked_by_user_id = None
        record.locked_at = None
        record.status = ClinicalRecord.Status.IN_PROGRESS
        record.save(update_fields=["is_locked", "locked_by_user_id", "locked_at", "status", "updated_at"])
        _audit(
            tenant_id=record.tenant_id,
            record_id=record.id,
            action=ClinicalRecordAuditLog.Action.UNLOCKED,
            user_id=request.user_id,
            metadata={"form_id": record.form_id},
        )
        return action_response(
            message="Record unlocked.",
            data=ClinicalRecordDetailSerializer(record, context={"request": request}).data,
        )

    @extend_schema(
        summary="Complete a clinical record",
        description="Transition a record to completed status. Record must not be locked.",
        tags=["Clinical Records"],
        responses={200: ClinicalRecordDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """Transition record to completed."""
        if not check_permission(request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to complete records.")
        record = self.get_object()
        if record.is_locked:
            return error_response(
                code=error_codes.RECORD_LOCKED,
                message="Record is locked; unlock before completing.",
                status=status.HTTP_409_CONFLICT,
            )
        record.status = ClinicalRecord.Status.COMPLETED
        record.save(update_fields=["status", "updated_at"])
        _audit(
            tenant_id=record.tenant_id,
            record_id=record.id,
            action=ClinicalRecordAuditLog.Action.UPDATED,
            user_id=request.user_id,
            metadata={"form_id": record.form_id, "status_transition": "completed"},
        )
        return action_response(
            message="Record marked as completed.",
            data=ClinicalRecordDetailSerializer(record, context={"request": request}).data,
        )

    @extend_schema(
        summary="Bulk upsert field values",
        description="Idempotently upsert field values for this record. Values are coerced to typed columns.",
        tags=["Clinical Records"],
        request=FieldValueBulkUpsertSerializer,
        responses={200: ClinicalFieldValueSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="bulk-upsert-values")
    def bulk_upsert_values(self, request, pk=None):
        """Bulk upsert field values with typed coercion."""
        if not check_permission(request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to edit clinical records.")

        record = self.get_object()
        if record.is_locked:
            return error_response(
                code=error_codes.RECORD_LOCKED,
                message="Record is locked; unlock before editing values.",
                status=status.HTTP_409_CONFLICT,
            )

        payload = FieldValueBulkUpsertSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        tenant_id = request.tenant_id
        user_id = request.user_id
        field_ids = {item["field_id"] for item in payload.validated_data["values"]}

        # System forms have tenant_id = 00000000-…-0000 (seeded, not owned by any hospital).
        # We must accept those fields as well as tenant-owned fields.
        _SYSTEM_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000000")

        # Ensure all fields belong to a section placed on the record's form.
        # Accept both tenant-owned fields and system-seeded fields.
        fields = {
            field.id: field
            for field in ClinicalFormField.objects.filter(
                Q(tenant_id=tenant_id) | Q(tenant_id=_SYSTEM_TENANT),
                id__in=field_ids,
                section__form_placements__form=record.form,
                section__form_placements__is_active=True,
                is_active=True,
            ).distinct()
        }
        missing = field_ids - set(fields.keys())
        if missing:
            return error_response(
                code=error_codes.FIELD_NOT_FOUND,
                message=f"Fields not found or not part of this form: {sorted(missing)}.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        upserted = []
        with transaction.atomic():
            for item in payload.validated_data["values"]:
                field_id = item["field_id"]
                field = fields[field_id]
                explicit_values = {
                    key: item.get(key)
                    for key in [
                        "value_text",
                        "value_number",
                        "value_boolean",
                        "value_date",
                        "value_datetime",
                        "value_time",
                        "value_json",
                        "picklist_item_id",
                    ]
                    if item.get(key) is not None
                }
                coerced = coerce_field_value(field, item.get("value_text")) if item.get("value_text") is not None else {}
                coerced.update(explicit_values)
                value_obj, created = ClinicalFieldValue.objects.update_or_create(
                    tenant_id=tenant_id,
                    record=record,
                    field=field,
                    defaults={
                        "created_by_user_id": user_id,
                        **coerced,
                    },
                )
                _sync_prescription_grid_to_pharmacy(
                    record=record,
                    field=field,
                    rows=value_obj.value_json,
                    user_id=user_id,
                )
                _sync_investigation_grid_to_diagnostics(
                    record=record,
                    field=field,
                    rows=value_obj.value_json,
                    user_id=user_id,
                )
                upserted.append(value_obj)

        _audit(
            tenant_id=record.tenant_id,
            record_id=record.id,
            action=ClinicalRecordAuditLog.Action.FIELD_VALUES_UPSERTED,
            user_id=user_id,
            metadata={"field_ids": sorted(field_ids)},
        )

        return action_response(
            message=f"{len(upserted)} field value(s) upserted.",
            data=ClinicalFieldValueSerializer(upserted, many=True).data,
        )

    @extend_schema(
        summary="Create diagnostic orders from advised investigations",
        description=(
            "Idempotently creates one investigation Requisition for this clinical record's "
            "encounter and DiagnosticOrder rows for the supplied investigation_ids."
        ),
        tags=["Clinical Records"],
    )
    @action(detail=True, methods=["post"], url_path="order-investigations")
    def order_investigations(self, request, pk=None):
        """Convert selected investigation IDs into actionable lab orders."""
        if not check_permission(request, "hms.diagnostics.order"):
            raise PermissionDenied("No permission to order diagnostics.")

        record = self.get_object()
        result = _order_investigations_for_record(
            record=record,
            investigation_ids=request.data.get("investigation_ids", []),
            tenant_id=request.tenant_id,
            user_id=request.user_id,
        )
        if "error" in result:
            return error_response(
                code=result["error"],
                message=result["message"],
                status=result["status"],
            )

        return action_response(
            message=f"{len(result['created_order_ids'])} investigation order(s) created.",
            data={
                "requisition": result["requisition_data"],
                "created_order_ids": result["created_order_ids"],
                "existing_investigation_ids": result["existing_investigation_ids"],
            },
        )

    # Picklist codes shared between OPD and IPD forms for cross-encounter
    # import. Chief Complaints, Past History, Diagnosis and Investigations
    # all use the SAME ClinicalPicklist (config.picklist_code) on both sides
    # even though the underlying field_key differs (e.g. OPD's "diagnosis"
    # vs IPD's "provisional_diagnosis") — matching by picklist_code is the
    # only stable link between the two forms' otherwise independently
    # authored sections (see apps/clinical/seeds/forms_opd.py + forms_ipd.py).
    IMPORTABLE_PICKLIST_CODES = ("chief_complaints", "past_history", "diagnosis", "investigations")

    @extend_schema(
        summary="Import Chief Complaints / Diagnosis / Investigations from OPD",
        description=(
            "Copies field values for the shared Chief Complaints, Past History, "
            "Diagnosis and Investigations fields from the patient's most recent "
            "OPD clinical record into this (IPD) record, matched by "
            "config.picklist_code. By default, only fields that are still empty "
            "on this record are filled in; pass {\"overwrite\": true} to replace "
            "existing values too."
        ),
        tags=["Clinical Records"],
        responses={200: ClinicalFieldValueSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="import-from-opd")
    def import_from_opd(self, request, pk=None):
        """Copy Chief Complaints/Diagnosis/Investigations values from the patient's latest OPD record."""
        if not check_permission(request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to edit clinical records.")

        record = self.get_object()
        if record.is_locked:
            return error_response(
                code=error_codes.RECORD_LOCKED,
                message="Record is locked; unlock before editing values.",
                status=status.HTTP_409_CONFLICT,
            )
        if not record.patient_user_id:
            return error_response(
                code=error_codes.VALIDATION_ERROR,
                message="This record has no linked patient, so OPD history cannot be looked up.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant_id = request.tenant_id
        user_id = request.user_id
        overwrite = bool(request.data.get("overwrite"))

        # Target fields: fields on THIS record's form whose picklist_code is
        # one of the shared codes above.
        target_fields = list(
            ClinicalFormField.objects.filter(
                Q(tenant_id=tenant_id) | Q(tenant_id=_SYSTEM_TENANT_ID),
                section__form_placements__form=record.form,
                section__form_placements__is_active=True,
                is_active=True,
            ).distinct()
        )
        target_by_picklist_code = {}
        for f in target_fields:
            code = (f.config or {}).get("picklist_code")
            if code in self.IMPORTABLE_PICKLIST_CODES:
                target_by_picklist_code[code] = f

        if not target_by_picklist_code:
            return error_response(
                code=error_codes.FIELD_NOT_FOUND,
                message="This form has no Chief Complaints, Diagnosis, or Investigations fields to import into.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Source: the patient's most recent active OPD record (any form), so
        # this works regardless of which specific OPD form was filled.
        source_record = (
            ClinicalRecord.objects.filter(
                tenant_id=tenant_id,
                encounter_type="opd_visit",
                patient_user_id=record.patient_user_id,
                is_active=True,
            )
            .order_by("-created_at")
            .first()
        )
        if not source_record:
            return error_response(
                code=error_codes.NO_SOURCE_RECORD_FOUND,
                message="No OPD clinical record was found for this patient yet.",
                status=status.HTTP_404_NOT_FOUND,
            )

        source_values = ClinicalFieldValue.objects.filter(
            tenant_id=tenant_id,
            record=source_record,
            is_active=True,
            field__config__picklist_code__in=list(target_by_picklist_code.keys()),
        ).select_related("field")

        existing_target_values = {
            fv.field_id: fv
            for fv in ClinicalFieldValue.objects.filter(
                tenant_id=tenant_id, record=record, field__in=target_by_picklist_code.values()
            )
        }

        value_columns = [
            "value_text", "value_number", "value_boolean",
            "value_date", "value_datetime", "value_time", "value_json",
        ]

        upserted = []
        imported_field_ids = []
        with transaction.atomic():
            for source_fv in source_values:
                code = (source_fv.field.config or {}).get("picklist_code")
                target_field = target_by_picklist_code.get(code)
                if not target_field:
                    continue
                existing = existing_target_values.get(target_field.id)
                if existing and not overwrite:
                    has_value = existing.picklist_item_id or any(
                        getattr(existing, col) not in (None, "") for col in value_columns
                    )
                    if has_value:
                        continue  # don't clobber values the user already entered
                defaults = {col: getattr(source_fv, col) for col in value_columns}
                defaults["picklist_item_id"] = source_fv.picklist_item_id
                defaults["created_by_user_id"] = user_id
                value_obj, _created = ClinicalFieldValue.objects.update_or_create(
                    tenant_id=tenant_id,
                    record=record,
                    field=target_field,
                    defaults=defaults,
                )
                upserted.append(value_obj)
                imported_field_ids.append(target_field.id)

        if not upserted:
            return action_response(
                message="No new values to import — the OPD record has no matching data, or this record is already filled.",
                data=[],
            )

        _audit(
            tenant_id=record.tenant_id,
            record_id=record.id,
            action=ClinicalRecordAuditLog.Action.FIELD_VALUES_UPSERTED,
            user_id=user_id,
            metadata={
                "field_ids": sorted(imported_field_ids),
                "source": "import_from_opd",
                "source_record_id": source_record.id,
            },
        )

        return action_response(
            message=f"Imported {len(upserted)} field value(s) from OPD.",
            data=ClinicalFieldValueSerializer(upserted, many=True).data,
        )

    @extend_schema(
        summary="Create a snapshot",
        description="Save a point-in-time snapshot of the record and its field values.",
        tags=["Clinical Records"],
        responses={201: SavedFormSnapshotSerializer},
    )
    @action(detail=True, methods=["post"], url_path="snapshot")
    def snapshot(self, request, pk=None):
        """Create a saved snapshot for this record."""
        if not check_permission(request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create snapshots.")
        record = self.get_object()
        name = request.data.get("name") or f"Snapshot {timezone.now().isoformat()}"
        snapshot_data = {
            "record_id": record.id,
            "form_id": record.form_id,
            "form_code": record.form.code,
            "version": record.version,
            "status": record.status,
            "field_values": ClinicalFieldValueSerializer(
                record.field_values.filter(is_active=True), many=True
            ).data,
        }
        snapshot = SavedFormSnapshot.objects.create(
            tenant_id=record.tenant_id,
            record=record,
            name=name,
            snapshot_data=snapshot_data,
            created_by_user_id=request.user_id,
        )
        _audit(
            tenant_id=record.tenant_id,
            record_id=record.id,
            action=ClinicalRecordAuditLog.Action.SNAPSHOT_CREATED,
            user_id=request.user_id,
            metadata={"snapshot_id": snapshot.id, "name": name},
        )
        return action_response(
            message="Snapshot created.",
            data=SavedFormSnapshotSerializer(snapshot).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# UserFormPreference
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        summary="List form preferences",
        description="List current user's form preferences.",
        tags=["Clinical Preferences"],
        responses={200: UserFormPreferenceSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Retrieve a form preference",
        description="Retrieve a form preference.",
        tags=["Clinical Preferences"],
        responses={200: UserFormPreferenceSerializer},
    ),
    create=extend_schema(
        summary="Create a form preference",
        description="Save display preferences for a form.",
        tags=["Clinical Preferences"],
        responses={201: UserFormPreferenceSerializer},
    ),
    update=extend_schema(
        summary="Update a form preference",
        description="Replace a form preference.",
        tags=["Clinical Preferences"],
        responses={200: UserFormPreferenceSerializer},
    ),
    partial_update=extend_schema(
        summary="Patch a form preference",
        description="Partially update a form preference.",
        tags=["Clinical Preferences"],
        responses={200: UserFormPreferenceSerializer},
    ),
    destroy=extend_schema(
        summary="Delete a form preference",
        description="Delete a form preference.",
        tags=["Clinical Preferences"],
        responses={204: None},
    ),
)
class UserFormPreferenceViewSet(PatientAccessMixin, TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for per-user form display preferences."""

    queryset = UserFormPreference.objects.select_related("form")
    serializer_class = UserFormPreferenceSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination

    def get_queryset(self):
        if not (check_permission(self.request, HMSPermissions.CLINICAL_VIEW) or check_permission(self.request, HMSPermissions.CLINICAL_CREATE) or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)):
            raise PermissionDenied("No permission to view form preferences.")
        qs = super().get_queryset()
        # Patients/staff should only see their own preferences.
        return qs.filter(user_id=self.request.user_id)

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create form preferences.")
        serializer.save(user_id=self.request.user_id, created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update form preferences.")
        serializer.save()

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete form preferences.")
        instance.delete()


# ---------------------------------------------------------------------------
# SavedFormSnapshot
# ---------------------------------------------------------------------------


class SavedFormSnapshotViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """CRUD for saved form snapshots."""

    queryset = SavedFormSnapshot.objects.select_related("record")
    serializer_class = SavedFormSnapshotSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create snapshots.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete snapshots.")
        instance.delete()


class ClinicalFormTemplateViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """Named, reusable field-value templates for a form (e.g. prescription templates).

    Filter by form with ``?form=<id>``. Create with ``{form, name, values}``.
    """

    queryset = ClinicalFormTemplate.objects.select_related("form").filter(is_active=True)
    serializer_class = ClinicalFormTemplateSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["form"]

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create templates.")
        serializer.save(created_by_user_id=self.request.user_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update templates.")
        serializer.save()

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete templates.")
        instance.delete()
