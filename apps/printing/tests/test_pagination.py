from io import BytesIO
from types import SimpleNamespace
from unittest import SkipTest

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from pypdf import PdfReader

from apps.printing.rendering import render_pdf_from_html


class ClinicalFormPaginationTest(SimpleTestCase):
    def test_long_form_paginates_and_repeats_letterhead(self):
        fields = [
            {
                "field_type": "text",
                "label": f"Field {index}",
                "display_value": f"Value {index}",
            }
            for index in range(160)
        ]
        context = {
            "structure": {"name": "Pagination regression form"},
            "record": SimpleNamespace(id=999),
            "uhid": "VERIFY-001",
            "ipd_no": "",
            "encounter_id": 999,
            "patient_name": "Pagination Verification",
            "age": 40,
            "gender": "Other",
            "encounter_type": "opd_visit",
            "sections": [{"title": "Long section", "section_fields": fields}],
            "letterhead": {
                "enabled": True,
                "show_logo": False,
                "logo_url": "",
                "show_badge": False,
                "badge_url": "",
                "alignment": "left",
                "show_hairline": False,
                "layout_mode": "two_column",
                "text_lines": [
                    {"text": "JEEVISHA", "style": "title"},
                    {
                        "text": "SPINE | PAIN | REGENERATIVE HOSPITAL",
                        "style": "normal",
                    },
                ],
                "right_column_lines": [
                    {"text": "Dr. SANJOG MEKEWAR", "style": "title"},
                ],
                "background_pattern_url": None,
                "info_bar": {
                    "enabled": True,
                    "background_color": "#1e3a5f",
                    "text_color": "#ffffff",
                    "lines": [
                        {
                            "id": "address",
                            "text": "Pagination verification address",
                            "align": "center",
                        }
                    ],
                },
            },
        }
        html = render_to_string("print/clinical_form_generic.html", context)
        try:
            pdf = render_pdf_from_html(html)
        except OSError as exc:
            raise SkipTest(f"WeasyPrint native runtime unavailable: {exc}") from exc

        pages = PdfReader(BytesIO(pdf)).pages
        self.assertGreater(len(pages), 1)
        for page in pages:
            self.assertIn("JEEVISHA", page.extract_text())
