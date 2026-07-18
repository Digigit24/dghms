"""Read-only clinical section values shared with pharmacy/lab dashboards."""

from collections import OrderedDict
from decimal import Decimal

from .models import ClinicalFieldValue, ClinicalFormField


ENCOUNTER_TYPE_ALIASES = {
    "opd": "opd_visit",
    "opd.visit": "opd_visit",
    "opd_visit": "opd_visit",
    "ipd": "ipd_admission",
    "ipd.admission": "ipd_admission",
    "ipd_admission": "ipd_admission",
}


def _plain_value(value):
    field_type = value.field.field_type
    if field_type == ClinicalFormField.FieldType.NUMBER:
        number = value.value_number
        return str(number) if isinstance(number, Decimal) else number
    if field_type == ClinicalFormField.FieldType.BOOLEAN:
        return value.value_boolean
    if field_type == ClinicalFormField.FieldType.DATE:
        return value.value_date.isoformat() if value.value_date else None
    if field_type == ClinicalFormField.FieldType.DATETIME:
        return value.value_datetime.isoformat() if value.value_datetime else None
    if field_type == ClinicalFormField.FieldType.TIME:
        return value.value_time.isoformat() if value.value_time else None
    if field_type in {
        ClinicalFormField.FieldType.GRID,
        ClinicalFormField.FieldType.MULTISELECT,
        ClinicalFormField.FieldType.DATA_REF,
        ClinicalFormField.FieldType.BODY_DIAGRAM,
    }:
        return value.value_json
    if value.picklist_item_id:
        return value.picklist_item.label
    return value.value_text


def get_reference_sections(*, tenant_id, encounter_type, encounter_id, audience):
    """Return submitted values from sections explicitly visible to an audience."""
    if audience not in {"pharmacy", "lab"}:
        raise ValueError("audience must be pharmacy or lab")
    normalized_type = ENCOUNTER_TYPE_ALIASES.get(str(encounter_type or "").lower())
    if normalized_type is None:
        return []
    visible_key = f"visible_to_{audience}"

    values = (
        ClinicalFieldValue.objects.filter(
            tenant_id=tenant_id,
            record__tenant_id=tenant_id,
            record__encounter_type=normalized_type,
            record__encounter_id=encounter_id,
            record__is_active=True,
            field__is_active=True,
            field__section__is_active=True,
            is_active=True,
        )
        .select_related("record__form", "field__section", "picklist_item")
        .order_by(
            "record__form_id",
            "record__occurrence_index",
            "field__section__code",
            "field__display_order",
            "field_id",
        )
    )

    grouped = OrderedDict()
    for value in values:
        section = value.field.section
        if (section.config or {}).get(visible_key) is not True:
            continue
        record = value.record
        group_key = (record.id, section.id)
        entry = grouped.setdefault(
            group_key,
            {
                "record_id": record.id,
                "form_id": record.form_id,
                "form_code": record.form.code,
                "form_name": record.form.name,
                "section_id": section.id,
                "section_code": section.code,
                "section_title": section.title,
                "fields": [],
            },
        )
        entry["fields"].append(
            {
                "field_id": value.field_id,
                "field_key": value.field.field_key,
                "label": value.field.label,
                "field_type": value.field.field_type,
                "value": _plain_value(value),
            }
        )
    return list(grouped.values())
