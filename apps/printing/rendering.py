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
    ClinicalDocumentTemplate,
    ClinicalFieldValue,
    ClinicalForm,
    ClinicalFormField,
    ClinicalPrintTemplate,
    ClinicalRecord,
)
from apps.clinical.serializers import ClinicalFormStructureSerializer
from apps.hospital.models import Hospital
from apps.ipd.models import Admission, IPDBilling
from apps.opd.models import OPDBill, Visit

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
FORM_OPD_VISIT = "opd_visit_form"
FORM_IPD_BILL = "ipd_bill"
FORM_OPD_BILL = "opd_bill"

REGISTERED_FORM_CODES = {
    FORM_ADMISSION,
    FORM_NURSING_PAPER,
    FORM_MONITORING_CHART,
    FORM_PROGRESS_SHEET,
    FORM_CLINICAL_GENERIC,
    FORM_OPD_VISIT,
    FORM_IPD_BILL,
    FORM_OPD_BILL,
}

CLINICAL_RECORD_FORM_CODES = {
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
    FORM_OPD_VISIT: "print/opd_visit_form.html",
    FORM_IPD_BILL: "print/ipd_bill.html",
    FORM_OPD_BILL: "print/opd_bill.html",
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


class PdfMergeError(Exception):
    """Raised when a rendered document cannot be safely merged.

    ``document_index`` is zero-based and lets the API identify the selected
    document that failed without exposing parser/native-library internals.
    """

    def __init__(self, message: str, *, document_index: int | None = None):
        super().__init__(message)
        self.document_index = document_index


def resolve_print_form_code(form_code: str, tenant_id: uuid.UUID | None = None) -> str:
    """Resolve a client-supplied print/form code to a registered print code."""
    normalized = (form_code or "").strip()
    if normalized in REGISTERED_FORM_CODES:
        return normalized

    if tenant_id is not None:
        form = (
            ClinicalForm.objects.filter(
                tenant_id__in=[tenant_id, _SYSTEM_TENANT_ID],
                code=normalized,
                is_active=True,
            )
            .only("print_template_code")
            .first()
        )
        if form and form.print_template_code in CLINICAL_RECORD_FORM_CODES:
            return form.print_template_code

    raise PrintFormCodeError(f"Unknown print form code: {form_code!r}.")


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
    right_column_lines = sorted(
        [line for line in (config.get("right_column_lines") or []) if line.get("enabled")],
        key=lambda line: line.get("order", 0),
    )
    info_bar = config.get("info_bar") or {
        "enabled": False,
        "background_color": "#1e3a5f",
        "text_color": "#ffffff",
        "lines": [],
    }
    return {
        "enabled": True,
        "show_logo": bool(config.get("show_logo")),
        "logo_url": config.get("logo_url") or "",
        "show_badge": bool(config.get("show_badge")),
        "badge_url": config.get("badge_url") or "",
        "alignment": config.get("alignment") or "left",
        "show_hairline": bool(config.get("show_hairline")),
        "text_lines": text_lines,
        "layout_mode": config.get("layout_mode") or "simple",
        "right_column_lines": right_column_lines,
        "background_pattern_url": config.get("background_pattern_url"),
        "info_bar": info_bar,
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


def _resolve_visit(tenant_id: uuid.UUID, record_id: int) -> Visit:
    """Fetch a tenant-scoped Visit by id for the opd_visit_form print."""
    visit = (
        Visit.objects.filter(tenant_id=tenant_id, pk=record_id)
        .select_related("patient", "doctor", "referred_by")
        .first()
    )
    if visit is None:
        raise PrintNotFoundError(f"Visit {record_id} not found for this tenant.")
    return visit


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


def _resolve_ipd_bill(tenant_id: uuid.UUID, record_id: int) -> IPDBilling:
    """Fetch a tenant-scoped IPDBilling by id for the ipd_bill print, 404 if not found/wrong tenant."""
    bill = (
        IPDBilling.objects.filter(tenant_id=tenant_id, pk=record_id)
        .select_related("admission", "admission__patient", "admission__ward", "admission__bed")
        .prefetch_related("items")
        .first()
    )
    if bill is None:
        raise PrintNotFoundError(f"IPD bill {record_id} not found for this tenant.")
    return bill


def _resolve_opd_bill(tenant_id: uuid.UUID, record_id: int) -> OPDBill:
    """Fetch a tenant-scoped OPDBill by id for the opd_bill print, 404 if not found/wrong tenant."""
    bill = (
        OPDBill.objects.filter(tenant_id=tenant_id, pk=record_id)
        .select_related("visit", "visit__patient", "visit__doctor", "doctor")
        .prefetch_related("items")
        .first()
    )
    if bill is None:
        raise PrintNotFoundError(f"OPD bill {record_id} not found for this tenant.")
    return bill


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


def _ipd_bill_context(tenant_id: uuid.UUID, record_id: int) -> dict[str, Any]:
    """Build the template context for the IPD Bill print.

    Mirrors how _admission_context pulls letterhead/patient/admission data —
    the letterhead itself is added once in build_print_context() via
    get_letterhead_context(), not here.
    """
    bill = _resolve_ipd_bill(tenant_id, record_id)
    admission = bill.admission
    patient = admission.patient
    items = list(bill.items.all().order_by('source', 'id'))

    return {
        "bill": bill,
        "items": items,
        "admission": admission,
        "patient": patient,
        "uhid": patient.patient_id,
        "ipd_no": admission.admission_id,
        "patient_name": patient.full_name,
        "age": patient.age,
        "gender": patient.get_gender_display() if patient.gender else "",
        "contact": patient.mobile_primary,
        "address": patient.full_address,
        "admission_date": admission.admission_date,
        "discharge_date": admission.discharge_date,
        "ward": admission.ward,
        "bed": admission.bed,
        "bill_number": bill.bill_number,
        "bill_date": bill.bill_date,
        "diagnosis": bill.diagnosis,
        "remarks": bill.remarks,
        "total_amount": bill.total_amount,
        "discount_percent": bill.discount_percent,
        "discount_amount": bill.discount_amount,
        "payable_amount": bill.payable_amount,
        "received_amount": bill.received_amount,
        "balance_amount": bill.balance_amount,
        "payment_status": bill.get_payment_status_display(),
        "payment_mode": bill.get_payment_mode_display(),
    }


def _opd_bill_context(tenant_id: uuid.UUID, record_id: int) -> dict[str, Any]:
    """Build the template context for the OPD Bill print.

    Mirrors _ipd_bill_context field-for-field where the models overlap so the
    opd_bill.html template can share the same structure/CSS classes as
    ipd_bill.html — the letterhead itself is added once in
    build_print_context() via get_letterhead_context(), not here.
    """
    bill = _resolve_opd_bill(tenant_id, record_id)
    visit = bill.visit
    patient = visit.patient
    doctor = bill.doctor or visit.doctor
    items = list(bill.items.all().order_by("source", "id"))

    return {
        "bill": bill,
        "items": items,
        "visit": visit,
        "patient": patient,
        "uhid": patient.patient_id,
        "opd_no": visit.visit_number,
        "patient_name": patient.full_name,
        "age": patient.age,
        "gender": patient.get_gender_display() if patient.gender else "",
        "contact": patient.mobile_primary,
        "address": patient.full_address,
        "visit_date": visit.visit_date,
        "visit_type": visit.get_visit_type_display(),
        "doctor": doctor,
        "doctor_name": doctor.full_name if doctor else "",
        "bill_number": bill.bill_number,
        "bill_date": bill.bill_date,
        "opd_type": bill.get_opd_type_display(),
        "charge_type": bill.get_charge_type_display(),
        "diagnosis": bill.diagnosis,
        "remarks": bill.remarks,
        "total_amount": bill.total_amount,
        "discount_percent": bill.discount_percent,
        "discount_amount": bill.discount_amount,
        "payable_amount": bill.payable_amount,
        "received_amount": bill.received_amount,
        "balance_amount": bill.balance_amount,
        "payment_status": bill.get_payment_status_display(),
        "payment_mode": bill.get_payment_mode_display(),
    }


def _opd_visit_context(tenant_id: uuid.UUID, record_id: int) -> dict[str, Any]:
    """Build the template context for the OPD Visit Form print."""
    visit = _resolve_visit(tenant_id, record_id)
    patient = visit.patient

    return {
        "visit": visit,
        "patient": patient,
        "uhid": patient.patient_id,
        "opd_no": visit.visit_number,
        "patient_name": patient.full_name,
        "age": patient.age,
        "gender": patient.get_gender_display() if patient.gender else "",
        "contact": patient.mobile_primary,
        "address": patient.full_address,
        "blood_group": patient.blood_group,
        "guardian_name": " ".join(
            part
            for part in [patient.guardian_first_name, patient.guardian_last_name]
            if part
        ),
        "guardian_relation": patient.guardian_relation,
        "guardian_mobile": patient.guardian_mobile,
        "visit_date": visit.visit_date,
        "entry_time": visit.entry_time,
        "visit_type": visit.get_visit_type_display(),
        "priority": visit.get_priority_display(),
        "status": visit.get_status_display(),
        "doctor": visit.doctor,
        "doctor_name": visit.doctor.full_name if visit.doctor else "",
        "referred_by_name": visit.referred_by.full_name if visit.referred_by else "",
        "notify_referring_doctor": visit.notify_referring_doctor,
        "is_follow_up": visit.is_follow_up,
        "follow_up_required": visit.follow_up_required,
        "follow_up_date": visit.follow_up_date,
        "follow_up_notes": visit.follow_up_notes,
        "queue_position": visit.queue_position,
        "consultation_start_time": visit.consultation_start_time,
        "consultation_end_time": visit.consultation_end_time,
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
    form_code = resolve_print_form_code(form_code, tenant_id)

    template_name = _TEMPLATE_BY_FORM_CODE[form_code]
    context: dict[str, Any] = {
        "letterhead": get_letterhead_context(tenant_id, letterhead),
        "language": language,
        "form_code": form_code,
    }

    if form_code == FORM_ADMISSION:
        context.update(_admission_context(tenant_id, record_id))
    elif form_code == FORM_OPD_VISIT:
        context.update(_opd_visit_context(tenant_id, record_id))
    elif form_code == FORM_IPD_BILL:
        context.update(_ipd_bill_context(tenant_id, record_id))
    elif form_code == FORM_OPD_BILL:
        context.update(_opd_bill_context(tenant_id, record_id))
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
    form_code = resolve_print_form_code(form_code, tenant_id)

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


# ---------------------------------------------------------------------------
# Consent / stationery / certificate document batch print
# ---------------------------------------------------------------------------
#
# Unlike the registered *form* codes above (which are backed by a specific
# Django model + a dedicated print template), consent/stationery/certificate
# documents are tenant-authored ``ClinicalDocumentTemplate`` rows. Their print
# HTML - when the tenant has authored one - lives in a matching
# ``ClinicalPrintTemplate`` (target_type='document', target_code=<doc code>).
# When no authored HTML exists we fall back to a generic, letterhead-aware
# stationery page so batch print is always robust and never hard-fails just
# because a template body has not been designed yet.
#
# Each selected document is rendered to its OWN PDF and the PDFs are then
# merged with pypdf into a single file (a "proper" page-accurate merge that
# preserves each document's own @page rules), rather than concatenating raw
# HTML.

DOCUMENT_GENERIC_TEMPLATE = "print/document_generic.html"

# encounter_type values (as sent by the frontend) the document batch supports.
DOCUMENT_ENCOUNTER_TYPES = {"ipd_admission", "opd_visit"}

MAX_DOCUMENT_BATCH_SIZE = 100


def _document_encounter_context(
    tenant_id: uuid.UUID, encounter_type: str, encounter_id: int
) -> dict[str, Any]:
    """Resolve the patient/encounter header context for a document print.

    Tenant-scoped (never trusts client identifiers). Supports the two encounter
    types the Consents & Stationery UI targets: IPD admissions and OPD visits.
    """
    if encounter_type == "ipd_admission":
        admission = _resolve_admission(tenant_id, encounter_id)
        patient = admission.patient
        return {
            "encounter_label": "IPD",
            "encounter_no": admission.admission_id,
            "patient": patient,
            "uhid": patient.patient_id,
            "patient_name": patient.full_name,
            "age": patient.age,
            "gender": patient.get_gender_display() if patient.gender else "",
            "contact": patient.mobile_primary,
            "address": patient.full_address,
            "ward": admission.ward,
            "bed": admission.bed,
            "encounter_date": admission.admission_date,
        }
    if encounter_type == "opd_visit":
        visit = _resolve_visit(tenant_id, encounter_id)
        patient = visit.patient
        return {
            "encounter_label": "OPD",
            "encounter_no": visit.visit_number,
            "patient": patient,
            "uhid": patient.patient_id,
            "patient_name": patient.full_name,
            "age": patient.age,
            "gender": patient.get_gender_display() if patient.gender else "",
            "contact": patient.mobile_primary,
            "address": patient.full_address,
            "ward": None,
            "bed": None,
            "encounter_date": visit.visit_date,
        }
    raise PrintFormCodeError(
        f"Unsupported encounter_type for documents: {encounter_type!r}. "
        f"Expected one of {sorted(DOCUMENT_ENCOUNTER_TYPES)}."
    )


def _resolve_document_template(tenant_id: uuid.UUID, code: str) -> ClinicalDocumentTemplate:
    """Fetch a tenant-scoped, active document template by code (404 otherwise)."""
    tpl = ClinicalDocumentTemplate.objects.filter(
        tenant_id=tenant_id, code=code, is_active=True
    ).first()
    if tpl is None:
        raise PrintNotFoundError(f"Document template {code!r} not found for this tenant.")
    return tpl


def _resolve_document_html(
    tenant_id: uuid.UUID, code: str, layout: str, language: str
) -> str | None:
    """Return authored ClinicalPrintTemplate HTML for a document code, if any.

    Prefers an exact language+layout match, then language, then layout, then
    any active row. Returns ``None`` when no non-empty authored HTML exists so
    the caller can fall back to the generic stationery template.
    """
    base = ClinicalPrintTemplate.objects.filter(
        tenant_id=tenant_id,
        target_type=ClinicalPrintTemplate.TargetType.DOCUMENT,
        target_code=code,
        is_active=True,
    )
    for extra_filter in (
        {"language": language, "layout": layout},
        {"language": language},
        {"layout": layout},
        {},
    ):
        tpl = base.filter(**extra_filter).order_by("id").first()
        if tpl and (tpl.html or "").strip():
            return tpl.html
    return None


def render_document_html(
    tenant_id: uuid.UUID,
    code: str,
    encounter_type: str,
    encounter_id: int,
    letterhead: bool,
    language: str,
) -> str:
    """Render one consent/stationery/certificate document to an HTML string."""
    doc = _resolve_document_template(tenant_id, code)
    layout = "letterhead" if letterhead else "blank"
    context: dict[str, Any] = {
        "letterhead": get_letterhead_context(tenant_id, letterhead),
        "language": language,
        "document": doc,
        "document_title": doc.name,
        "document_code": doc.code,
        "doc_type": doc.get_doc_type_display(),
        "requires_signature": doc.requires_signature,
        "page_break_before": False,
        **_document_encounter_context(tenant_id, encounter_type, encounter_id),
    }

    authored_html = _resolve_document_html(tenant_id, code, layout, language)
    if authored_html is not None:
        # Authored templates are rendered through Django's template engine so
        # they can use the same {{ patient_name }} / {{ uhid }} placeholders.
        from django.template import Context, Template

        return Template(authored_html).render(Context(context))

    return render_to_string(DOCUMENT_GENERIC_TEMPLATE, context)


def render_document_pdf(
    tenant_id: uuid.UUID,
    code: str,
    encounter_type: str,
    encounter_id: int,
    letterhead: bool,
    language: str,
) -> bytes:
    """Render one document to PDF bytes."""
    html = render_document_html(
        tenant_id, code, encounter_type, encounter_id, letterhead, language
    )
    return render_pdf_from_html(html)


A4_WIDTH_POINTS = 595.275591
A4_HEIGHT_POINTS = 841.889764
_A4_TOLERANCE_POINTS = 1.0


def _page_as_a4(page: Any) -> Any:
    """Return ``page`` on an A4 portrait canvas, preserving aspect ratio.

    WeasyPrint templates normally already emit A4 pages, in which case the
    original page object is returned untouched (preserving links/annotations).
    Tenant-authored HTML can declare another page size, so non-A4 pages are
    scaled to fit and centred rather than leaving a mixed-size merged file.
    """
    from pypdf import PageObject, Transformation

    if page.rotation:
        page.transfer_rotation_to_content()

    box = page.mediabox
    width = float(box.width)
    height = float(box.height)
    left = float(box.left)
    bottom = float(box.bottom)
    if width <= 0 or height <= 0:
        raise ValueError("page has a zero or negative media box")

    is_a4 = (
        abs(width - A4_WIDTH_POINTS) <= _A4_TOLERANCE_POINTS
        and abs(height - A4_HEIGHT_POINTS) <= _A4_TOLERANCE_POINTS
        and abs(left) <= _A4_TOLERANCE_POINTS
        and abs(bottom) <= _A4_TOLERANCE_POINTS
    )
    if is_a4:
        return page

    scale = min(A4_WIDTH_POINTS / width, A4_HEIGHT_POINTS / height)
    x_offset = (A4_WIDTH_POINTS - width * scale) / 2 - left * scale
    y_offset = (A4_HEIGHT_POINTS - height * scale) / 2 - bottom * scale
    transform = Transformation().scale(scale).translate(x_offset, y_offset)
    a4_page = PageObject.create_blank_page(
        width=A4_WIDTH_POINTS,
        height=A4_HEIGHT_POINTS,
    )
    a4_page.merge_transformed_page(page, transform, expand=False)
    return a4_page


def merge_pdfs(pdfs: list[bytes]) -> bytes:
    """Validate and merge PDF byte-strings into one A4 document.

    Page and document order are preserved. Invalid, encrypted, or zero-page
    inputs fail closed with the source document index instead of producing a
    corrupt output that only fails later in the browser PDF viewer.
    """
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter

    if not pdfs:
        raise PdfMergeError("At least one rendered PDF is required for merging.")

    writer = PdfWriter()
    expected_page_count = 0
    for index, pdf in enumerate(pdfs):
        try:
            if not isinstance(pdf, bytes) or not pdf:
                raise ValueError("rendered PDF is empty")
            reader = PdfReader(BytesIO(pdf), strict=True)
            if reader.is_encrypted and not reader.decrypt(""):
                raise ValueError("rendered PDF is password-protected")
            if not reader.pages:
                raise ValueError("rendered PDF contains no pages")
            for page in reader.pages:
                writer.add_page(_page_as_a4(page))
                expected_page_count += 1
        except PdfMergeError:
            raise
        except Exception as exc:
            raise PdfMergeError(
                f"Rendered document {index + 1} is not a mergeable PDF: {exc}",
                document_index=index,
            ) from exc

    buffer = BytesIO()
    try:
        writer.write(buffer)
        merged = buffer.getvalue()
        result = PdfReader(BytesIO(merged), strict=True)
        if len(result.pages) != expected_page_count:
            raise ValueError(
                f"expected {expected_page_count} pages, wrote {len(result.pages)}"
            )
    except Exception as exc:
        raise PdfMergeError(f"Merged PDF validation failed: {exc}") from exc

    return merged


def render_document_batch_pdf(
    tenant_id: uuid.UUID,
    template_codes: list[str],
    encounter_type: str,
    encounter_id: int,
    letterhead: bool,
    language: str,
) -> bytes:
    """Render each selected document to its own PDF, then merge into one.

    Order is preserved (documents print in the order the codes are supplied).
    Single-document batches also pass through ``merge_pdfs`` so validation and
    A4 normalization are identical for every response size.
    """
    if encounter_type not in DOCUMENT_ENCOUNTER_TYPES:
        raise PrintFormCodeError(
            f"Unsupported encounter_type for documents: {encounter_type!r}. "
            f"Expected one of {sorted(DOCUMENT_ENCOUNTER_TYPES)}."
        )

    pdfs = []
    for index, code in enumerate(template_codes):
        try:
            pdfs.append(
                render_document_pdf(
                    tenant_id,
                    code,
                    encounter_type,
                    encounter_id,
                    letterhead,
                    language,
                )
            )
        except (PrintFormCodeError, PrintNotFoundError):
            raise
        except Exception as exc:
            raise PdfMergeError(
                f"Document {code!r} could not be rendered: {exc}",
                document_index=index,
            ) from exc
    return merge_pdfs(pdfs)
