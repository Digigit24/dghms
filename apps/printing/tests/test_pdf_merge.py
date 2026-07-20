from io import BytesIO
import uuid
from unittest.mock import patch

from django.test import SimpleTestCase
from pypdf import PdfReader, PdfWriter
from rest_framework.test import APIRequestFactory, force_authenticate

from common.auth_backends import TenantUser
from apps.printing.rendering import (
    A4_HEIGHT_POINTS,
    A4_WIDTH_POINTS,
    PdfMergeError,
    merge_pdfs,
)
from apps.printing.views import ClinicalDocumentBatchPrintView


def _blank_pdf(*page_sizes: tuple[float, float], password: str | None = None) -> bytes:
    writer = PdfWriter()
    for width, height in page_sizes:
        writer.add_blank_page(width=width, height=height)
    if password:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PdfMergeTest(SimpleTestCase):
    def test_rejects_empty_batch(self):
        with self.assertRaisesRegex(PdfMergeError, "At least one"):
            merge_pdfs([])

    def test_rejects_corrupt_input_with_document_index(self):
        with self.assertRaises(PdfMergeError) as raised:
            merge_pdfs([_blank_pdf((612, 792)), b"not a PDF"])

        self.assertEqual(raised.exception.document_index, 1)
        self.assertIn("document 2", str(raised.exception))

    def test_rejects_password_protected_input(self):
        with self.assertRaises(PdfMergeError) as raised:
            merge_pdfs([_blank_pdf((612, 792), password="secret")])

        self.assertEqual(raised.exception.document_index, 0)
        self.assertIn("password-protected", str(raised.exception))

    def test_rejects_zero_page_pdf(self):
        with self.assertRaises(PdfMergeError) as raised:
            merge_pdfs([_blank_pdf()])

        self.assertEqual(raised.exception.document_index, 0)
        self.assertIn("no pages", str(raised.exception))

    def test_preserves_page_count_and_normalizes_every_page_to_a4(self):
        merged = merge_pdfs(
            [
                _blank_pdf((612, 792), (A4_WIDTH_POINTS, A4_HEIGHT_POINTS)),
                _blank_pdf((792, 612), (420, 595)),
            ]
        )
        pages = PdfReader(BytesIO(merged), strict=True).pages

        self.assertEqual(len(pages), 4)
        for page in pages:
            self.assertAlmostEqual(float(page.mediabox.width), A4_WIDTH_POINTS, places=3)
            self.assertAlmostEqual(float(page.mediabox.height), A4_HEIGHT_POINTS, places=3)
            self.assertEqual(page.rotation, 0)

    def test_single_document_is_also_normalized(self):
        merged = merge_pdfs([_blank_pdf((612, 792))])
        page = PdfReader(BytesIO(merged), strict=True).pages[0]

        self.assertAlmostEqual(float(page.mediabox.width), A4_WIDTH_POINTS, places=3)
        self.assertAlmostEqual(float(page.mediabox.height), A4_HEIGHT_POINTS, places=3)

    @patch("apps.printing.views.render_document_batch_pdf")
    def test_batch_api_returns_structured_merge_error(self, render_batch):
        render_batch.side_effect = PdfMergeError(
            "second document is corrupt",
            document_index=1,
        )
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        user = TenantUser(
            {
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
                "email": "print-test@example.invalid",
                "is_super_admin": True,
                "permissions": {},
            }
        )
        request = APIRequestFactory().post(
            "/api/print/documents/batch/",
            {
                "template_codes": ["general_consent", "st_nurses_continuation"],
                "encounter_type": "opd_visit",
                "encounter_id": 1,
                "letterhead": True,
                "language": "en",
            },
            format="json",
        )
        request.tenant_id = tenant_id
        request.user_id = user_id
        request.permissions = {}
        request.is_super_admin = True
        force_authenticate(request, user=user)

        response = ClinicalDocumentBatchPrintView.as_view()(request)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["error"]["code"], "PDF_MERGE_FAILED")
        self.assertEqual(response.data["error"]["detail"]["document_index"], 1)
        self.assertEqual(
            response.data["error"]["detail"]["document_code"],
            "st_nurses_continuation",
        )
