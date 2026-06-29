"""Prescription ViewSet for clinical medicine prescriptions."""

from decimal import Decimal

import structlog
from django.db import transaction as db_transaction
from django.db.models import F
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.inventory.models import InventoryItem, StockTransaction
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
    Atomically deduct inventory for a dispensed prescription item.
    Creates an issue_opd StockTransaction and updates InventoryItem.current_stock.
    """
    inventory_item = item.inventory_item
    with db_transaction.atomic():
        inventory_item.refresh_from_db(fields=["current_stock"])
        qty_before = inventory_item.current_stock
        qty_after = qty_before - quantity

        InventoryItem.objects.filter(pk=inventory_item.pk).update(
            current_stock=F("current_stock") - quantity
        )

        txn = StockTransaction.objects.create(
            tenant_id=tenant_id,
            item=inventory_item,
            transaction_type="issue_opd",
            quantity=quantity,
            quantity_before=qty_before,
            quantity_after=qty_after,
            unit_cost=inventory_item.purchase_price,
            reference_type="opd_visit",
            reference_id=str(item.prescription.visit_id),
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
    }

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["visit", "status"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filter by visit when provided via ?visit=."""
        queryset = super().get_queryset()
        visit_id = self.request.query_params.get("visit")
        if visit_id:
            queryset = queryset.filter(visit_id=visit_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(
            tenant_id=self.request.tenant_id,
            created_by_user_id=self.request.user_id,
        )

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

        inventory_item = serializer.validated_data["inventory_item"]
        item = serializer.save(
            tenant_id=request.tenant_id,
            prescription=prescription,
            medicine_name=inventory_item.name,
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
        serializer.save()

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
