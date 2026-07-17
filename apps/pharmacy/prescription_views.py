"""Prescription ViewSet for clinical medicine prescriptions."""

from decimal import Decimal

import structlog
from django.contrib.contenttypes.models import ContentType
from django.db import transaction as db_transaction
from django.db.models import F, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.inventory.models import InventoryItem, StockTransaction
from apps.patients.models import PatientProfile
from common.drf_auth import HMSPermission
from common.mixins import TenantViewSetMixin
from common.responses import action_response, error_response

from .models import Prescription, PrescriptionItem
from .serializers import PrescriptionItemSerializer, PrescriptionSerializer

logger = structlog.get_logger(__name__)


def _apply_prescription_dispense(
    item: PrescriptionItem,
    quantity: Decimal,
    tenant_id,
    user_id,
) -> StockTransaction:
    """
    Atomically deduct inventory for an inventory-linked dispensed prescription item.
    Manual prescription rows with no inventory_item skip stock movement.
    """
    inventory_item = item.inventory_item
    if inventory_item is None:
        return None

    with db_transaction.atomic():
        inventory_item.refresh_from_db(fields=["current_stock"])
        qty_before = inventory_item.current_stock
        qty_after = qty_before - quantity

        InventoryItem.objects.filter(pk=inventory_item.pk).update(
            current_stock=F("current_stock") - quantity
        )

        encounter_type = (
            f"{item.prescription.content_type.app_label}_{item.prescription.content_type.model}"
            if item.prescription.content_type_id
            else "opd_visit"
        )
        transaction_type = "issue_ipd" if encounter_type == "ipd_admission" else "issue_opd"
        reference_id = item.prescription.object_id or item.prescription.visit_id

        txn = StockTransaction.objects.create(
            tenant_id=tenant_id,
            item=inventory_item,
            transaction_type=transaction_type,
            quantity=quantity,
            quantity_before=qty_before,
            quantity_after=qty_after,
            unit_cost=inventory_item.purchase_price,
            reference_type=encounter_type,
            reference_id=str(reference_id or ""),
            notes=f"Dispensed for prescription {item.prescription_id}, item {item.id}",
            performed_by_user_id=user_id,
        )

    logger.info(
        "prescription_item_dispensed",
        tenant_id=str(tenant_id),
        prescription_id=item.prescription_id,
        prescription_item_id=item.id,
        inventory_item_id=inventory_item.id,
        quantity=str(quantity),
        qty_before=str(qty_before),
        qty_after=str(qty_after),
    )
    return txn


class PrescriptionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Clinical prescription management.

    - List/retrieve filtered by visit (encounter)
    - Create/update prescription headers
    - Nested item CRUD via actions
    - Dispense action deducts inventory
    """

    queryset = Prescription.objects.prefetch_related("items__inventory_item").all()
    serializer_class = PrescriptionSerializer
    permission_classes = [HMSPermission]
    hms_module = "pharmacy"

    action_permission_map = {
        "list": "view",
        "retrieve": "view",
        "create": "create",
        "update": "edit",
        "partial_update": "edit",
        "destroy": "delete",
        "add_item": "create",
        "update_item": "edit",
        "remove_item": "delete",
        "dispense": "sell",
        "by_visit": "view",
        "by_encounter": "view",
        "dashboard": "view",
    }

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["visit", "status"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Tenant-scoped list with OPD/IPD encounter and dashboard filters."""
        queryset = super().get_queryset().select_related(
            "content_type",
            "visit__patient",
        ).prefetch_related("items__inventory_item")
        visit_id = self.request.query_params.get("visit")
        if visit_id:
            queryset = queryset.filter(visit_id=visit_id)
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        encounter_type = self.request.query_params.get("encounter_type")
        encounter_id = self.request.query_params.get("encounter_id")
        if encounter_type:
            content_type = PrescriptionSerializer.resolve_encounter_type(encounter_type)
            queryset = queryset.filter(content_type=content_type)
            if encounter_id:
                queryset = queryset.filter(object_id=encounter_id)

        patient_id = self.request.query_params.get("patient")
        search = self.request.query_params.get("search")
        if patient_id or search:
            patient_qs = PatientProfile.objects.filter(tenant_id=self.request.tenant_id)
            if patient_id:
                patient_qs = patient_qs.filter(id=patient_id)
            if search:
                patient_qs = patient_qs.filter(
                    Q(patient_id__icontains=search)
                    | Q(first_name__icontains=search)
                    | Q(middle_name__icontains=search)
                    | Q(last_name__icontains=search)
                    | Q(mobile_primary__icontains=search)
                )

            visit_ids = []
            admission_ids = []
            try:
                from apps.opd.models import Visit

                visit_ids = list(
                    Visit.objects.filter(
                        tenant_id=self.request.tenant_id,
                        patient_id__in=patient_qs.values("id"),
                    ).values_list("id", flat=True)
                )
            except Exception:
                visit_ids = []
            try:
                from apps.ipd.models import Admission

                admission_ids = list(
                    Admission.objects.filter(
                        tenant_id=self.request.tenant_id,
                        patient_id__in=patient_qs.values("id"),
                    ).values_list("id", flat=True)
                )
                admission_ct = ContentType.objects.get(app_label="ipd", model="admission")
            except Exception:
                admission_ids = []
                admission_ct = None

            patient_filter = Q(visit_id__in=visit_ids)
            if admission_ct and admission_ids:
                patient_filter |= Q(content_type=admission_ct, object_id__in=admission_ids)
            queryset = queryset.filter(patient_filter)
        return queryset

    def perform_create(self, serializer):
        prescription = serializer.save(
            tenant_id=self.request.tenant_id,
            created_by_user_id=self.request.user_id,
        )
        if prescription.visit_id and not prescription.content_type_id:
            prescription.content_type = PrescriptionSerializer.resolve_encounter_type("opd.visit")
            prescription.object_id = prescription.visit_id
            prescription.save(update_fields=["content_type", "object_id", "updated_at"])

    @action(detail=True, methods=["post"])
    def add_item(self, request, pk=None):
        """Add a medicine line item to the prescription."""
        prescription = self.get_object()

        if prescription.status == "cancelled":
            return error_response(
                "INVALID_PAYLOAD", "Cannot modify a cancelled prescription.", status=400
            )

        data = request.data.copy()
        data["prescription"] = prescription.id
        serializer = PrescriptionItemSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        inventory_item = serializer.validated_data.get("inventory_item")
        medicine_name = serializer.validated_data.get("medicine_name", "")
        if inventory_item is None and not medicine_name:
            return error_response(
                "INVALID_PAYLOAD",
                "Either inventory_item or drug_name is required.",
                status=400,
            )
        item = serializer.save(
            tenant_id=request.tenant_id,
            prescription=prescription,
            medicine_name=inventory_item.name if inventory_item else medicine_name,
        )

        prescription.recalculate_status()
        prescription.save(update_fields=["status", "updated_at"])

        return Response(
            {
                "success": True,
                "message": "Medicine added to prescription.",
                "data": PrescriptionItemSerializer(item).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def update_item(self, request, pk=None):
        """Update an existing prescription item."""
        prescription = self.get_object()

        if prescription.status == "cancelled":
            return error_response(
                "INVALID_PAYLOAD", "Cannot modify a cancelled prescription.", status=400
            )

        item_id = request.data.get("item_id")
        if not item_id:
            return error_response("INVALID_PAYLOAD", "item_id is required.", status=400)

        try:
            item = PrescriptionItem.objects.get(
                id=item_id, prescription=prescription, tenant_id=request.tenant_id
            )
        except PrescriptionItem.DoesNotExist:
            return error_response("RECORD_NOT_FOUND", "Prescription item not found.", status=404)

        if item.is_dispensed:
            return error_response(
                "RECORD_LOCKED",
                "Cannot update an already dispensed item.",
                status=400,
            )

        serializer = PrescriptionItemSerializer(
            item,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        if item.inventory_item_id and not request.data.get("drug_name"):
            item.medicine_name = item.inventory_item.name
            item.save(update_fields=["medicine_name", "updated_at"])
            serializer = PrescriptionItemSerializer(item, context={"request": request})

        prescription.recalculate_status()
        prescription.save(update_fields=["status", "updated_at"])

        return action_response("Prescription item updated.", data=serializer.data)

    @action(detail=True, methods=["post"])
    def remove_item(self, request, pk=None):
        """Remove a prescription item."""
        prescription = self.get_object()

        if prescription.status == "cancelled":
            return error_response(
                "INVALID_PAYLOAD", "Cannot modify a cancelled prescription.", status=400
            )

        item_id = request.data.get("item_id")
        if not item_id:
            return error_response("INVALID_PAYLOAD", "item_id is required.", status=400)

        try:
            item = PrescriptionItem.objects.get(
                id=item_id, prescription=prescription, tenant_id=request.tenant_id
            )
        except PrescriptionItem.DoesNotExist:
            return error_response("RECORD_NOT_FOUND", "Prescription item not found.", status=404)

        if item.is_dispensed:
            return error_response(
                "RECORD_LOCKED",
                "Cannot remove an already dispensed item.",
                status=400,
            )

        item.delete()
        prescription.recalculate_status()
        prescription.save(update_fields=["status", "updated_at"])

        return action_response("Prescription item removed.")

    @action(detail=True, methods=["post"])
    def dispense(self, request, pk=None):
        """
        Dispense one or all pending items on this prescription.

        Payload:
        - item_id (optional): dispense a single item; if omitted, dispenses all pending items.
        - quantity (optional): override quantity for single-item dispense; defaults to prescribed quantity.
        """
        prescription = self.get_object()

        if prescription.status == "cancelled":
            return error_response(
                "INVALID_PAYLOAD", "Cannot dispense a cancelled prescription.", status=400
            )

        item_id = request.data.get("item_id")
        items = prescription.items.filter(
            tenant_id=request.tenant_id, is_dispensed=False
        )
        if item_id:
            items = items.filter(id=item_id)

        if not items.exists():
            return error_response(
                "RECORD_NOT_FOUND", "No pending items to dispense.", status=404
            )

        dispensed = []
        errors = []

        for item in items.select_related("inventory_item"):
            inventory_item = item.inventory_item
            requested_qty = Decimal(str(request.data.get("quantity", item.quantity)))

            if requested_qty <= 0:
                errors.append(
                    {"item_id": item.id, "message": "Dispense quantity must be greater than 0."}
                )
                continue

            if requested_qty > item.quantity:
                errors.append(
                    {
                        "item_id": item.id,
                        "message": (
                            f"Dispense quantity ({requested_qty}) cannot exceed "
                            f"prescribed quantity ({item.quantity})."
                        ),
                    }
                )
                continue

            if inventory_item is not None:
                inventory_item.refresh_from_db(fields=["current_stock"])
                if inventory_item.current_stock < requested_qty:
                    errors.append(
                        {
                            "item_id": item.id,
                            "message": (
                                f"Insufficient stock for {inventory_item.name}. "
                                f"Available: {inventory_item.current_stock} {inventory_item.unit_of_measure}."
                            ),
                        }
                    )
                    continue

                _apply_prescription_dispense(
                    item,
                    requested_qty,
                    request.tenant_id,
                    request.user_id,
                )
            item.mark_dispensed(quantity=requested_qty, user_id=request.user_id)
            item.save(
                update_fields=[
                    "is_dispensed",
                    "dispensed_quantity",
                    "dispensed_at",
                    "dispensed_by_user_id",
                    "updated_at",
                ]
            )
            dispensed.append(PrescriptionItemSerializer(item).data)

        prescription.recalculate_status()
        prescription.save(update_fields=["status", "updated_at"])

        if errors and not dispensed:
            return error_response(
                "INSUFFICIENT_STOCK",
                "Could not dispense any items.",
                status=422,
                detail={"errors": errors},
            )

        response_data = {"dispensed": dispensed}
        if errors:
            response_data["errors"] = errors

        return action_response(
            f"Dispensed {len(dispensed)} item(s).",
            data=response_data,
        )

    @action(detail=False, methods=["get"])
    def by_visit(self, request):
        """Return the prescription (with items) for a given visit."""
        visit_id = request.query_params.get("visit")
        if not visit_id:
            return error_response("INVALID_PAYLOAD", "visit query parameter is required.", status=400)

        prescription = (
            Prescription.objects.filter(
                tenant_id=request.tenant_id, visit_id=visit_id
            )
            .prefetch_related("items__inventory_item")
            .order_by("-created_at")
            .first()
        )

        if not prescription:
            return Response(
                {"success": True, "data": None, "message": "No prescription found for this visit."}
            )

        return Response(
            {
                "success": True,
                "data": PrescriptionSerializer(prescription).data,
            }
        )

    @action(detail=False, methods=["get"], url_path="by-encounter")
    def by_encounter(self, request):
        """Return the latest prescription for any supported encounter."""
        encounter_type = request.query_params.get("encounter_type")
        encounter_id = request.query_params.get("encounter_id")
        if not encounter_type or not encounter_id:
            return error_response(
                "INVALID_PAYLOAD",
                "encounter_type and encounter_id query parameters are required.",
                status=400,
            )

        content_type = PrescriptionSerializer.resolve_encounter_type(encounter_type)
        prescription = (
            Prescription.objects.filter(
                tenant_id=request.tenant_id,
                content_type=content_type,
                object_id=encounter_id,
            )
            .select_related("content_type", "visit__patient")
            .prefetch_related("items__inventory_item")
            .order_by("-created_at")
            .first()
        )

        if not prescription:
            return Response(
                {"success": True, "data": None, "message": "No prescription found for this encounter."}
            )

        return Response({"success": True, "data": PrescriptionSerializer(prescription).data})

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        """Pharmacy dashboard list; mirrors list filters with eager-loaded patient and items."""
        page = self.paginate_queryset(self.get_queryset())
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({"success": True, "data": serializer.data})
