from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.inventory.views import StockAlertViewSet


class InventoryAlertCacheFailureTests(SimpleTestCase):
    @patch("apps.inventory.services.stats.compute_alerts_summary")
    @patch("apps.inventory.views.CeliyoCache")
    def test_summary_computes_when_cache_is_unavailable(self, cache_class, compute):
        cache = cache_class.return_value
        cache.get.side_effect = ConnectionError("redis unavailable")
        cache.set.side_effect = ConnectionError("redis unavailable")
        compute.return_value = {"total_active": 3}

        response = StockAlertViewSet().summary(
            SimpleNamespace(tenant_id="tenant-1")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], {"total_active": 3})
        cache.set.assert_not_called()
