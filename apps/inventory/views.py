"""
Inventory Management Views
==========================

ViewSets:
  InventoryCategoryViewSet     GET/POST/PATCH/DELETE  /inventory/categories/
  InventorySupplierViewSet     GET/POST/PATCH/DELETE  /inventory/suppliers/
  InventoryItemViewSet         GET/POST/PATCH/DELETE  /inventory/items/
    + @action  low-stock       GET  /inventory/items/low-stock/
    + @action  expiring-soon   GET  /inventory/items/expiring-soon/
    + @action  stock-history   GET  /inventory/items/{id}/stock-history/
  InventoryBatchViewSet        GET/POST/PATCH/DELETE  /inventory/batches/
  StockTransactionViewSet      GET/POST               /inventory/stock-transactions/
    + @action  receive         POST /inventory/stock-transactions/receive/
    + @action  issue           POST /inventory/stock-transactions/issue/
    + @action  adjust          POST /inventory/stock-transactions/adjust/
  StockAlertViewSet            GET                    /inventory/alerts/
    + @action  acknowledge     POST /inventory/alerts/{id}/acknowledge/
    + @action  summary         GET  /inventory/alerts/summary/
  InventoryDashboardViewSet    GET  /inventory/dashboard/
"""

import datetime
from decimal import Decimal

import structlog
from django.db import transaction as db_transaction
from django.db.models import Count, F, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    OpenApiParameter, extend_schema, extend_schema_view,
)
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.drf_auth import HMSPermission
from common.mixins import TenantViewSetMixin
from common.cache import CeliyoCache
from common.responses import action_response, error_response

from .models import (
    InventoryBatch,
    InventoryCategory,
    InventoryItem,
    InventorySupplier,
    StockAlert,
    StockTransaction,
)
from .serializers import (
    AdjustStockSerializer,
    InventoryBatchSerializer,
    InventoryCategorySerializer,
    InventoryDashboardSerializer,
    InventoryItemListSerializer,
    InventoryItemSerializer,
    InventorySupplierSerializer,
    IssueStockSerializer,
    ReceiveStockSerializer,
    StockAlertSerializer,
    StockTransactionSerializer,
)

log = structlog.get_logger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────

EXPIRY_WARNING_DAYS = 90   # alert when batch expires within this many days


def _check_and_update_alerts(item: InventoryItem, tenant_id, batch: InventoryBatch = None):
    """
    Evaluate stock thresholds and expiry for *item* and create / resolve alerts.
    Called after every StockTransaction and every batch save.  Never raises —
    alert failure must never block a stock transaction.
    """
    try:
        _eval_stock_alerts(item, tenant_id)
        if batch:
            _eval_expiry_alert(item, batch, tenant_id)
        # Also re-evaluate ALL batches for this item (e.g. after purchase resolves a shortage)
        for b in item.batches.filter(is_active=True):
            _eval_expiry_alert(item, b, tenant_id)
    except Exception as exc:
        log.warning("alert_check_failed", item_id=item.id, error=str(exc))


def _eval_stock_alerts(item: InventoryItem, tenant_id):
    stock = item.current_stock

    for alert_type, condition, message_fn in [
        ("out_of_stock", stock <= 0,
         lambda: f"{item.name} is out of stock (current: {stock} {item.unit_of_measure})."),
        ("low_stock",    0 < stock <= item.reorder_level,
         lambda: f"{item.name} is below reorder level ({stock} / {item.reorder_level} {item.unit_of_measure})."),
        ("overstock",    item.max_stock_level > 0 and stock > item.max_stock_level,
         lambda: f"{item.name} exceeds max stock level ({stock} / {item.max_stock_level} {item.unit_of_measure})."),
    ]:
        if condition:
            StockAlert.objects.update_or_create(
                tenant_id=tenant_id, item=item, alert_type=alert_type, batch=None,
                defaults=dict(
                    message=message_fn(),
                    current_value=stock,
                    threshold=item.reorder_level if "stock" in alert_type else item.max_stock_level,
                    is_active=True,
                    is_acknowledged=False,
                ),
            )
        else:
            # Condition resolved → deactivate alert (don't delete — keep history)
            StockAlert.objects.filter(
                tenant_id=tenant_id, item=item, alert_type=alert_type,
                batch=None, is_active=True,
            ).update(is_active=False)


