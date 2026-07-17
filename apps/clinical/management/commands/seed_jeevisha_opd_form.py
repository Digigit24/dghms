"""Seed the Jeevisha Pain OPD form in the current clinical-form system.

The legacy ``apps.opd`` template remains untouched.  Body-diagram answers are
stored in ``ClinicalFieldValue.value_json`` as a list of points shaped like::

    [{"x": 42.5, "y": 18.0, "view": "front", "note": "Tender"}]

``x`` and ``y`` are percentages in the inclusive range 0..100 and ``view`` is
either ``front`` or ``back``.
"""

from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.clinical.models import (
    ClinicalForm,
    ClinicalFormField,
    ClinicalFormSection,
    ClinicalPicklist,
    ClinicalPicklistItem,
    FormSectionPlacement,
)


JEEVISHA_TENANT_ID = uuid.UUID("615da126-a7d8-4112-a5ae-45bca4c623b6")
FORM_CODE = "jeevisha_pain_opd"

PICKLISTS = {
    "jeevisha_pmh_conditions": {
        "name": "Jeevisha Past Medical History Conditions",
        "items": [("DM", "dm"), ("HTN", "htn"), ("TB", "tb"), ("Thyroid", "thyroid")],
    },
    "jeevisha_diet": {
        "name": "Jeevisha Diet",
        "items": [("Veg", "veg"), ("Non-veg", "non_veg")],
    },
    "jeevisha_ls_spine_findings": {
        "name": "Jeevisha L/S Spine Findings",
        "items": [
            ("SLR", "slr"),
            ("Patrick's", "patricks"),
            ("FAIR", "fair"),
            ("Sp Tenderness", "sp_tenderness"),
            ("P/S Tenderness", "ps_tenderness"),
            ("Flex / Ext", "flex_ext"),
        ],
    },
    "jeevisha_c_spine_findings": {
        "name": "Jeevisha C Spine Findings",
        "items": [
            ("Axial", "axial"),
            ("Spurling", "spurling"),
            ("Sp Tenderness", "sp_tenderness"),
            ("P/S Tenderness", "ps_tenderness"),
            ("Flex / Ext / Rot", "flex_ext_rot"),
            ("Trap TP", "trap_tp"),
        ],
    },
    "jeevisha_knee_findings": {
        "name": "Jeevisha Knee Findings",
        "items": [
            ("Crepitus", "crepitus"),
            ("Tender", "tender"),
            ("Apley's", "apleys"),
            ("Drawer", "drawer"),
            ("ROM", "rom"),
        ],
    },
    "jeevisha_shoulder_findings": {
        "name": "Jeevisha Shoulder Findings",
        "items": [
            ("ROM Active", "rom_active"),
            ("ROM Passive", "rom_passive"),
            ("Neer's", "neers"),
            ("O'Brien", "obrien"),
            ("Rotator Cuff", "rotator_cuff"),
        ],
    },
}


def field(key, label, field_type="text", *, picklist=None, config=None, help_text=""):
    return {
        "field_key": key,
        "label": label,
        "field_type": field_type,
        "picklist": picklist,
        "config": config or {},
        "help_text": help_text,
    }


