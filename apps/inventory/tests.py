import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.inventory.views import StockAlertViewSet, _eval_expiry_alert
from apps.inventory.services.expiry import (
    get_tenant_default_expiry_alert_days,
    resolve_expiry_alert_days,
)
from apps.inventory.views import _filter_by_tags


class InventoryAlertCacheFailureTests(SimpleTestCase):
    @patch("apps.inventory.services.stats.compute_alerts_summary")
    @patch("apps.inventory.views.CeliyoCache")
    def test_summary_computes_when_cache_is_unavailable(self, cache_class, compute):
        cache = cache_class.return_value
        cache.get.side_effect = ConnectionError("redis unavailable")
        cache.set.side_effect = ConnectionError("redis unavailable")
        compute.return_value = {"total_active": 3}

        response = StockAlertViewSet().summary(
            SimpleNamespace(tenant_id="tenant-1", query_params={})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], {"total_active": 3})
        compute.assert_called_once_with("tenant-1", tags=[])
        cache.set.assert_not_called()


class ExpiryAlertConfigurationTests(SimpleTestCase):
    @patch("apps.inventory.services.expiry.Hospital.objects")
    def test_hardcoded_default_is_final_fallback(self, hospital_objects):
        values = hospital_objects.filter.return_value.values_list.return_value
        values.first.return_value = None

        self.assertEqual(get_tenant_default_expiry_alert_days("tenant-1"), 90)

    def test_item_override_wins(self):
        item = SimpleNamespace(
            expiry_alert_days=14,
            category=SimpleNamespace(expiry_alert_days=30),
            tenant_id="tenant-1",
        )
        self.assertEqual(resolve_expiry_alert_days(item, tenant_default=60), 14)

    def test_category_override_wins_over_tenant(self):
        item = SimpleNamespace(
            expiry_alert_days=None,
            category=SimpleNamespace(expiry_alert_days=30),
            tenant_id="tenant-1",
        )
        self.assertEqual(resolve_expiry_alert_days(item, tenant_default=60), 30)

    def test_tenant_default_is_used_when_no_override(self):
        item = SimpleNamespace(
            expiry_alert_days=None,
            category=SimpleNamespace(expiry_alert_days=None),
            tenant_id="tenant-1",
        )
        self.assertEqual(resolve_expiry_alert_days(item, tenant_default=60), 60)

    @patch("apps.inventory.views.StockAlert.objects")
    def test_alert_snapshot_uses_resolved_category_threshold(self, alerts):
        item = SimpleNamespace(
            id=1,
            name="Medicine",
            unit_of_measure="box",
            expiry_alert_days=None,
            category=SimpleNamespace(expiry_alert_days=30),
            tenant_id="tenant-1",
        )
        batch = SimpleNamespace(
            id=2,
            expiry_date=datetime.date.today() + datetime.timedelta(days=20),
            remaining_quantity=Decimal("2"),
            batch_number="B1",
        )

        _eval_expiry_alert(item, batch, "tenant-1", tenant_default=60)

        defaults = alerts.update_or_create.call_args.kwargs["defaults"]
        self.assertEqual(defaults["threshold"], Decimal("30"))


class InventoryTagFilterTests(SimpleTestCase):
    def test_comma_separated_tags_use_and_semantics(self):
        queryset = Mock()
        second = Mock()
        queryset.filter.return_value = second
        second.filter.return_value = second

        result = _filter_by_tags(queryset, ["pharmacy", "general"], "item__")

        queryset.filter.assert_called_once_with(item__tags__contains="pharmacy")
        second.filter.assert_called_once_with(item__tags__contains="general")
        self.assertIs(result, second)
