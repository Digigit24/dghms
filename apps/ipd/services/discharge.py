"""Discharge-packet aggregation and AI narrative generation."""

import json
from decimal import Decimal

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from openai import OpenAI

from apps.clinical.models import ClinicalRecord, FormSectionPlacement


def _json_safe(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _field_value(row):
    if row.picklist_item_id:
        return row.picklist_item.label
    for name in (
        "value_text", "value_number", "value_boolean", "value_date",
        "value_datetime", "value_time", "value_json",
    ):
        value = getattr(row, name)
        if value is not None and value != "":
            if isinstance(value, Decimal):
                return str(value.normalize())
            return _json_safe(value)
    return None


def collect_discharge_sections(admission):
    """Return admission sections configured for discharge, without AI rewriting."""
    records = list(
        ClinicalRecord.objects.filter(
            tenant_id=admission.tenant_id,
            encounter_type="ipd_admission",
            encounter_id=admission.id,
            is_active=True,
        )
        .select_related("form")
        .prefetch_related("field_values__field", "field_values__picklist_item")
        .order_by("form__name", "occurrence_index", "id")
    )
    if not records:
        return [], []

    placements = FormSectionPlacement.objects.filter(
        tenant_id=admission.tenant_id,
        form_id__in={record.form_id for record in records},
        is_active=True,
        section__is_active=True,
        section__config__print_on_discharge=True,
    ).select_related("form", "section").prefetch_related("section__fields").order_by(
        "form__name", "display_order", "id"
    )
    placements_by_form = {}
    for placement in placements:
        placements_by_form.setdefault(placement.form_id, []).append(placement)

    sections, included_records = [], []
    for record in records:
        record_values = {value.field_id: value for value in record.field_values.all() if value.is_active}
        record_included = False
        for placement in placements_by_form.get(record.form_id, []):
            fields = sorted(
                (field for field in placement.section.fields.all() if field.is_active),
                key=lambda field: (field.display_order, field.id),
            )
            values = []
            for field in fields:
                row = record_values.get(field.id)
                value = _field_value(row) if row else None
                if value is not None and value != [] and value != {}:
                    values.append({
                        "field_key": field.field_key,
                        "label": field.label,
                        "field_type": field.field_type,
                        "value": value,
                    })
            if not values:
                continue
            sections.append({
                "record_id": record.id,
                "form_code": record.form.code,
                "form_name": record.form.name,
                "occurrence_index": record.occurrence_index,
                "recorded_at": _json_safe(record.updated_at),
                "section_id": placement.section_id,
                "section_code": placement.section.code,
                "section_title": placement.title_override or placement.section.title,
                "values": values,
            })
            record_included = True
        if record_included:
            included_records.append(record.id)
    return sections, included_records


def generate_discharge_narrative(admission, sections):
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")
    model = getattr(settings, "OPENAI_DISCHARGE_MODEL", "") or getattr(
        settings, "OPENAI_FORM_MODEL", "gpt-4o-mini"
    )
    source = {
        "admission_type": admission.admission_type,
        "admission_date": admission.admission_date,
        "reason_for_admission": admission.reason,
        "provisional_diagnosis": admission.provisional_diagnosis,
        "final_diagnosis": admission.final_diagnosis,
        "doctor": getattr(admission.doctor, "full_name", None),
        "clinical_sections": sections,
    }
    # Explicit timeout: the SDK default (600s call / 5s connect) can outlast
    # nginx/Cloudflare's own upstream timeout, which turns a slow-but-legitimate
    # generation into an opaque edge 502 instead of the JSON error the caller's
    # try/except is meant to produce. Fail inside our own error handling first.
    response = OpenAI(api_key=api_key, timeout=55.0).chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "Draft a clinician-reviewable hospital discharge summary using only supplied facts. "
                    "Never invent diagnoses, medicines, procedures, results, follow-up, or condition. "
                    "Omit unsupported headings. Return concise plain text with clinical headings. Do not "
                    "repeat raw form tables because they are appended verbatim elsewhere."
                ),
            },
            {"role": "user", "content": json.dumps(source, cls=DjangoJSONEncoder)},
        ],
    )
    narrative = (response.choices[0].message.content or "").strip()
    if not narrative:
        raise ValueError("OpenAI returned an empty discharge summary.")
    return narrative, model
