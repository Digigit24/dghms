import uuid

from django.test import TestCase

from apps.clinical.models import ClinicalForm
from apps.printing.rendering import (
    PrintFormCodeError,
    PrintNotFoundError,
    build_print_context,
    resolve_print_form_code,
)


class PrintFormCodeResolutionTests(TestCase):
    def test_resolves_actual_tenant_clinical_form_code_to_registered_print_code(self):
        tenant_id = uuid.uuid4()
        ClinicalForm.objects.create(
            tenant_id=tenant_id,
            code="system_ipd_monitoring_entry",
            name="IPD Monitoring Chart Entry",
            print_template_code=ClinicalForm.PrintTemplateCode.MONITORING_CHART,
        )

        self.assertEqual(
            resolve_print_form_code("system_ipd_monitoring_entry", tenant_id),
            "monitoring_chart",
        )

    def test_resolves_actual_system_clinical_form_code_for_tenant_request(self):
        request_tenant_id = uuid.uuid4()
        ClinicalForm.objects.create(
            tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            code="system_ipd_nursing_notes",
            name="Nurses Continuation Sheet",
            is_system=True,
            print_template_code=ClinicalForm.PrintTemplateCode.NURSING_PAPER,
        )

        self.assertEqual(
            resolve_print_form_code("system_ipd_nursing_notes", request_tenant_id),
            "nursing_paper",
        )

    def test_build_print_context_normalizes_actual_form_code_before_template_lookup(self):
        tenant_id = uuid.uuid4()
        ClinicalForm.objects.create(
            tenant_id=tenant_id,
            code="round_notes",
            name="Round Notes",
            print_template_code=ClinicalForm.PrintTemplateCode.PROGRESS_SHEET,
        )

        with self.assertRaisesRegex(PrintNotFoundError, "Clinical record 123 not found"):
            build_print_context("round_notes", tenant_id, 123, letterhead=False, language="en")

    def test_unknown_form_code_still_fails_cleanly(self):
        with self.assertRaises(PrintFormCodeError):
            resolve_print_form_code("not_a_real_print_or_form_code", uuid.uuid4())