def _eval_expiry_alert(item: InventoryItem, batch: InventoryBatch, tenant_id):
    if not batch.expiry_date or batch.remaining_quantity <= 0:
        # Resolve any existing expiry alerts for this batch
        StockAlert.objects.filter(
            tenant_id=tenant_id, item=item, batch=batch, is_active=True,
        ).update(is_active=False)
        return

    today = timezone.now().date()
    days  = (batch.expiry_date - today).days

    if days < 0:
        alert_type = "expired"
        msg = (f"Batch {batch.batch_number} of {item.name} expired on "
               f"{batch.expiry_date} ({abs(days)} days ago). "
               f"Remaining: {batch.remaining_quantity} {item.unit_of_measure}.")
    elif days <= EXPIRY_WARNING_DAYS:
        alert_type = "expiry_approaching"
        msg = (f"Batch {batch.batch_number} of {item.name} expires on "
               f"{batch.expiry_date} ({days} days). "
               f"Remaining: {batch.remaining_quantity} {item.unit_of_measure}.")
    else:
        # Condition resolved
        StockAlert.objects.filter(
            tenant_id=tenant_id, item=item, batch=batch, is_active=True,
        ).update(is_active=False)
        return

    StockAlert.objects.update_or_create(
        tenant_id=tenant_id, item=item, batch=batch, alert_type=alert_type,
        defaults=dict(
            message=msg,
            current_value=Decimal(str(days)),
            threshold=Decimal(str(EXPIRY_WARNING_DAYS)),
            is_active=True,
            is_acknowledged=False,
        ),
    )
    # If we just created an 'expired' alert, resolve any 'expiry_approaching' alert
    if alert_type == "expired":
        StockAlert.objects.filter(
            tenant_id=tenant_id, item=item, batch=batch,
            alert_type="expiry_approaching", is_active=True,
        ).update(is_active=False)


def _apply_transaction(
    item: InventoryItem,
    quantity: Decimal,
    transaction_type: str,
    tenant_id,
    batch: InventoryBatch = None,
    unit_cost: Decimal = Decimal("0.00"),
    reference_type: str = "manual",
    reference_id: str = "",
    notes: str = "",
    performed_by_user_id=None,
) -> StockTransaction:
    """
    Atomically apply a stock transaction:
      1. Record before/after on the StockTransaction row.
      2. Update InventoryItem.current_stock via F().
      3. Update InventoryBatch.remaining_quantity via F() if batch given.
      4. Trigger alert evaluation.
    """
    is_addition = transaction_type in StockTransaction.ADDITION_TYPES
    delta       = quantity if is_addition else -quantity

    with db_transaction.atomic():
        # Snapshot before
        item.refresh_from_db(fields=["current_stock"])
        qty_before = item.current_stock

        # Update item stock atomically
        InventoryItem.objects.filter(pk=item.pk).update(
            current_stock=F("current_stock") + delta
        )

        # Update batch remaining
        if batch:
            if is_addition:
                InventoryBatch.objects.filter(pk=batch.pk).update(
                    remaining_quantity=F("remaining_quantity") + quantity
                )
            else:
                InventoryBatch.objects.filter(pk=batch.pk).update(
                    remaining_quantity=F("remaining_quantity") - quantity
                )
            batch.refresh_from_db(fields=["remaining_quantity"])

        qty_after = qty_before + delta

        txn = StockTransaction.objects.create(
            tenant_id=tenant_id,
            item=item,
            batch=batch,
            transaction_type=transaction_type,
            quantity=quantity,
            quantity_before=qty_before,
            quantity_after=qty_after,
            unit_cost=unit_cost,
            reference_type=reference_type,
            reference_id=reference_id or "",
            notes=notes or "",
            performed_by_user_id=performed_by_user_id,
        )

    # Refresh and evaluate alerts outside the atomic block so alert DB ops
    # don't risk rolling back the transaction on failure
    item.refresh_from_db(fields=["current_stock", "reorder_level", "max_stock_level"])
    _check_and_update_alerts(item, tenant_id, batch)

    log.info(
        "stock_transaction_applied",
        tenant_id=str(tenant_id),
        item_id=item.id,
        transaction_type=transaction_type,
        quantity=str(quantity),
        qty_before=str(qty_before),
        qty_after=str(qty_after),
    )
    return txn


