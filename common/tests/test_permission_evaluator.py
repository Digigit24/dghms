import logging
import unittest
from types import SimpleNamespace

from common import permission_evaluator as evaluator


class FakeQuerySet:
    model = None

    def __init__(self):
        self.filters = []
        self.was_none = False

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def none(self):
        self.was_none = True
        return self


def subject(permissions, *, user_id="u-1", tenant_id="t-1"):
    return SimpleNamespace(permissions=permissions, user_id=user_id, tenant_id=tenant_id,
                           roles=["doctor"], is_super_admin=False)


class PermissionEvaluatorTests(unittest.TestCase):
    def test_queryset_tenant_filter_is_first_and_all_stops_there(self):
        qs = FakeQuerySet()
        result = evaluator.get_queryset_for_permission(subject({"hms.patients.view": "all"}), "hms.patients.view", qs)
        self.assertIs(result, qs)
        self.assertEqual(qs.filters, [{"tenant_id": "t-1"}])

    def test_own_requires_resolved_owner_and_fails_closed(self):
        grant = subject({"hms.clinical.edit": "own"})
        self.assertFalse(evaluator.has_permission(grant, "hms.clinical.edit", SimpleNamespace()))
        self.assertTrue(evaluator.has_permission(grant, "hms.clinical.edit", SimpleNamespace(doctor_id="u-1")))
        self.assertFalse(evaluator.has_permission(grant, "hms.clinical.edit", SimpleNamespace(doctor_id="other")))

    def test_own_queryset_filters_after_tenant(self):
        qs = FakeQuerySet()
        evaluator.get_queryset_for_permission(subject({"hms.patients.view": "own"}), "hms.patients.view", qs)
        self.assertEqual(qs.filters, [{"tenant_id": "t-1"}, {"user_id": "u-1"}])

    def test_create_does_not_imply_view(self):
        grant = subject({"hms.patients.create": True})
        self.assertFalse(evaluator.has_permission(grant, "hms.patients.view"))

    def test_team_normalizes_to_all_and_warns(self):
        grant = subject({"hms.patients.view": "team"})
        with self.assertLogs("common.permission_evaluator", logging.WARNING) as logs:
            self.assertTrue(evaluator.has_permission(grant, "hms.patients.view"))
        self.assertIn("permission_legacy_team_normalized", logs.output[0])

    def test_unknown_string_is_rejected(self):
        with self.assertLogs("common.permission_evaluator", logging.WARNING) as logs:
            self.assertFalse(evaluator.has_permission(subject({"hms.patients.view": "yes"}), "hms.patients.view"))
        self.assertIn("permission_unknown_value_rejected", logs.output[0])

    def test_full_access_is_tenant_scoped_wildcard(self):
        grant = subject({"admin.full_access.enabled": True})
        self.assertTrue(evaluator.has_permission(grant, "hms.payments.refund"))
        qs = FakeQuerySet()
        evaluator.get_queryset_for_permission(grant, "hms.patients.view", qs)
        self.assertEqual(qs.filters, [{"tenant_id": "t-1"}])
