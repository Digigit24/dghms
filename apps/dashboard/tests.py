import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from apps.dashboard.views import (
    _can_view_recent_encounters,
    _pending_counts_for_encounters,
)


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


class RecentEncounterPendingCountsTest(TestCase):
    def setUp(self):
        from apps.diagnostics.models import DiagnosticOrder, Investigation, Requisition
        from apps.ipd.models import Admission
        from apps.opd.models import Visit
        from apps.patients.models import PatientProfile
        from apps.pharmacy.models import Prescription, PrescriptionItem

        self.tenant_id = uuid.uuid4()
        patient = PatientProfile.objects.create(
            tenant_id=self.tenant_id,
            first_name="Pending",
            last_name="Counts",
            gender="male",
            mobile_primary="9999999999",
        )
        visit = Visit.objects.create(
            tenant_id=self.tenant_id,
            visit_number="OPD/PENDING/001",
            patient=patient,
        )
        self.opd_id = visit.id
        self.ipd_id = 909

        visit_content_type = ContentType.objects.get_for_model(Visit)
        admission_content_type = ContentType.objects.get_for_model(Admission)

        opd_prescription = Prescription.objects.create(
            tenant_id=self.tenant_id,
            visit=visit,
            content_type=visit_content_type,
            object_id=visit.id,
        )
        PrescriptionItem.objects.create(
            tenant_id=self.tenant_id,
            prescription=opd_prescription,
            medicine_name="Pending OPD",
            is_dispensed=False,
        )
        PrescriptionItem.objects.create(
            tenant_id=self.tenant_id,
            prescription=opd_prescription,
            medicine_name="Dispensed OPD",
            is_dispensed=True,
        )

        ipd_prescription = Prescription.objects.create(
            tenant_id=self.tenant_id,
            content_type=admission_content_type,
            object_id=self.ipd_id,
        )
        for name in ("Pending IPD A", "Pending IPD B"):
            PrescriptionItem.objects.create(
                tenant_id=self.tenant_id,
                prescription=ipd_prescription,
                medicine_name=name,
                is_dispensed=False,
            )

        investigation = Investigation.objects.create(
            tenant_id=self.tenant_id,
            name="CBC",
            code="CBC-PENDING",
        )
        opd_requisition = Requisition.objects.create(
            tenant_id=self.tenant_id,
            content_type=visit_content_type,
            object_id=self.opd_id,
            patient=patient,
            requesting_doctor_id=uuid.uuid4(),
            requisition_type="investigation",
        )
        DiagnosticOrder.objects.create(
            tenant_id=self.tenant_id,
            requisition=opd_requisition,
            investigation=investigation,
            status="processing",
        )
        DiagnosticOrder.objects.create(
            tenant_id=self.tenant_id,
            requisition=opd_requisition,
            investigation=investigation,
            status="completed",
        )

        ipd_requisition = Requisition.objects.create(
            tenant_id=self.tenant_id,
            content_type=admission_content_type,
            object_id=self.ipd_id,
            patient=patient,
            requesting_doctor_id=uuid.uuid4(),
            requisition_type="investigation",
        )
        DiagnosticOrder.objects.create(
            tenant_id=self.tenant_id,
            requisition=ipd_requisition,
            investigation=investigation,
            status="pending",
        )
        DiagnosticOrder.objects.create(
            tenant_id=self.tenant_id,
            requisition=ipd_requisition,
            investigation=investigation,
            status="cancelled",
        )

    def test_counts_are_batched_and_match_pending_work(self):
        rows = [
            {"encounter_type": "opd", "encounter_id": self.opd_id},
            {"encounter_type": "ipd", "encounter_id": self.ipd_id},
        ]
        ContentType.objects.clear_cache()

        with CaptureQueriesContext(connection) as queries:
            pharmacy_counts, lab_counts = _pending_counts_for_encounters(
                self.tenant_id,
                rows,
            )

        self.assertLessEqual(len(queries), 3)
        self.assertEqual(pharmacy_counts[("opd", self.opd_id)], 1)
        self.assertEqual(pharmacy_counts[("ipd", self.ipd_id)], 2)
        self.assertEqual(lab_counts[("opd", self.opd_id)], 1)
        self.assertEqual(lab_counts[("ipd", self.ipd_id)], 1)

    def test_empty_page_uses_no_queries(self):
        with self.assertNumQueries(0):
            pharmacy_counts, lab_counts = _pending_counts_for_encounters(
                self.tenant_id,
                [],
            )

        self.assertEqual(pharmacy_counts, {})
        self.assertEqual(lab_counts, {})
