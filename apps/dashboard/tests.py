from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboard.views import _can_view_recent_encounters


class RecentEncountersPermissionTest(SimpleTestCase):
    def _assert_allowed_by(self, permission):
        request = SimpleNamespace()

        with patch(
            "apps.dashboard.views.check_permission",
            side_effect=lambda _request, key: key == permission,
        ):
            self.assertTrue(_can_view_recent_encounters(request))

    def test_patient_view_is_allowed(self):
        self._assert_allowed_by("hms.patients.view")

    def test_pharmacy_view_is_allowed(self):
        self._assert_allowed_by("hms.pharmacy.view")

    def test_diagnostics_view_is_allowed(self):
        self._assert_allowed_by("hms.diagnostics.view")

    def test_unrelated_permission_is_denied(self):
        with patch("apps.dashboard.views.check_permission", return_value=False):
            self.assertFalse(_can_view_recent_encounters(SimpleNamespace()))
