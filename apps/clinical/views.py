"""API views for the clinical forms and records app."""

import hashlib
import structlog
import uuid
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from common import error_codes
from common.cache import CeliyoCache
from common.drf_auth import HMSPermission
from common.permissions import HMSPermissions, IsTenantAuthenticated, check_permission
from common.mixins import CachedFormStructureMixin, PatientAccessMixin, TenantViewSetMixin
from common.pagination import StandardPagination
from common.responses import action_response, error_response

from .filters import ClinicalFormFilter, ClinicalPicklistItemFilter, ClinicalRecordFilter
from .models import (
    ClinicalFieldValue,
    ClinicalForm,
    ClinicalFormField,
    ClinicalFormSection,
    ClinicalPicklist,
    ClinicalPicklistItem,
    ClinicalRecord,
    ClinicalRecordAuditLog,
    SavedFormSnapshot,
    UserFormPreference,
)
from .serializers import (
    ClinicalFieldValueSerializer,
    ClinicalFormFieldSerializer,
    ClinicalFormSerializer,
    ClinicalFormSectionWriteSerializer,
    ClinicalFormStructureSerializer,
    ClinicalPicklistItemSerializer,
    ClinicalPicklistSerializer,
    ClinicalRecordDetailSerializer,
    ClinicalRecordListSerializer,
    ClinicalRecordWriteSerializer,
    FieldValueBulkUpsertSerializer,
    SavedFormSnapshotSerializer,
    UserFormPreferenceSerializer,
    coerce_field_value,
)
from .tasks import create_clinical_audit_log_task

logger = structlog.get_logger(__name__)


def _audit(
    tenant_id,
    record_id,
    action,
    user_id,
    metadata=None,
):
    """Queue an async audit log entry."""
    create_clinical_audit_log_task.delay(
        tenant_id=str(tenant_id),
        record_id=record_id,
        action=action,
        user_id=str(user_id),
        metadata=metadata or {},
    )


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

        cached = cache.get(cache_key)
        if cached is not None:
            logger.info("clinical_form_structure_cache_hit", form_id=form.id)
            return action_response(message="Form structure.", data=cached)

        serializer = ClinicalFormStructureSerializer(form)
        data = serializer.data
        cache.set(cache_key, data, ttl=3600)
        logger.info("clinical_form_structure_cache_set", form_id=form.id)
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

    queryset = ClinicalFormSection.objects.select_related("form")
    serializer_class = ClinicalFormSectionWriteSerializer
    permission_classes = [IsTenantAuthenticated, HMSPermission]
    hms_module = "clinical"
    pagination_class = StandardPagination
    filterset_fields = ["form"]

    def get_queryset(self):
        if not (check_permission(self.request, HMSPermissions.CLINICAL_VIEW) or check_permission(self.request, HMSPermissions.CLINICAL_CREATE) or check_permission(self.request, HMSPermissions.CLINICAL_EDIT)):
            raise PermissionDenied("No permission to view form sections.")
        return super().get_queryset()

    def perform_create(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_CREATE):
            raise PermissionDenied("No permission to create form sections.")
        serializer.save(created_by_user_id=self.request.user_id)
        form_id = getattr(serializer.instance, "form_id", None)
        if form_id:
            self._bust_form_cache(form_id)

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update form sections.")
        serializer.save()
        form_id = getattr(serializer.instance, "form_id", None)
        if form_id:
            self._bust_form_cache(form_id)

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete form sections.")
        form_id = getattr(instance, "form_id", None)
        super().perform_destroy(instance)
        if form_id:
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

    queryset = ClinicalFormField.objects.select_related("section__form", "picklist")
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
        try:
            self._bust_form_cache(serializer.instance.section.form_id)
        except AttributeError:
            pass

    def perform_update(self, serializer):
        if not check_permission(self.request, HMSPermissions.CLINICAL_EDIT):
            raise PermissionDenied("No permission to update form fields.")
        serializer.save()
        try:
            self._bust_form_cache(serializer.instance.section.form_id)
        except AttributeError:
            pass

    def perform_destroy(self, instance):
        if not check_permission(self.request, HMSPermissions.CLINICAL_DELETE):
            raise PermissionDenied("No permission to delete form fields.")
        try:
            form_id = instance.section.form_id
        except AttributeError:
            form_id = None
        super().perform_destroy(instance)
        if form_id:
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
        return super().get_queryset()

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
        record = serializer.save(created_by_user_id=self.request.user_id)
        _audit(
            tenant_id=record.tenant_id,
            record_id=record.id,
            action=ClinicalRecordAuditLog.Action.CREATED,
            user_id=self.request.user_id,
            metadata={"form_id": record.form_id, "encounter_type": record.encounter_type, "encounter_id": record.encounter_id},
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

        # Ensure all fields belong to the record's form.
        # Accept both tenant-owned fields and system-seeded fields.
        fields = {
            field.id: field
            for field in ClinicalFormField.objects.filter(
                Q(tenant_id=tenant_id) | Q(tenant_id=_SYSTEM_TENANT),
                id__in=field_ids,
                section__form=record.form,
                is_active=True,
            )
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
                coerced = coerce_field_value(field, item["value_text"])
                value_obj, created = ClinicalFieldValue.objects.update_or_create(
                    tenant_id=tenant_id,
                    record=record,
                    field=field,
                    defaults={
                        "created_by_user_id": user_id,
                        **coerced,
                    },
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