SECTIONS = [
    {
        "code": "jeevisha_opd_chief_complaint",
        "title": "Chief Complaint",
        "config": {
            "columns": 3,
            "groups": [
                {"key": "pain_history", "title": "Pain History", "column": 1},
                {"key": "neuro_symptoms", "title": "Neuro Symptoms", "column": 2},
                {"key": "visit_info", "title": "Visit Info", "column": 3},
            ],
        },
        "fields": [
            field("co_pain_site", "Site", config={"group": "pain_history", "column": 1, "prefix": "C/O Pain :"}),
            field("co_pain_type", "Type", config={"group": "pain_history", "column": 1}),
            field("duration", "Duration", config={"group": "pain_history", "column": 1}),
            field("radiation", "Radiation", config={"group": "pain_history", "column": 1}),
            field("aggravated_on", "Aggravated on", config={"group": "pain_history", "column": 1}),
            field("relieved_on", "Relieved on", config={"group": "pain_history", "column": 1}),
            field("tingling", "Tingling", config={"group": "neuro_symptoms", "column": 2}),
            field("numbness", "Numbness", config={"group": "neuro_symptoms", "column": 2}),
            field("burning", "Burning", config={"group": "neuro_symptoms", "column": 2}),
            field("weakness", "Weakness", config={"group": "neuro_symptoms", "column": 2}),
            field("ems", "EMS", config={"group": "neuro_symptoms", "column": 2}),
            field("associated_features", "Associated Features", config={"group": "neuro_symptoms", "column": 2}),
            field("direct_referral", "Direct / Referral", config={"group": "visit_info", "column": 3}),
            field("bowel_bladder", "B/B", config={"group": "visit_info", "column": 3}),
            field("acidity_sleep_appetite", "Acidity / Sleep / Appetite", config={"group": "visit_info", "column": 3}),
            field("treatment_history", "Treatment History", "textarea", config={"group": "visit_info", "column": 3}),
        ],
    },
    {
        "code": "jeevisha_opd_past_medical_history",
        "title": "Past Medical History",
        "config": {"columns": 5, "layout": "inline_row"},
        "fields": [
            field("pmh_conditions", "Conditions", "multiselect", picklist="jeevisha_pmh_conditions", config={"inline_options": True}),
            field("allergies", "Allergies", "textarea"),
            field("addiction", "Addiction"),
            field("occupation", "Occupation"),
            field("diet", "Veg / Non-veg", "picklist", picklist="jeevisha_diet"),
        ],
    },
    {
        "code": "jeevisha_opd_examination",
        "title": "Examination",
        "config": {"columns": 3, "column_widths": ["1fr", "1fr", "1.5fr"]},
        "fields": [
            field(
                "ls_spine_findings",
                "L/S Spine",
                "multiselect",
                picklist="jeevisha_ls_spine_findings",
                config={"column": 1, "orientation": "vertical", "allow_notes": True, "per_option_notes": True},
            ),
            field(
                "c_spine_findings",
                "C Spine",
                "multiselect",
                picklist="jeevisha_c_spine_findings",
                config={"column": 2, "orientation": "vertical", "allow_notes": True, "per_option_notes": True},
            ),
            field(
                "body_diagram_canvas",
                "Mark pain points",
                "body_diagram",
                config={
                    "column": 3,
                    "views": ["front", "back"],
                    "coordinate_unit": "percent",
                    "value_json_contract": {
                        "type": "array",
                        "item": {"x": "float:0..100", "y": "float:0..100", "view": ["front", "back"], "note": "string"},
                    },
                },
            ),
        ],
    },
    {
        "code": "jeevisha_opd_knee",
        "title": "Knee",
        "config": {"columns": 2},
        "fields": [
            field("left_knee_findings", "Left", "multiselect", picklist="jeevisha_knee_findings", config={"column": 1, "allow_notes": True, "per_option_notes": True}),
            field("right_knee_findings", "Right", "multiselect", picklist="jeevisha_knee_findings", config={"column": 2, "allow_notes": True, "per_option_notes": True}),
        ],
    },
    {
        "code": "jeevisha_opd_shoulder",
        "title": "Shoulder",
        "config": {"columns": 1},
        "fields": [
            field("shoulder_findings", "Shoulder Findings", "multiselect", picklist="jeevisha_shoulder_findings", config={"allow_notes": True, "per_option_notes": True}),
        ],
    },
    {
        "code": "jeevisha_opd_provisional_diagnosis",
        "title": "Provisional Diagnosis",
        "config": {"columns": 1},
        "fields": [field("provisional_diagnosis", "Provisional Diagnosis", "textarea")],
    },
    {
        "code": "jeevisha_opd_prescription",
        "title": "Rx",
        "config": {"columns": 1, "role": "prescription"},
        "fields": [
            field(
                "prescription",
                "Medicines",
                "grid",
                config={
                    "allow_add": True,
                    "max_rows": 50,
                    "grid_schema": [
                        {"key": "medicine_name", "label": "Medicine", "type": "text", "required": True},
                        {"key": "dosage", "label": "Dose", "type": "text"},
                        {"key": "frequency", "label": "Frequency", "type": "text"},
                        {"key": "duration", "label": "Duration", "type": "text"},
                        {"key": "quantity", "label": "Quantity", "type": "number", "min": 1},
                    ],
                },
            )
        ],
    },
    {
        "code": "jeevisha_opd_plan",
        "title": "Plan",
        "config": {"columns": 1},
        "fields": [field("plan_text", "Plan", "textarea")],
    },
    {
        "code": "jeevisha_opd_physiotherapy",
        "title": "Physiotherapy",
        "config": {"columns": 1},
        "fields": [field("physiotherapy_text", "Physiotherapy", "textarea")],
    },
]