# ─── 1. Category ViewSet ─────────────────────────────────────────────────────

@extend_schema_view(
    list=extend_schema(
        summary="List inventory categories",
        description="Returns all active categories for this tenant. Supports search and parent filtering.",
        parameters=[
            OpenApiParameter("search", str, description="Search by name or code"),
            OpenApiParameter("parent", int, description="Filter by parent category ID"),
            OpenApiParameter("is_active", bool, description="Filter by active status"),
        ],
        tags=["Inventory — Categories"],
    ),
    create=extend_schema(summary="Create category", tags=["Inventory — Categories"]),
    retrieve=extend_schema(summary="Get category", tags=["Inventory — Categories"]),
    partial_update=extend_schema(summary="Update category", tags=["Inventory — Categories"]),
    destroy=extend_schema(summary="Delete category", tags=["Inventory — Categories"]),
)
class InventoryCategoryViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = InventoryCategory.objects.all()
    serializer_class = InventoryCategorySerializer
    permission_classes = [HMSPermission]
    hms_module = "inventory"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    action_permission_map = {
        "list":           "view_inventory",
        "retrieve":       "view_inventory",
        "create":         "manage_inventory",
        "partial_update": "manage_inventory",
        "destroy":        "manage_inventory",
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["parent", "is_active"]
    search_fields    = ["name", "code"]
    ordering_fields  = ["name", "created_at"]
    ordering         = ["name"]


# ─── 2. Supplier ViewSet ─────────────────────────────────────────────────────

@extend_schema_view(
    list=extend_schema(
        summary="List suppliers",
        parameters=[
            OpenApiParameter("search", str, description="Search by name, code, contact, phone"),
            OpenApiParameter("is_active", bool),
        ],
        tags=["Inventory — Suppliers"],
    ),
    create=extend_schema(summary="Create supplier", tags=["Inventory — Suppliers"]),
    retrieve=extend_schema(summary="Get supplier", tags=["Inventory — Suppliers"]),
    partial_update=extend_schema(summary="Update supplier", tags=["Inventory — Suppliers"]),
    destroy=extend_schema(summary="Delete supplier", tags=["Inventory — Suppliers"]),
)
class InventorySupplierViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = InventorySupplier.objects.all()
    serializer_class = InventorySupplierSerializer
    permission_classes = [HMSPermission]
    hms_module = "inventory"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    action_permission_map = {
        "list":           "view_inventory",
        "retrieve":       "view_inventory",
        "create":         "manage_inventory",
        "partial_update": "manage_inventory",
        "destroy":        "manage_inventory",
    }

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields   = ["name", "code", "contact_name", "phone", "email"]
    ordering        = ["name"]


# ─── 3. Item ViewSet ─────────────────────────────────────────────────────────

@extend_schema_view(
    list=extend_schema(
        summary="List inventory items",
        parameters=[
            OpenApiParameter("search", str, description="Search by name, code, barcode"),
            OpenApiParameter("category", int, description="Filter by category ID"),
            OpenApiParameter("is_active", bool),
            OpenApiParameter("tags", str, description="Comma-separated tags: opd,ipd,general,pharmacy,surgical,lab,other"),
        ],
        tags=["Inventory — Items"],
    ),
    create=extend_schema(summary="Create item", tags=["Inventory — Items"]),
    retrieve=extend_schema(summary="Get item detail", tags=["Inventory — Items"]),
    partial_update=extend_schema(summary="Update item", tags=["Inventory — Items"]),
    destroy=extend_schema(summary="Deactivate item", tags=["Inventory — Items"]),
)
class InventoryItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = InventoryItem.objects.select_related("category").all()
    serializer_class = InventoryItemSerializer
    permission_classes = [HMSPermission]
    hms_module = "inventory"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    action_permission_map = {
        "list":           "view_inventory",
        "retrieve":       "view_inventory",
        "create":         "manage_inventory",
        "partial_update": "manage_inventory",
        "destroy":        "manage_inventory",
        "low_stock":      "view_inventory",
        "expiring_soon":  "view_inventory",
        "stock_history":  "view_inventory",
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "is_active"]
    search_fields    = ["name", "code", "barcode"]
    ordering_fields  = ["name", "current_stock", "created_at"]
    ordering         = ["name"]

    def get_serializer_class(self):
        if self.action == "list":
            return InventoryItemListSerializer
        return InventoryItemSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tags_param = self.request.query_params.get("tags")
        if tags_param:
            tags = [t.strip() for t in tags_param.split(",") if t.strip()]
            for tag in tags:
                qs = qs.filter(tags__contains=tag)
        return qs

    def perform_create(self, serializer):
        serializer.save(
            tenant_id=self.request.tenant_id,
            created_by_user_id=self.request.user_id,
        )
        cache = CeliyoCache()
        cache.delete_pattern(f"inventory:dashboard:{self.request.tenant_id}")
        cache.delete_pattern(f"inventory:alerts:{self.request.tenant_id}")

    def perform_update(self, serializer):
        super().perform_update(serializer)
        cache = CeliyoCache()
        cache.delete_pattern(f"inventory:dashboard:{self.request.tenant_id}")
        cache.delete_pattern(f"inventory:alerts:{self.request.tenant_id}")

    def perform_destroy(self, instance):
        tenant_id = self.request.tenant_id
        super().perform_destroy(instance)
        cache = CeliyoCache()
        cache.delete_pattern(f"inventory:dashboard:{tenant_id}")
        cache.delete_pattern(f"inventory:alerts:{tenant_id}")

    # ── Custom actions ────────────────────────────────────────────────────────

    @extend_schema(
        summary="Items below reorder level",
        description="Returns all active items where current_stock ≤ reorder_level.",
        tags=["Inventory — Items"],
    )
    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        qs = self.get_queryset().filter(
            is_active=True,
            current_stock__lte=F("reorder_level"),
        ).order_by("current_stock")
        page = self.paginate_queryset(qs)
        serializer = InventoryItemListSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response({"success": True, "results": serializer.data})

    @extend_schema(
        summary="Items with batches expiring soon",
        parameters=[
            OpenApiParameter("days", int, description=f"Look-ahead days (default {EXPIRY_WARNING_DAYS})"),
        ],
        tags=["Inventory — Items"],
    )
    @action(detail=False, methods=["get"], url_path="expiring-soon")
    def expiring_soon(self, request):
        days   = int(request.query_params.get("days", EXPIRY_WARNING_DAYS))
        cutoff = timezone.now().date() + datetime.timedelta(days=days)
        qs = self.get_queryset().filter(
            is_active=True,
            batches__is_active=True,
            batches__expiry_date__lte=cutoff,
            batches__expiry_date__isnull=False,
            batches__remaining_quantity__gt=0,
        ).distinct().order_by("name")
        page = self.paginate_queryset(qs)
        serializer = InventoryItemListSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response({"success": True, "results": serializer.data})

    @extend_schema(
        summary="Stock transaction history for an item",
        parameters=[
            OpenApiParameter("date_from", str, description="YYYY-MM-DD"),
            OpenApiParameter("date_to",   str, description="YYYY-MM-DD"),
            OpenApiParameter("transaction_type", str),
        ],
        tags=["Inventory — Items"],
    )
    @action(detail=True, methods=["get"], url_path="stock-history")
    def stock_history(self, request, pk=None):
        item = self.get_object()
        qs   = StockTransaction.objects.filter(tenant_id=request.tenant_id, item=item)

        date_from = request.query_params.get("date_from")
        date_to   = request.query_params.get("date_to")
        txn_type  = request.query_params.get("transaction_type")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if txn_type:
            qs = qs.filter(transaction_type=txn_type)

        qs = qs.order_by("-created_at")
        page = self.paginate_queryset(qs)
        serializer = StockTransactionSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response({"success": True, "results": serializer.data})


# ─── 4. Batch ViewSet ────────────────────────────────────────────────────────

@extend_schema_view(
    list=extend_schema(
        summary="List batches",
        parameters=[
            OpenApiParameter("item",      int,  description="Filter by item ID"),
            OpenApiParameter("supplier",  int,  description="Filter by supplier ID"),
            OpenApiParameter("is_active", bool),
            OpenApiParameter("expiring_within_days", int,
                             description="Batches expiring within N days"),
        ],
        tags=["Inventory — Batches"],
    ),
    create=extend_schema(summary="Add batch", tags=["Inventory — Batches"]),
    retrieve=extend_schema(summary="Get batch", tags=["Inventory — Batches"]),
    partial_update=extend_schema(summary="Update batch notes/status", tags=["Inventory — Batches"]),
    destroy=extend_schema(summary="Delete batch", tags=["Inventory — Batches"]),
)
class InventoryBatchViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = InventoryBatch.objects.select_related("item", "supplier").all()
    serializer_class = InventoryBatchSerializer
    permission_classes = [HMSPermission]
    hms_module = "inventory"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    action_permission_map = {
        "list":           "view_inventory",
        "retrieve":       "view_inventory",
        "create":         "manage_inventory",
        "partial_update": "manage_inventory",
        "destroy":        "manage_inventory",
    }

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["item", "supplier", "is_active"]
    search_fields    = ["batch_number", "item__name"]
    ordering_fields  = ["expiry_date", "created_at"]
    ordering         = ["expiry_date"]

    def get_queryset(self):
        qs = super().get_queryset()
        days_param = self.request.query_params.get("expiring_within_days")
        if days_param:
            try:
                cutoff = timezone.now().date() + datetime.timedelta(days=int(days_param))
                qs = qs.filter(
                    expiry_date__lte=cutoff,
                    expiry_date__isnull=False,
                    remaining_quantity__gt=0,
                )
            except (ValueError, TypeError):
                pass
        return qs

    def perform_create(self, serializer):
        """
        Creating a batch via this endpoint adds stock automatically.
        Use POST /stock-transactions/receive/ for the full workflow.
        """
        batch = serializer.save(
            tenant_id=self.request.tenant_id,
            created_by_user_id=self.request.user_id,
        )
        # If quantity_received > 0, auto-create a 'purchase' transaction
        if batch.quantity_received > 0:
            item = batch.item
            _apply_transaction(
                item=item,
                quantity=batch.quantity_received,
                transaction_type="purchase",
                tenant_id=self.request.tenant_id,
                batch=batch,
                unit_cost=batch.purchase_price,
                reference_type="purchase_order",
                notes=f"Auto-created on batch {batch.batch_number} creation.",
                performed_by_user_id=self.request.user_id,
            )


# ─── 5. Stock Transaction ViewSet ─────────────────────────────────────────────

@extend_schema_view(
    list=extend_schema(
        summary="List stock transactions",
        parameters=[
            OpenApiParameter("item",             int,  description="Filter by item ID"),
            OpenApiParameter("transaction_type", str,  description="Filter by type"),
            OpenApiParameter("reference_type",   str),
            OpenApiParameter("date_from",        str,  description="YYYY-MM-DD"),
            OpenApiParameter("date_to",          str,  description="YYYY-MM-DD"),
        ],
        tags=["Inventory — Transactions"],
    ),
    retrieve=extend_schema(summary="Get transaction", tags=["Inventory — Transactions"]),
)
class StockTransactionViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only base (GET list/retrieve).
    All writes happen through the dedicated action endpoints:
      POST /receive/   — receive new stock from supplier
      POST /issue/     — issue to OPD/IPD patient or general
      POST /adjust/    — manual stock correction
    """
    queryset = StockTransaction.objects.select_related("item", "batch").all()
    serializer_class = StockTransactionSerializer
    permission_classes = [HMSPermission]
    hms_module = "inventory"

    action_permission_map = {
        "list":     "view_inventory",
        "retrieve": "view_inventory",
        "receive":  "manage_inventory",
        "issue":    "manage_inventory",
        "adjust":   "manage_inventory",
    }

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["item", "transaction_type", "reference_type"]
    ordering_fields  = ["created_at", "quantity"]
    ordering         = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        date_from = params.get("date_from")
        date_to   = params.get("date_to")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs

    # ── Receive ───────────────────────────────────────────────────────────────

    @extend_schema(
        summary="Receive stock from supplier",
        description=(
            "Creates a new batch and adds stock. "
            "Also creates a `purchase` StockTransaction automatically."
        ),
        request=ReceiveStockSerializer,
        responses={201: StockTransactionSerializer},
        tags=["Inventory — Transactions"],
    )
    @action(detail=False, methods=["post"])
    def receive(self, request):
        ser = ReceiveStockSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        # Resolve item
        try:
            item = InventoryItem.objects.get(pk=d["item"], tenant_id=request.tenant_id)
        except InventoryItem.DoesNotExist:
            return error_response("ITEM_NOT_FOUND", "Item not found.", status=404)

        supplier = None
        if d.get("supplier"):
            try:
                supplier = InventorySupplier.objects.get(
                    pk=d["supplier"], tenant_id=request.tenant_id
                )
            except InventorySupplier.DoesNotExist:
                return error_response("SUPPLIER_NOT_FOUND", "Supplier not found.", status=404)

        quantity = Decimal(str(d["quantity"]))

        with db_transaction.atomic():
            batch = InventoryBatch.objects.create(
                tenant_id=request.tenant_id,
                item=item,
                batch_number=d["batch_number"],
                expiry_date=d.get("expiry_date"),
                manufacturing_date=d.get("manufacturing_date"),
                supplier=supplier,
                purchase_price=d.get("unit_cost", Decimal("0.00")),
                quantity_received=quantity,
                remaining_quantity=Decimal("0"),  # _apply_transaction increments this via F()
                created_by_user_id=request.user_id,
                notes=d.get("notes", ""),
            )

        txn = _apply_transaction(
            item=item,
            quantity=quantity,
            transaction_type="purchase",
            tenant_id=request.tenant_id,
            batch=batch,
            unit_cost=d.get("unit_cost", Decimal("0.00")),
            reference_type="purchase_order",
            reference_id=d.get("reference_id", ""),
            notes=d.get("notes", ""),
            performed_by_user_id=request.user_id,
        )

        return Response(
            {"success": True, "message": "Stock received.", "data": StockTransactionSerializer(txn).data},
            status=status.HTTP_201_CREATED,
        )

    # ── Issue ─────────────────────────────────────────────────────────────────

    @extend_schema(
        summary="Issue stock",
        description="Issue items to an OPD visit, IPD admission, or for general use.",
        request=IssueStockSerializer,
        responses={201: StockTransactionSerializer},
        tags=["Inventory — Transactions"],
    )
    @action(detail=False, methods=["post"])
    def issue(self, request):
        ser = IssueStockSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        try:
            item = InventoryItem.objects.get(pk=d["item"], tenant_id=request.tenant_id)
        except InventoryItem.DoesNotExist:
            return error_response("ITEM_NOT_FOUND", "Item not found.", status=404)

        batch = None
        if d.get("batch"):
            try:
                batch = InventoryBatch.objects.get(
                    pk=d["batch"], item=item, tenant_id=request.tenant_id
                )
            except InventoryBatch.DoesNotExist:
                return error_response("BATCH_NOT_FOUND", "Batch not found for this item.", status=404)

        quantity = Decimal(str(d["quantity"]))

        # Validate sufficient stock
        item.refresh_from_db(fields=["current_stock"])
        if item.current_stock < quantity:
            return error_response(
                "INSUFFICIENT_STOCK",
                f"Insufficient stock. Available: {item.current_stock} {item.unit_of_measure}.",
                status=422,
            )
        if batch and batch.remaining_quantity < quantity:
            return error_response(
                "INSUFFICIENT_BATCH_STOCK",
                f"Insufficient batch stock. Batch has: {batch.remaining_quantity} {item.unit_of_measure}.",
                status=422,
            )

        txn = _apply_transaction(
            item=item,
            quantity=quantity,
            transaction_type=d.get("issue_type", "issue_general"),
            tenant_id=request.tenant_id,
            batch=batch,
            reference_type=d.get("reference_type", "manual"),
            reference_id=d.get("reference_id", ""),
            notes=d.get("notes", ""),
            performed_by_user_id=request.user_id,
        )

        return Response(
            {"success": True, "message": "Stock issued.", "data": StockTransactionSerializer(txn).data},
            status=status.HTTP_201_CREATED,
        )

    # ── Adjust ────────────────────────────────────────────────────────────────

    @extend_schema(
        summary="Manual stock adjustment",
        description="Add or remove stock manually (disposal, write-off, correction).",
        request=AdjustStockSerializer,
        responses={201: StockTransactionSerializer},
        tags=["Inventory — Transactions"],
    )
    @action(detail=False, methods=["post"])
    def adjust(self, request):
        ser = AdjustStockSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        try:
            item = InventoryItem.objects.get(pk=d["item"], tenant_id=request.tenant_id)
        except InventoryItem.DoesNotExist:
            return error_response("ITEM_NOT_FOUND", "Item not found.", status=404)

        batch = None
        if d.get("batch"):
            try:
                batch = InventoryBatch.objects.get(
                    pk=d["batch"], item=item, tenant_id=request.tenant_id
                )
            except InventoryBatch.DoesNotExist:
                return error_response("BATCH_NOT_FOUND", "Batch not found for this item.", status=404)

        quantity      = Decimal(str(d["quantity"]))
        adj_type      = d["adjustment_type"]
        is_reduction  = adj_type not in StockTransaction.ADDITION_TYPES

        if is_reduction:
            item.refresh_from_db(fields=["current_stock"])
            if item.current_stock < quantity:
                return error_response(
                    "INSUFFICIENT_STOCK",
                    f"Cannot remove {quantity}. Available: {item.current_stock} {item.unit_of_measure}.",
                    status=422,
                )

        txn = _apply_transaction(
            item=item,
            quantity=quantity,
            transaction_type=adj_type,
            tenant_id=request.tenant_id,
            batch=batch,
            notes=d.get("notes", ""),
            performed_by_user_id=request.user_id,
        )

        return Response(
            {"success": True, "message": "Stock adjusted.", "data": StockTransactionSerializer(txn).data},
            status=status.HTTP_201_CREATED,
        )


# ─── 6. Alert ViewSet ────────────────────────────────────────────────────────

@extend_schema_view(
    list=extend_schema(
        summary="List stock alerts",
        parameters=[
            OpenApiParameter("is_active",       bool),
            OpenApiParameter("is_acknowledged", bool),
            OpenApiParameter("alert_type",      str,
                description="low_stock | out_of_stock | expiry_approaching | expired | overstock"),
            OpenApiParameter("item",            int),
        ],
        tags=["Inventory — Alerts"],
    ),
    retrieve=extend_schema(summary="Get alert", tags=["Inventory — Alerts"]),
)
class StockAlertViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = StockAlert.objects.select_related("item", "batch").all()
    serializer_class = StockAlertSerializer
    permission_classes = [HMSPermission]
    hms_module = "inventory"

    action_permission_map = {
        "list":        "view_inventory",
        "retrieve":    "view_inventory",
        "acknowledge": "manage_inventory",
        "summary":     "view_inventory",
        "refresh":     "manage_inventory",
    }

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["is_active", "is_acknowledged", "alert_type", "item"]
    ordering_fields  = ["created_at", "updated_at"]
    ordering         = ["-created_at"]

    @extend_schema(
        summary="Acknowledge an alert",
        description="Marks the alert as acknowledged. Does not resolve it — stock must improve for that.",
        responses={200: StockAlertSerializer},
        tags=["Inventory — Alerts"],
    )
    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        if alert.is_acknowledged:
            return action_response("Alert already acknowledged.", data=StockAlertSerializer(alert).data)
        alert.is_acknowledged       = True
        alert.acknowledged_by_user_id = request.user_id
        alert.acknowledged_at       = timezone.now()
        alert.save(update_fields=["is_acknowledged", "acknowledged_by_user_id", "acknowledged_at", "updated_at"])
        return action_response("Alert acknowledged.", data=StockAlertSerializer(alert).data)

    @extend_schema(
        summary="Alert summary counts",
        description="Returns count of active alerts by type for the badge/notification display.",
        tags=["Inventory — Alerts"],
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        from .services.stats import compute_alerts_summary

        cache = CeliyoCache()
        cache_key = f"inventory:alerts:{request.tenant_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        # Shared computation with the consolidated dashboard endpoint —
        # see apps/inventory/services/stats.py.
        data = {
            "success": True,
            "data": compute_alerts_summary(request.tenant_id),
        }
        cache.set(cache_key, data, ttl=180)
        return Response(data)

    @extend_schema(
        summary="Refresh all alerts for tenant",
        description=(
            "Re-evaluates stock thresholds and expiry for every active item. "
            "Useful after a bulk import. May be slow for large inventories."
        ),
        tags=["Inventory — Alerts"],
    )
    @action(detail=False, methods=["post"])
    def refresh(self, request):
        items = InventoryItem.objects.filter(
            tenant_id=request.tenant_id, is_active=True
        )
        count = 0
        for item in items.iterator(chunk_size=200):
            _check_and_update_alerts(item, request.tenant_id)
            count += 1
        return action_response(f"Alert refresh complete. {count} items evaluated.")


# ─── 7. Dashboard ViewSet ────────────────────────────────────────────────────

class InventoryDashboardViewSet(TenantViewSetMixin, viewsets.ViewSet):
    """Single endpoint that returns the inventory dashboard stats."""
    permission_classes = [HMSPermission]
    hms_module = "inventory"
    # ViewSet with no model — override get_queryset with a no-op
    queryset = InventoryItem.objects.none()

    action_permission_map = {
        "stats": "view_inventory",
    }

    def get_queryset(self):
        return InventoryItem.objects.filter(tenant_id=self.request.tenant_id)

    @extend_schema(
        summary="Inventory dashboard statistics",
        responses={200: InventoryDashboardSerializer},
        tags=["Inventory — Dashboard"],
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        from .services.stats import compute_dashboard_stats

        cache = CeliyoCache()
        cache_key = f"inventory:dashboard:{request.tenant_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        # Shared computation with the consolidated dashboard endpoint —
        # see apps/inventory/services/stats.py.
        result = {
            "success": True,
            "data": compute_dashboard_stats(request.tenant_id),
        }
        cache.set(cache_key, result, ttl=300)
        return Response(result)
