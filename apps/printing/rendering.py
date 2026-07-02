"""Rendering helpers for server-side print (WeasyPrint) templates.

This module resolves the tenant letterhead context and the per-form print
context (patient/admission/clinical-record data), then hands a rendered
Django template string to WeasyPrint for PDF conversion. Kept separate from
``views.py`` so the HTML-building logic is independently testable and does
not need a live WeasyPrint import to be exercised in isolation.

Tenant isolation: every lookup function in this module takes an explicit
``tenant_id`` argument (never trusts client-supplied identifiers) and filters
every queryset by it, per CLAUDE.md §3.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from django.template.loader import render_to_string

from apps.clinical.models import (
    ClinicalFieldValue,
    ClinicalForm,
    ClinicalFormField,
    ClinicalRecord,
)
from apps.clinical.serializers import ClinicalFormStructureSerializer
from apps.hospital.models import Hospital
from apps.ipd.models import Admission

log = structlog.get_logger(__name__)

_SYSTEM_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

# Registered print form codes -> human labels (kept in sync with the
# frontend's SPECIFIC_PRINT_FORM_CODES in
# celiyohms/app/src/features/clinical/components/PrintPreviewModal.tsx).
FORM_ADMISSION = "admission_form"
FORM_NURSING_PAPER = "nursing_paper"
FORM_MONITORING_CHART = "monitoring_chart"
FORM_PROGRESS_SHEET = "progress_sheet"
FORM_CLINICAL_GENERIC = "clinical_form"

REGISTERED_FORM_CODES = {
    FORM_ADMISSION,
    FORM_NURSING_PAPER,
    FORM_MONITORING_CHART,
    FORM_PROGRESS_SHEET,
    FORM_CLINICAL_GENERIC,
}

# Template used for each registered form code.
_TEMPLATE_BY_FORM_CODE = {
    FORM_ADMISSION: "print/admission_form.html",
    FORM_NURSING_PAPER: "print/ipd_nursing_paper.html",
    FORM_MONITORING_CHART: "print/monitoring_chart.html",
    FORM_PROGRESS_SHEET: "print/progress_sheet.html",
    FORM_CLINICAL_GENERIC: "print/clinical_form_generic.html",
}

# Monitoring chart time slots: 2-hour intervals across a 24h cycle. No fixed
# time-slot field was found on a Monitoring Chart model/clinical form during
# investigation (it is modeled as a data-driven ClinicalForm with a GRID/table
# field, not a dedicated Django model) so this fixed slot list is used as the
# printed grid's row labels, matching common nursing chart conventions.
MONITORING_CHART_TIME_SLOTS = [
    "6 AM", "8 AM", "10 AM", "12 PM", "2 PM", "4 PM",
    "6 PM", "8 PM", "10 PM", "12 AM", "2 AM", "4 AM",
]

MONITORING_CHART_COLUMNS = [
    ("pulse", "Pulse"),
    ("bp", "BP"),
    ("temp", "Temp"),
    ("resp", "Resp"),
    ("cvp", "CVP"),
    ("spo2", "SPO2"),
    ("o2", "O2"),
    ("intake", "Intake"),
    ("output", "Output"),
    ("bsl", "BSL"),
    ("procedure", "Procedure"),
    ("nurse_sign", "Nurse Sign"),
]


class PrintNotFoundError(Exception):
    """Raised when a requested record/admission is not found within tenant scope."""


class PrintFormCodeError(Exception):
    """Raised when the requested ``form`` query/body param is not a registered code."""


# ---------------------------------------------------------------------------
# Letterhead
# ---------------------------------------------------------------------------


def get_letterhead_context(tenant_id: uuid.UUID, show_letterhead: bool) -> dict[str, Any]:
    """Build the letterhead dict for template rendering.

    Mirrors the JSON contract of ``GET /api/hospital/config/letterhead/``
    (``apps.hospital.views.HospitalLetterheadView``). That endpoint already
    exists and its serializer accepts either a tenant-configured
    ``Hospital.letterhead_config`` or a computed default from
    ``Hospital.get_default_letterhead_config()`` — this helper reuses that
    exact model method directly (no HTTP round-trip needed since we're
    already inside the Django process), so swapping to a network call to the
    live endpoint later is a one-line change if ever needed.
    """
    if not show_letterhead:
        return {"enabled": False}

    hospital = Hospital.objects.filter(tenant_id=tenant_id).first()
    if hospital is None:
        return {"enabled": False}

    config = hospital.letterhead_config or hospital.get_default_letterhead_config()
    text_lines = sorted(
        [line for line in (config.get("text_lines") or []) if line.get("enabled")],
        key=lambda line: line.get("order", 0),
    )
    return {
        "enabled": True,
        "show_logo": bool(config.get("show_logo")),
        "logo_url": config.get("logo_url") or "",
        "show_badge": bool(config.get("show_badge")),
        "badge_url": config.get("badge_url") or "",
        "alignment": config.get("alignment") or "left",
        "show_hairline": bool(config.get("show_hairline")),
        "text_lines": text_lines,
    }


# ---------------------------------------------------------------------------
# Record / admission resolution (tenant-scoped)
# ---------------------------------------------------------------------------


def _resolve_admission(tenant_id: uuid.UUID, record_id: int) -> Admission:
    """Fetch a tenant-scoped Admission by id for the admission_form print."""
    admission = (
        Admission.objects.filter(tenant_id=tenant_id, pk=record_id)
        .select_related("patient", "ward", "bed")
        .first()
    )
    if admission is None:
        raise PrintNotFoundError(f"Admission {record_id} not found for this tenant.")
    return admission


def _resolve_clinical_record(tenant_id: uuid.UUID, record_id: int) -> ClinicalRecord:
    """Fetch a tenant-scoped ClinicalRecord by id, with structure + values preloaded."""
    record = (
        ClinicalRecord.objects.filter(tenant_id=tenant_id, pk=record_id)
        .select_related("form")
        .prefetch_related("field_values__field", "field_values__picklist_item")
        .first()
    )
    if record is None:
        raise PrintNotFoundError(f"Clinical record {record_id} not found for this tenant.")
    return record


# ---------------------------------------------------------------------------
# Per-form context builders
# ---------------------------------------------------------------------------


def _admission_context(tenant_id: uuid.UUID, record_id: int) -> dict[str, Any]:
    """Build the template context for the Admission Form print."""
    admission = _resolve_admission(tenant_id, record_id)
    patient = admission.patient

    return {
        "admission": admission,
        "patient": patient,
        "uhid": patient.patient_id,
        "ipd_no": admission.admission_id,
        "patient_name": patient.full_name,
        "age": patient.age,
        "gender": patient.get_gender_display() if patient.gender else "",
        "contact": patient.mobile_primary,
        "address": patient.full_address,
        "guardian_name": " ".join(
            part
            for part in [patient.guardian_first_name, patient.guardian_last_name]
            if part
        ),
        "guardian_relation": patient.guardian_relation,
        "guardian_mobile": patient.guardian_mobile,
        "admission_date": admission.admission_date,
        "discharge_date": admission.discharge_date,
        "ward": admission.ward,
        "bed": admission.bed,
        "admission_type": admission.get_admission_type_display(),
        "reason": admission.reason,
        "provisional_diagnosis": admission.provisional_diagnosis,
        "final_diagnosis": admission.final_diagnosis,
        "status": admission.get_status_display(),
        "has_mediclaim": admission.has_mediclaim,
        "tpa_name": admission.tpa_name,
        "claim_status": admission.get_claim_status_display(),
        "bed_transfers": list(admission.bed_transfers.select_related("from_bed", "to_bed").order_by("transfer_date")),
        "is_mlc_case": "mlc" in (admission.reason or "").lower(),
    }


def _clinical_record_context(tenant_id: uuid.UUID, record_id: int, language: str) -> dict[str, Any]:
    """Build the shared context used by nursing paper / progress sheet / generic templates.

    All of these are ``ClinicalRecord`` instances (not dedicated Django
    models) — see investigation notes: nursing_initial_assessment,
    round_notes/progress_sheet and monitoring_chart are seeded ClinicalForm
    definitions (apps/clinical/seeds/catalog.py), not separate tables.
    """
    record = _resolve_clinical_record(tenant_id, record_id)
    structure = ClinicalFormStructureSerializer(record.form).data

    values_by_key: dict[str, ClinicalFieldValue] = {
        fv.field.field_key: fv for fv in record.field_values.all() if fv.is_active
    }

    def _plain_value(field_key: str) -> Any:
        fv = values_by_key.get(field_key)
        if fv is None:
            return None
        return _field_value_to_display(fv, language)

    sections = []
    for section in structure.get("sections", []):
        fields = []
        for field_data in section.get("section_fields", []):
            fv = values_by_key.get(field_data["field_key"])
            display_value = _field_value_to_display(fv, language) if fv else None
            fields.append({**field_data, "display_value": display_value})
        sections.append({**section, "section_fields": fields})

    encounter_type = record.encounter_type
    encounter_id = record.encounter_id
    admission = None
    patient = None
    if encounter_type == ClinicalForm.EntityType.IPD_ADMISSION:
        admission = Admission.objects.filter(tenant_id=tenant_id, pk=encounter_id).select_related("patient").first()
        patient = admission.patient if admission else None

    return {
        "record": record,
        "structure": structure,
        "sections": sections,
        "values": values_by_key,
        "get_value": _plain_value,
        "admission": admission,
        "patient": patient,
        "uhid": patient.patient_id if patient else "",
        "ipd_no": admission.admission_id if admission else "",
        "patient_name": patient.full_name if patient else "",
        "age": patient.age if patient else "",
        "gender": patient.get_gender_display() if patient and patient.gender else "",
        "consulting_doctor_ids": admission.consulting_doctor_ids if admission else [],
        "encounter_type": encounter_type,
        "encounter_id": encounter_id,
        "occurrence_index": record.occurrence_index,
        "language": language,
    }


def _field_value_to_display(field_value: ClinicalFieldValue, language: str) -> Any:
    """Return a human-displayable representation of a stored field value."""
    field_type = field_value.field.field_type
    if field_type == ClinicalFormField.FieldType.BOOLEAN:
        return "Yes" if field_value.value_boolean else ("No" if field_value.value_boolean is False else "")
    if field_type == ClinicalFormField.FieldType.NUMBER:
        return field_value.value_number
    if field_type == ClinicalFormField.FieldType.DATE:
        return field_value.value_date
    if field_type == ClinicalFormField.FieldType.DATETIME:
        return field_value.value_datetime
    if field_type == ClinicalFormField.FieldType.TIME:
        return field_value.value_time
    if field_type in (ClinicalFormField.FieldType.GRID, ClinicalFormField.FieldType.MULTISELECT):
        return field_value.value_json
    if field_value.picklist_item_id:
        item = field_value.picklist_item
        if language == "mr" and item.label_mr:
            return item.label_mr
        return item.label
    return field_value.value_text


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def build_print_context(
    form_code: str,
    tenant_id: uuid.UUID,
    record_id: int,
    letterhead: bool,
    language: str,
) -> tuple[str, dict[str, Any]]:
    """Resolve ``(template_name, context)`` for a single record of ``form_code``.

    Raises ``PrintFormCodeError`` for an unregistered form code and
    ``PrintNotFoundError`` if the record/admission does not exist for the
    tenant.
    """
    if form_code not in REGISTERED_FORM_CODES:
        raise PrintFormCodeError(f"Unknown print form code: {form_code!r}.")

    template_name = _TEMPLATE_BY_FORM_CODE[form_code]
    context: dict[str, Any] = {
        "letterhead": get_letterhead_context(tenant_id, letterhead),
        "language": language,
        "form_code": form_code,
    }

    if form_code == FORM_ADMISSION:
        context.update(_admission_context(tenant_id, record_id))
    elif form_code == FORM_MONITORING_CHART:
        context.update(_clinical_record_context(tenant_id, record_id, language))
        context["time_slots"] = MONITORING_CHART_TIME_SLOTS
        context["columns"] = MONITORING_CHART_COLUMNS
    else:
        # nursing_paper, progress_sheet, clinical_form all share the generic
        # ClinicalRecord-driven context; templates render different subsets.
        context.update(_clinical_record_context(tenant_id, record_id, language))

    return template_name, context


def render_print_html(form_code: str, tenant_id: uuid.UUID, record_id: int, letterhead: bool, language: str) -> str:
    """Render a single record's print template to an HTML string."""
    template_name, context = build_print_context(form_code, tenant_id, record_id, letterhead, language)
    return render_to_string(template_name, context)


