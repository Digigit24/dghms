from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from rest_framework.exceptions import PermissionDenied

from apps.clinical.models import ClinicalFormField, ClinicalFormSection
from apps.clinical.reference_sections import get_reference_sections
from apps.clinical.serializers import ClinicalFormSectionWriteSerializer
from apps.clinical.views import (
    ClinicalFormSectionViewSet,
    _prescription_item_defaults,
    _section_has_sync_role,
    _sync_prescription_grid_to_pharmacy,
)


def section(config=None, has_grid=False):
    fields = Mock()
    fields.filter.return_value.exists.return_value = has_grid
    return SimpleNamespace(config=config or {}, fields=fields)


class SectionSyncToggleTests(SimpleTestCase):
    def test_grid_toggle_resolves_to_structured_role(self):
        instance = section(has_grid=True)
        data = ClinicalFormSectionWriteSerializer._apply_toggles(
            instance, {"sync_pharmacy": True}
        )

        self.assertEqual(data["config"]["role"], "prescription")
        self.assertNotIn("visible_to_pharmacy", data["config"])
        self.assertTrue(_section_has_sync_role(SimpleNamespace(config=data["config"]), "prescription"))

    def test_non_grid_toggle_resolves_to_read_only_visibility(self):
        instance = section(has_grid=False)
        data = ClinicalFormSectionWriteSerializer._apply_toggles(
            instance, {"sync_pharmacy": True}
        )

        self.assertTrue(data["config"]["visible_to_pharmacy"])
        self.assertNotIn("role", data["config"])

    def test_section_response_always_exposes_both_toggle_booleans(self):
        instance = ClinicalFormSection(
            id=10,
            tenant_id="00000000-0000-0000-0000-000000000001",
            code="note",
            title="Note",
            config={"visible_to_pharmacy": True},
        )

        data = ClinicalFormSectionWriteSerializer(instance).data

        self.assertIs(data["sync_pharmacy"], True)
        self.assertIs(data["sync_lab"], False)

    def test_grid_can_sync_to_both_destinations(self):
        instance = section(has_grid=True)
        data = ClinicalFormSectionWriteSerializer._apply_toggles(
            instance, {"sync_pharmacy": True, "sync_lab": True}
        )

        self.assertEqual(data["config"]["roles"], ["prescription", "investigation"])

    @patch("apps.pharmacy.serializers.PrescriptionSerializer.resolve_encounter_type")
    @patch("apps.pharmacy.models.PrescriptionItem.objects")
    @patch("apps.pharmacy.models.Prescription.objects")
    def test_grid_role_creates_structured_prescription_item(
        self, prescriptions, items, resolve_content_type
    ):
        content_type = SimpleNamespace(app_label="opd", model="visit")
        resolve_content_type.return_value = content_type
        prescriptions.filter.return_value.order_by.return_value.first.return_value = None
        prescription = Mock(id=5, visit_id=42)
        prescriptions.create.return_value = prescription
        items.filter.return_value.order_by.return_value = []
        created_item = SimpleNamespace(id=9)
        items.create.return_value = created_item
        items.filter.return_value.exclude.return_value.filter.return_value.delete.return_value = (0, {})
        field = SimpleNamespace(
            field_type=ClinicalFormField.FieldType.GRID,
            section=SimpleNamespace(config={"role": "prescription"}),
        )
        record = SimpleNamespace(
            encounter_type="opd_visit",
            encounter_id=42,
            tenant_id="tenant-1",
        )

        result = _sync_prescription_grid_to_pharmacy(
            record,
            field,
            [{"medicine": "Paracetamol", "days": 4, "qty": 2}],
            "user-1",
        )

        self.assertIs(result, prescription)
        items.create.assert_called_once()
        created = items.create.call_args.kwargs
        self.assertEqual(created["medicine_name"], "Paracetamol")
        self.assertEqual(created["duration"], "4")
        self.assertEqual(created["quantity"], Decimal("2"))

    def test_legacy_days_and_qty_are_mapped(self):
        data = _prescription_item_defaults(
            {"medicine": "Paracetamol", "days": 4, "qty": 2}, "row-1"
        )

        self.assertEqual(data["duration"], "4")
        self.assertEqual(data["quantity"], Decimal("2"))

    @patch("apps.clinical.views.check_permission", return_value=False)
    def test_section_update_requires_clinical_edit(self, _permission):
        view = ClinicalFormSectionViewSet()
        view.request = SimpleNamespace()

        with self.assertRaises(PermissionDenied):
            view.perform_update(Mock())


class ReferenceSectionTests(SimpleTestCase):
    @patch("apps.clinical.reference_sections.ClinicalFieldValue.objects")
    def test_visible_non_grid_value_is_returned_read_only(self, objects):
        form = SimpleNamespace(id=4, code="consult", name="Consultation")
        record = SimpleNamespace(id=8, form_id=4, form=form)
        section_obj = SimpleNamespace(
            id=10,
            code="doctor_note",
            title="Doctor Note",
            config={"visible_to_pharmacy": True},
        )
        field = SimpleNamespace(
            id=12,
            field_key="note",
            label="Note",
            field_type=ClinicalFormField.FieldType.TEXTAREA,
            section=section_obj,
        )
        value = SimpleNamespace(
            record=record,
            field=field,
            field_id=12,
            value_text="Take after food",
            value_number=None,
            value_boolean=None,
            value_date=None,
            value_datetime=None,
            value_time=None,
            value_json=None,
            picklist_item_id=None,
        )
        queryset = objects.filter.return_value
        queryset.select_related.return_value = queryset
        queryset.order_by.return_value = [value]

        result = get_reference_sections(
            tenant_id="tenant-1",
            encounter_type="opd",
            encounter_id=1,
            audience="pharmacy",
        )

        self.assertEqual(result[0]["section_title"], "Doctor Note")
        self.assertEqual(result[0]["fields"][0]["value"], "Take after food")
