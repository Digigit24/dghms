from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.diagnostics.views import DiagnosticOrderViewSet


class DiagnosticEncounterAliasTest(SimpleTestCase):
    def test_short_and_dotted_aliases_resolve_identically(self):
        def fake_get(*, app_label, model):
            return SimpleNamespace(app_label=app_label, model=model)

        with patch(
            "apps.diagnostics.views.ContentType.objects.get",
            side_effect=fake_get,
        ):
            for value in ("opd", "opd.visit"):
                resolved = DiagnosticOrderViewSet._resolve_encounter_content_type(value)
                self.assertEqual((resolved.app_label, resolved.model), ("opd", "visit"))
            for value in ("ipd", "ipd.admission"):
                resolved = DiagnosticOrderViewSet._resolve_encounter_content_type(value)
                self.assertEqual((resolved.app_label, resolved.model), ("ipd", "admission"))
