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

import os
import uuid
from decimal import Decimal
from pathlib import Path
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
from apps.doctors.models import DoctorProfile
from apps.hospital.models import Hospital
from apps.hospital.serializers import with_letterhead_defaults
from apps.ipd.models import Admission, DischargePacket, IPDBilling
from apps.ipd.services.discharge import collect_discharge_sections
from apps.opd.models import OPDBill, Visit
from apps.payments.models import BillPayment

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
FORM_JEEVISHA_PAIN_OPD = "jeevisha_pain_opd"
FORM_OPD_VISIT = "opd_visit_form"
FORM_IPD_BILL = "ipd_bill"
FORM_OPD_BILL = "opd_bill"
FORM_OPD_PAYMENT_RECEIPT = "opd_payment_receipt"
FORM_IPD_PAYMENT_RECEIPT = "ipd_payment_receipt"
FORM_DISCHARGE_SUMMARY = "discharge_summary"
FORM_IPD_ADMISSION_STATEMENT = "ipd_admission_statement"

REGISTERED_FORM_CODES = {
    FORM_ADMISSION,
    FORM_NURSING_PAPER,
    FORM_MONITORING_CHART,
    FORM_PROGRESS_SHEET,
    FORM_CLINICAL_GENERIC,
    FORM_JEEVISHA_PAIN_OPD,
    FORM_OPD_VISIT,
    FORM_IPD_BILL,
    FORM_OPD_BILL,
    FORM_OPD_PAYMENT_RECEIPT,
    FORM_IPD_PAYMENT_RECEIPT,
    FORM_DISCHARGE_SUMMARY,
    FORM_IPD_ADMISSION_STATEMENT,
}

# Form codes whose record_id is a BillPayment.payment_group_id (a UUID)
# rather than an integer bill/admission/record pk.
UUID_RECORD_ID_FORM_CODES = {
    FORM_OPD_PAYMENT_RECEIPT,
    FORM_IPD_PAYMENT_RECEIPT,
}

CLINICAL_RECORD_FORM_CODES = {
    FORM_NURSING_PAPER,
    FORM_MONITORING_CHART,
    FORM_PROGRESS_SHEET,
    FORM_CLINICAL_GENERIC,
    FORM_JEEVISHA_PAIN_OPD,
}

