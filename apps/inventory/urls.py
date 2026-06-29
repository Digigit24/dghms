from rest_framework.routers import DefaultRouter

from .views import (
    InventoryCategoryViewSet,
    InventoryDashboardViewSet,
    InventoryItemViewSet,
    InventoryBatchViewSet,
    InventorySupplierViewSet,
    StockAlertViewSet,
    StockTransactionViewSet,
)

router = DefaultRouter()
router.register(r"categories",         InventoryCategoryViewSet,   basename="inventory-category")
router.register(r"suppliers",          InventorySupplierViewSet,   basename="inventory-supplier")
router.register(r"items",              InventoryItemViewSet,        basename="inventory-item")
router.register(r"batches",            InventoryBatchViewSet,       basename="inventory-batch")
router.register(r"stock-transactions", StockTransactionViewSet,    basename="inventory-transaction")
router.register(r"alerts",             StockAlertViewSet,          basename="inventory-alert")
router.register(r"dashboard",          InventoryDashboardViewSet,  basename="inventory-dashboard")

urlpatterns = router.urls