def render_batch_html(
    form_code: str,
    tenant_id: uuid.UUID,
    record_ids: list[int],
    letterhead: bool,
    language: str,
) -> str:
    """Render many records of the same ``form_code`` into one HTML document.

    Each record's body is wrapped in a container with
    ``page-break-before: always`` (except the first) so WeasyPrint paginates
    them as separate pages in a single PDF. The letterhead renders on every
    page because it lives inside each per-record template, not hoisted out.
    """
    if form_code not in REGISTERED_FORM_CODES:
        raise PrintFormCodeError(f"Unknown print form code: {form_code!r}.")

    pages = []
    for index, record_id in enumerate(record_ids):
        template_name, context = build_print_context(form_code, tenant_id, record_id, letterhead, language)
        context["is_batch"] = True
        context["page_break_before"] = index > 0
        pages.append(render_to_string(template_name, context))

    return "\n".join(pages)


def render_pdf_from_html(html: str) -> bytes:
    """Convert an HTML string to PDF bytes using WeasyPrint.

    Imported lazily so the rest of this module (and the view layer's error
    handling / URL wiring) can be exercised without WeasyPrint's native
    dependencies (Pango/Cairo) being installed in every environment.
    """
    from weasyprint import HTML

    return HTML(string=html).write_pdf()