# Template used for each registered form code.
_TEMPLATE_BY_FORM_CODE = {
    FORM_ADMISSION: "print/admission_form.html",
    FORM_NURSING_PAPER: "print/ipd_nursing_paper.html",
    FORM_MONITORING_CHART: "print/monitoring_chart.html",
    FORM_PROGRESS_SHEET: "print/progress_sheet.html",
    FORM_CLINICAL_GENERIC: "print/clinical_form_generic.html",
    FORM_JEEVISHA_PAIN_OPD: "print/jeevisha_pain_opd.html",
    FORM_OPD_VISIT: "print/opd_visit_form.html",
    FORM_IPD_BILL: "print/ipd_bill.html",
    FORM_OPD_BILL: "print/opd_bill.html",
    FORM_OPD_PAYMENT_RECEIPT: "print/opd_payment_receipt.html",
    FORM_IPD_PAYMENT_RECEIPT: "print/ipd_payment_receipt.html",
    FORM_DISCHARGE_SUMMARY: "print/discharge_summary.html",
    FORM_IPD_ADMISSION_STATEMENT: "print/ipd_admission_statement.html",
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

    config = with_letterhead_defaults(
        hospital.letterhead_config or hospital.get_default_letterhead_config()
    )
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
        "left_image": config["left_image"],
        "right_image": config["right_image"],
        "alignment": config.get("alignment") or "left",
        "show_hairline": bool(config.get("show_hairline")),
        "text_lines": text_lines,
        "layout_mode": config.get("layout_mode") or "simple",
        "right_column_lines": right_column_lines,
        "right_column_align": config.get("right_column_align", "right"),
        "background_pattern_url": config.get("background_pattern_url"),
        "background_pattern_opacity": config.get("background_pattern_opacity", 1.0),
        "body_watermark": config.get("body_watermark")
        or {"enabled": False, "url": "", "size_pct": 45, "opacity": 0.10},
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


def _resolve_payment_group(
    tenant_id: uuid.UUID, bill_types: tuple[str, ...], group_id: Any
) -> list[BillPayment]:
    """Fetch every BillPayment row recorded together as one payment event.

    ``group_id`` is normally a ``payment_group_id`` shared by every leg of one
    payment (e.g. the cash + online rows of a split payment). Rows created
    before ``payment_group_id`` existed have it null, so as a fallback this
    also accepts a single BillPayment's own ``id`` and returns just that row.
    """
    payments = list(
        BillPayment.objects.filter(
            tenant_id=tenant_id, bill_type__in=bill_types, payment_group_id=group_id
        )
        .select_related("opd_bill", "ipd_bill")
        .order_by("payment_mode")
    )
    if not payments:
        single = (
            BillPayment.objects.filter(tenant_id=tenant_id, bill_type__in=bill_types, pk=group_id)
            .select_related("opd_bill", "ipd_bill")
            .first()
        )
        if single is not None:
            payments = [single]
    if not payments:
        raise PrintNotFoundError(f"Payment {group_id} not found for this tenant.")
    return payments


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


def _print_safe_field_value(value: Any) -> Any:
    """Format a discharge-section field value for direct template display.

    ``collect_discharge_sections()`` returns raw JSON-safe values (used by
    both the AI narrative prompt and the in-app review API) — a multiselect
    is a Python list, not a display string. Rendering a list directly with
    ``{{ field.value }}`` would print its repr, and applying Django's
    ``|join`` filter unconditionally would incorrectly iterate a plain
    string's characters. Grid-shaped dicts (``{"columns": ..., "rows": ...}``)
    are left untouched — the template branches on those explicitly.
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return value


def _discharge_summary_context(tenant_id: uuid.UUID, record_id: int, include_sections: bool) -> dict[str, Any]:
    """Build the template context for the combined Discharge Summary print.

    ``record_id`` is an Admission id here (this form has no single backing
    ClinicalRecord). Reuses the exact "approved snapshot else collect fresh"
    rule apps.ipd.views.AdmissionViewSet._discharge_packet_data already uses
    for the in-app review API, so the printed document always matches what
    was reviewed/approved — no drift between the two.
    """
    admission = _resolve_admission(tenant_id, record_id)
    patient = admission.patient

    # Admission has no `doctor` FK — doctor_id is a raw SuperAdmin User ID
    # (per CLAUDE.md's "no local User model" rule). Resolve the display name
    # through DoctorProfile.user_id, tenant-scoped.
    doctor = DoctorProfile.objects.filter(tenant_id=tenant_id, user_id=admission.doctor_id).first()

    packet = DischargePacket.objects.filter(tenant_id=tenant_id, admission=admission).first()
    narrative = packet.narrative if packet else ""

    if packet and packet.status == "approved" and packet.sections_snapshot:
        raw_sections = packet.sections_snapshot
    else:
        raw_sections, _ = collect_discharge_sections(admission)

    sections = [
        {
            **section,
            "values": [
                {**field, "value": _print_safe_field_value(field.get("value"))}
                for field in section.get("values", [])
            ],
        }
        for section in raw_sections
    ] if include_sections else []

    return {
        "admission": admission,
        "patient": patient,
        "uhid": patient.patient_id,
        "ipd_no": admission.admission_id,
        "patient_name": patient.full_name,
        "age": patient.age,
        "gender": patient.get_gender_display() if patient.gender else "",
        "contact": patient.mobile_primary,
        "admission_date": admission.admission_date,
        "discharge_date": admission.discharge_date,
        "admission_type": admission.get_admission_type_display(),
        "reason": admission.reason,
        "provisional_diagnosis": admission.provisional_diagnosis,
        "final_diagnosis": admission.final_diagnosis,
        "doctor_name": doctor.full_name if doctor else None,
        "narrative": narrative,
        "sections": sections,
        "include_sections": include_sections,
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
        # A Mediclaim bill is a claim copy for the TPA/insurer: the template
        # shows the insurer name + a signature block for the patient/relative
        # and hides paid/balance amounts (see templates/print/ipd_bill.html).
        "bill_type": bill.bill_type,
        "is_mediclaim_bill": bill.bill_type == "mediclaim",
        "tpa_name": admission.tpa_name,
        "claim_status": admission.get_claim_status_display(),
        "claim_reference_number": admission.claim_reference_number,
    }


def _admission_statement_context(tenant_id: uuid.UUID, record_id: int) -> dict[str, Any]:
    """Build the template context for the consolidated IPD Admission Statement.

    Aggregates every non-mediclaim IPDBilling row for the admission into one
    printable document — grand total, total received, advance applied, net
    balance, and a per-bill breakdown. Mirrors _ipd_bill_context's
    patient/admission field set so the statement template can share the same
    layout/CSS classes as ipd_bill.html. In single_accumulated mode there is
    at most one such bill, so this naturally degenerates to showing that one
    bill — no special-casing needed.
    """
    admission = _resolve_admission(tenant_id, record_id)
    patient = admission.patient
    bills = list(
        IPDBilling.objects.filter(tenant_id=tenant_id, admission=admission)
        .exclude(bill_type='mediclaim')
        .prefetch_related('items')
        .order_by('bill_date', 'id')
    )

    grand_total = sum((bill.payable_amount for bill in bills), Decimal("0.00"))
    # bill.received_amount already includes any advance applied to that bill
    # (apply_advance writes it there directly) — total_received must NOT add
    # advance_applied again on top, or applied-advance money gets counted
    # twice. advance_applied is surfaced separately below purely as a memo
    # line item (mirrors Admission.recompute_billing_rollup()'s formula).
    total_received = sum((bill.received_amount for bill in bills), Decimal("0.00"))
    advance_applied = admission.advance_applied or Decimal("0.00")
    net_balance = grand_total - total_received

    return {
        "admission": admission,
        "bills": bills,
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
        "grand_total": grand_total,
        "advance_applied": advance_applied,
        "total_received": total_received,
        "net_balance": net_balance,
        "total_advance_paid": admission.total_advance_paid or Decimal("0.00"),
        "advance_balance": admission.advance_balance or Decimal("0.00"),
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


def _opd_payment_receipt_context(tenant_id: uuid.UUID, record_id: Any) -> dict[str, Any]:
    """Build the template context for one OPD payment-event receipt.

    ``record_id`` is a payment_group_id (or a bare BillPayment id for legacy
    rows recorded before grouping existed) — see _resolve_payment_group.
    Reuses _opd_bill_context for the patient/visit/item breakdown so the
    receipt lists the same charges as the full bill print, then overlays the
    specific payment(s) this receipt covers.
    """
    payments = _resolve_payment_group(tenant_id, ("opd",), record_id)
    bill = payments[0].opd_bill
    if bill is None:
        raise PrintNotFoundError(f"Bill for payment {record_id} not found for this tenant.")

    context = _opd_bill_context(tenant_id, bill.pk)
    receipt_total = sum((p.amount for p in payments), Decimal("0.00"))
    context.update({
        "payments": payments,
        "receipt_number": next((p.receipt_number for p in payments if p.receipt_number), str(record_id)),
        "receipt_date": payments[0].payment_date,
        "receipt_total": receipt_total,
        "received_before_this_payment": context["received_amount"] - receipt_total,
    })
    return context


def _ipd_payment_receipt_context(tenant_id: uuid.UUID, record_id: Any) -> dict[str, Any]:
    """Build the template context for one IPD/Daycare payment-event receipt.

    ``record_id`` is a payment_group_id (or a bare BillPayment id for legacy
    rows recorded before grouping existed) — see _resolve_payment_group.
    Reuses _ipd_bill_context for the patient/admission/item breakdown so the
    receipt lists the same charges as the full bill print, then overlays the
    specific payment(s) this receipt covers.
    """
    payments = _resolve_payment_group(tenant_id, ("ipd", "daycare"), record_id)
    bill = payments[0].ipd_bill
    if bill is None:
        raise PrintNotFoundError(f"Bill for payment {record_id} not found for this tenant.")

    context = _ipd_bill_context(tenant_id, bill.pk)
    receipt_total = sum((p.amount for p in payments), Decimal("0.00"))
    context.update({
        "payments": payments,
        "receipt_number": next((p.receipt_number for p in payments if p.receipt_number), str(record_id)),
        "receipt_date": payments[0].payment_date,
        "receipt_total": receipt_total,
        "received_before_this_payment": context["received_amount"] - receipt_total,
        "is_daycare": bill.admission.admission_type == "daycare" if bill.admission else False,
    })
    return context


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
    fields_by_key: dict[str, dict[str, Any]] = {}
    for section in structure.get("sections", []):
        fields = []
        for field_data in section.get("section_fields", []):
            fv = values_by_key.get(field_data["field_key"])
            raw_value = _field_value_to_display(fv, language) if fv else None
            display_value = _format_print_display(field_data, raw_value)
            print_field = {**field_data, "display_value": display_value, "raw_value": raw_value}
            if field_data.get("field_type") == ClinicalFormField.FieldType.MULTISELECT:
                print_field["checklist_options"] = _format_checklist_options(field_data, raw_value)
            if field_data.get("field_type") == ClinicalFormField.FieldType.BODY_DIAGRAM:
                pins = raw_value if isinstance(raw_value, (list, tuple)) else []
                print_field["front_pins"] = [
                    pin for pin in pins if isinstance(pin, dict) and pin.get("view") == "front"
                ]
                print_field["back_pins"] = [
                    pin for pin in pins if isinstance(pin, dict) and pin.get("view") == "back"
                ]
            fields.append(print_field)
            fields_by_key[field_data["field_key"]] = print_field
        sections.append({**section, "section_fields": fields})

    encounter_type = record.encounter_type
    encounter_id = record.encounter_id
    admission = None
    visit = None
    patient = None
    if encounter_type == ClinicalForm.EntityType.IPD_ADMISSION:
        admission = Admission.objects.filter(tenant_id=tenant_id, pk=encounter_id).select_related("patient").first()
        patient = admission.patient if admission else None
    elif encounter_type == ClinicalForm.EntityType.OPD_VISIT:
        visit = Visit.objects.filter(tenant_id=tenant_id, pk=encounter_id).select_related("patient").first()
        patient = visit.patient if visit else None

    return {
        "record": record,
        "structure": structure,
        "sections": sections,
        "fields_by_key": fields_by_key,
        "values": values_by_key,
        "get_value": _plain_value,
        "admission": admission,
        "visit": visit,
        "patient": patient,
        "uhid": patient.patient_id if patient else "",
        "ipd_no": admission.admission_id if admission else (visit.visit_number if visit else ""),
        "patient_name": patient.full_name if patient else "",
        "age": patient.age if patient and patient.age is not None else "",
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
    if field_type == ClinicalFormField.FieldType.GRID:
        # Grid keeps its list-of-rows shape; the template renders it as a table.
        return field_value.value_json
    if field_type in (
        ClinicalFormField.FieldType.MULTISELECT,
        ClinicalFormField.FieldType.BODY_DIAGRAM,
    ):
        # Composite values are stored as JSON. Fall back to text for legacy rows
        # that predate JSON persistence (so nothing is silently dropped).
        return (
            field_value.value_json
            if field_value.value_json is not None
            else field_value.value_text
        )
    if field_value.picklist_item_id:
        item = field_value.picklist_item
        if language == "mr" and item.label_mr:
            return item.label_mr
        return item.label
    # Prefer structured JSON when only a placeholder/blank text was persisted
    # for a composite value (legacy rows saved before the client stored JSON).
    if field_value.value_json is not None and (
        field_value.value_text is None or _is_object_placeholder(field_value.value_text)
    ):
        return field_value.value_json
    return field_value.value_text


# ---------------------------------------------------------------------------
# Display formatting for composite (object / array) field values
#
# WeasyPrint templates print ``{{ value }}`` directly, so a ``dict`` or ``list``
# reaches the page as its Python repr (``{'selected': [...]}``) and a value the
# client stringified with ``String(obj)`` reaches it as ``[object Object]``.
# These helpers flatten such values into compact, human-readable text.
# ---------------------------------------------------------------------------


def _is_object_placeholder(text: Any) -> bool:
    """True when ``text`` is the JS ``String(object)`` artifact."""
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if not stripped:
        return False
    tokens = [token.strip() for token in stripped.split(",")]
    return all(token == "[object Object]" for token in tokens)


def _humanize_key(key: Any) -> str:
    """Turn a field/option code ("ps_tenderness") into a readable label."""
    return " ".join(str(key).replace("_", " ").replace("-", " ").split()).title()


def _options_label_map(field_data: dict[str, Any]) -> dict[str, str]:
    """Build a ``{option_value: label}`` map from a serialized field."""
    labels: dict[str, str] = {}
    for item in field_data.get("picklist_items") or []:
        if isinstance(item, dict) and item.get("value") is not None:
            labels[str(item["value"])] = str(item.get("label") or item["value"])
    config = field_data.get("config") or {}
    for opt in config.get("options") or []:
        if isinstance(opt, dict) and opt.get("value") is not None:
            labels.setdefault(str(opt["value"]), str(opt.get("label") or opt["value"]))
    return labels


def _humanize_json(value: Any) -> str:
    """Render an arbitrary JSON value as compact text.

    Never emits a Python ``dict``/``list`` repr or the ``[object Object]``
    artifact.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            rendered = _humanize_json(val)
            if rendered == "":
                continue
            parts.append(f"{_humanize_key(key)}: {rendered}")
        return "; ".join(parts)
    if isinstance(value, (list, tuple)):
        return ", ".join(r for r in (_humanize_json(item) for item in value) if r != "")
    return str(value)


def _format_multiselect(field_data: dict[str, Any], raw: Any) -> str:
    """Render a multi-select value (plain list or ``{selected, notes}``) as text."""
    labels = _options_label_map(field_data)

    def label_for(option_value: Any) -> str:
        return labels.get(str(option_value)) or _humanize_key(option_value)

    if isinstance(raw, dict) and "selected" in raw:
        selected = raw.get("selected") or []
        notes = raw.get("notes") if isinstance(raw.get("notes"), dict) else {}
        parts = []
        for option_value in selected:
            base = label_for(option_value)
            note = notes.get(str(option_value)) if notes else None
            parts.append(f"{base}: {note}" if note else base)
        return ", ".join(parts)
    if isinstance(raw, (list, tuple)):
        return ", ".join(label_for(option_value) for option_value in raw)
    if isinstance(raw, str):
        if _is_object_placeholder(raw):
            return ""
        return ", ".join(label_for(v.strip()) for v in raw.split(",") if v.strip()) or raw
    return _humanize_json(raw)


def _format_checklist_options(field_data: dict[str, Any], raw: Any) -> list[dict[str, Any]]:
    """Return all configured options with selection state and optional notes."""
    selected: list[Any] = []
    notes: dict[str, Any] = {}
    if isinstance(raw, dict):
        selected = list(raw.get("selected") or [])
        notes = raw.get("notes") if isinstance(raw.get("notes"), dict) else {}
    elif isinstance(raw, (list, tuple)):
        selected = list(raw)
    elif isinstance(raw, str):
        selected = [value.strip() for value in raw.split(",") if value.strip()]

    selected_keys = {str(value) for value in selected}
    options = field_data.get("picklist_items") or (field_data.get("config") or {}).get("options") or []
    result = []
    for option in options:
        if isinstance(option, dict):
            value = option.get("value")
            label = option.get("label") or value
        else:
            value = option
            label = option
        key = str(value)
        result.append(
            {
                "value": value,
                "label": label,
                "selected": key in selected_keys,
                "note": notes.get(key, ""),
            }
        )
    return result


def _format_body_diagram(raw: Any) -> str:
    """Render a body-diagram pin array (``{x, y, view, note}[]``) as text."""
    if not raw:
        return ""
    if isinstance(raw, str):
        return "" if _is_object_placeholder(raw) else raw
    pins = list(raw) if isinstance(raw, (list, tuple)) else [raw]
    parts = []
    for pin in pins:
        if not isinstance(pin, dict):
            continue
        view = pin.get("view")
        note = pin.get("note") or pin.get("notes")
        site = f"{str(view).title()} view" if view else "Marked point"
        parts.append(f"{site}: {note}" if note else site)
    if parts:
        return ", ".join(parts)
    count = len(pins)
    return f"{count} marked point{'s' if count != 1 else ''}"


# Common medical grid column keys, in the order they should print, with
# display labels. Used to lay out grid tables (e.g. the prescription grid) with
# proper headers even when the stored ``config.grid_schema`` has drifted from
# the keys the client actually saves.
_GRID_KEY_ORDER = [
    "medicine", "medicine_name", "drug", "drug_name", "item", "product",
    "dose", "dosage", "strength",
    "frequency", "freq", "route",
    "days", "duration", "period",
    "quantity", "qty",
    "timing", "when",
    "instruction", "instructions", "direction", "directions",
    "remark", "remarks", "note", "notes",
]
_GRID_KEY_LABELS = {
    "medicine": "Medicine", "medicine_name": "Medicine", "drug": "Drug",
    "drug_name": "Drug", "item": "Item", "product": "Product",
    "dose": "Dose", "dosage": "Dose", "strength": "Strength",
    "frequency": "Frequency", "freq": "Frequency", "route": "Route",
    "days": "Days", "duration": "Duration", "period": "Period",
    "quantity": "Quantity", "qty": "Qty",
    "timing": "Timing", "when": "When",
    "instruction": "Instruction", "instructions": "Instructions",
    "direction": "Direction", "directions": "Directions",
    "remark": "Remark", "remarks": "Remarks", "note": "Note", "notes": "Notes",
}


def _grid_label(key: Any) -> str:
    return _GRID_KEY_LABELS.get(str(key).lower()) or _humanize_key(key)


def _order_grid_keys(keys: list) -> list:
    order = {k: i for i, k in enumerate(_GRID_KEY_ORDER)}
    return sorted(keys, key=lambda k: (order.get(str(k).lower(), len(_GRID_KEY_ORDER)), str(k)))


def _grid_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list, tuple)):
        return _humanize_json(value)
    return str(value).strip()