class Command(BaseCommand):
    help = "Idempotently seed the Jeevisha Pain OPD form in apps.clinical."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", default=str(JEEVISHA_TENANT_ID))
        parser.add_argument("--user-id", default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            tenant_id = uuid.UUID(options["tenant_id"])
            user_id = uuid.UUID(options["user_id"]) if options.get("user_id") else None
        except (TypeError, ValueError) as exc:
            raise CommandError(f"Invalid UUID: {exc}") from exc

        counts = {"picklists": 0, "items": 0, "sections": 0, "fields": 0, "placements": 0}
        with transaction.atomic():
            picklists = {}
            for code, spec in PICKLISTS.items():
                obj, _ = ClinicalPicklist.objects.update_or_create(
                    tenant_id=tenant_id,
                    code=code,
                    defaults={
                        "name": spec["name"],
                        "description": "Reusable option list for the Jeevisha Pain OPD form.",
                        "is_system": False,
                        "is_active": True,
                        "created_by_user_id": user_id,
                    },
                )
                picklists[code] = obj
                counts["picklists"] += 1
                for order, (label, value) in enumerate(spec["items"], 1):
                    ClinicalPicklistItem.objects.update_or_create(
                        tenant_id=tenant_id,
                        picklist=obj,
                        value=value,
                        defaults={
                            "label": label,
                            "display_order": order,
                            "is_active": True,
                            "created_by_user_id": user_id,
                        },
                    )
                    counts["items"] += 1

            form_obj, _ = ClinicalForm.objects.update_or_create(
                tenant_id=tenant_id,
                code=FORM_CODE,
                defaults={
                    "name": "Jeevisha Pain OPD",
                    "description": "Structured consultation form for Jeevisha Spine | Pain | Regenerative Hospital.",
                    "version": 1,
                    "status": ClinicalForm.Status.PUBLISHED,
                    "is_system": False,
                    "entity_type": ClinicalForm.EntityType.OPD_VISIT,
                    "config": {"layout": "sections", "source": "jeevisha_paper_opd_form"},
                    "is_active": True,
                    "created_by_user_id": user_id,
                },
            )

            for section_order, spec in enumerate(SECTIONS, 1):
                section, _ = ClinicalFormSection.objects.update_or_create(
                    tenant_id=tenant_id,
                    code=spec["code"],
                    defaults={
                        "title": spec["title"],
                        "description": "",
                        "is_system": False,
                        "config": spec["config"],
                        "is_active": True,
                        "created_by_user_id": user_id,
                    },
                )
                counts["sections"] += 1
                FormSectionPlacement.objects.update_or_create(
                    tenant_id=tenant_id,
                    form=form_obj,
                    section=section,
                    instance_key="",
                    defaults={
                        "display_order": section_order,
                        "is_collapsed": False,
                        "config": {},
                        "is_active": True,
                        "created_by_user_id": user_id,
                    },
                )
                counts["placements"] += 1

                for field_order, field_spec in enumerate(spec["fields"], 1):
                    picklist = picklists.get(field_spec["picklist"])
                    ClinicalFormField.objects.update_or_create(
                        tenant_id=tenant_id,
                        section=section,
                        field_key=field_spec["field_key"],
                        defaults={
                            "field_type": field_spec["field_type"],
                            "label": field_spec["label"],
                            "help_text": field_spec["help_text"],
                            "display_order": field_order,
                            "is_required": False,
                            "is_read_only": False,
                            "config": field_spec["config"],
                            "picklist": picklist,
                            "is_active": True,
                            "created_by_user_id": user_id,
                        },
                    )
                    counts["fields"] += 1

            if options["dry_run"]:
                transaction.set_rollback(True)

        mode = "DRY RUN (rolled back)" if options["dry_run"] else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"{mode}: tenant={tenant_id} form={FORM_CODE} counts={counts}"))