def _format_grid(field_data: dict[str, Any], raw: Any) -> Any:
    """Turn a GRID value (list of row dicts) into an aligned table with headers.

    Columns come from the field's ``config.grid_schema``/``columns`` when those
    keys actually match the stored data; otherwise (schema drift, e.g. the
    prescription grid whose config keys differ from the saved keys) they are
    derived from the data keys, ordered by a medical-form preference list. Every
    row emits a cell for every column in the same order, so empty values stay
    empty and columns never shift. Returns ``{"columns": [...], "rows": [...]}``
    or ``None`` when there is no tabular data.
    """
    if not isinstance(raw, (list, tuple)):
        return None
    rows = [r for r in raw if isinstance(r, dict)]
    if not rows:
        return None

    data_keys: list = []
    for row in rows:
        for key in row.keys():
            if key not in data_keys:
                data_keys.append(key)
    if not data_keys:
        return None

    config = field_data.get("config") or {}
    schema = config.get("grid_schema") or config.get("columns") or []
    schema_cols = [c for c in schema if isinstance(c, dict) and c.get("key")]
    schema_keys = [str(c["key"]) for c in schema_cols]
    matched = sum(1 for k in schema_keys if k in data_keys)
    use_schema = bool(schema_keys) and matched >= max(1, (len(schema_keys) + 1) // 2)

    columns: list = []
    if use_schema:
        for col in schema_cols:
            key = str(col["key"])
            if key in data_keys:
                columns.append({"key": key, "label": str(col.get("label") or _grid_label(key))})
        used = {c["key"] for c in columns}
        for key in _order_grid_keys([k for k in data_keys if k not in used]):
            columns.append({"key": key, "label": _grid_label(key)})
    else:
        for key in _order_grid_keys(data_keys):
            columns.append({"key": key, "label": _grid_label(key)})

    table_rows = [[_grid_cell(row.get(col["key"], "")) for col in columns] for row in rows]
    return {"columns": columns, "rows": table_rows}


def _format_print_display(field_data: dict[str, Any], raw: Any) -> Any:
    """Coerce a raw stored value into what the print template should show.

    GRID keeps its list-of-rows shape (the template renders it as a table);
    every other composite type is flattened to readable text so the printout
    never shows ``[object Object]`` or a raw ``dict``/``list`` repr.
    """
    if raw is None:
        return None
    field_type = field_data.get("field_type")
    if field_type == ClinicalFormField.FieldType.GRID:
        return _format_grid(field_data, raw)
    if field_type == ClinicalFormField.FieldType.MULTISELECT:
        return _format_multiselect(field_data, raw)
    if field_type == ClinicalFormField.FieldType.BODY_DIAGRAM:
        return _format_body_diagram(raw)
    if isinstance(raw, (dict, list, tuple)):
        return _humanize_json(raw)
    if isinstance(raw, str) and _is_object_placeholder(raw):
        return ""
    return raw


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def build_print_context(
    form_code: str,
    tenant_id: uuid.UUID,
    record_id: int,
    letterhead: bool,
    language: str,
    include_sections: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Resolve ``(template_name, context)`` for a single record of ``form_code``.

    Raises ``PrintFormCodeError`` for an unregistered form code and
    ``PrintNotFoundError`` if the record/admission does not exist for the
    tenant. ``include_sections`` only affects FORM_DISCHARGE_SUMMARY; every
    other form code ignores it.
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
    elif form_code == FORM_DISCHARGE_SUMMARY:
        context.update(_discharge_summary_context(tenant_id, record_id, include_sections))
    elif form_code == FORM_OPD_VISIT:
        context.update(_opd_visit_context(tenant_id, record_id))
    elif form_code == FORM_IPD_BILL:
        context.update(_ipd_bill_context(tenant_id, record_id))
    elif form_code == FORM_IPD_ADMISSION_STATEMENT:
        context.update(_admission_statement_context(tenant_id, record_id))
    elif form_code == FORM_OPD_BILL:
        context.update(_opd_bill_context(tenant_id, record_id))
    elif form_code == FORM_OPD_PAYMENT_RECEIPT:
        context.update(_opd_payment_receipt_context(tenant_id, record_id))
    elif form_code == FORM_IPD_PAYMENT_RECEIPT:
        context.update(_ipd_payment_receipt_context(tenant_id, record_id))
    elif form_code == FORM_MONITORING_CHART:
        context.update(_clinical_record_context(tenant_id, record_id, language))
        context["time_slots"] = MONITORING_CHART_TIME_SLOTS
        context["columns"] = MONITORING_CHART_COLUMNS
    else:
        # nursing_paper, progress_sheet, clinical_form all share the generic
        # ClinicalRecord-driven context; templates render different subsets.
        context.update(_clinical_record_context(tenant_id, record_id, language))

    return template_name, context


def render_print_html(
    form_code: str,
    tenant_id: uuid.UUID,
    record_id: int,
    letterhead: bool,
    language: str,
    include_sections: bool = True,
) -> str:
    """Render a single record's print template to an HTML string."""
    template_name, context = build_print_context(
        form_code, tenant_id, record_id, letterhead, language, include_sections
    )
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
    _ensure_windows_gtk_runtime()

    from weasyprint import HTML

    return HTML(string=html).write_pdf()


_GTK_DLL_DIRECTORY_HANDLES: list[Any] = []


def _ensure_windows_gtk_runtime() -> None:
    """Make an installed GTK runtime discoverable before importing WeasyPrint.

    Windows does not consistently search a system-wide GTK installation for
    dependent DLLs. Previously PDF rendering depended on the shell that
    launched ``runserver`` having the GTK ``bin`` directory in ``PATH``; a
    normal restart from VS Code could therefore regress every print endpoint
    to ``cannot load library 'gobject-2.0-0'``. Registering the directory here
    keeps rendering independent of the process-launch environment.
    """
    if os.name != "nt":
        return

    configured = os.environ.get("WEASYPRINT_GTK_BIN")
    candidates = [
        Path(configured) if configured else None,
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "GTK3-Runtime Win64"
        / "bin",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "GTK3-Runtime"
        / "bin",
    ]
    for candidate in candidates:
        if candidate is None or not candidate.is_dir():
            continue
        candidate_text = str(candidate)
        path_parts = os.environ.get("PATH", "").split(os.pathsep)
        if candidate_text.casefold() not in {part.casefold() for part in path_parts}:
            os.environ["PATH"] = candidate_text + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory") and not _GTK_DLL_DIRECTORY_HANDLES:
            _GTK_DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(candidate_text))
        return


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
