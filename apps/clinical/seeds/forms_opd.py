"""OPD clinical forms (foundation structure)."""

OPD_FORMS = [
    {
        "code": "opd_consultation",
        "name": "OPD Consultation",
        "description": "OPD consultation / clinical note.",
        "entity_type": "opd_visit",
        "status": "published",
        "config": {"icon": "stethoscope", "color": "blue"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "complaints", "title": "Complaints & History", "display_order": 2,
                "fields": [
                    {"field_key": "chief_complaints", "field_type": "multiselect", "label": "Chief Complaints",
                     "config": {"picklist_code": "chief_complaints", "span": "full"}},
                    {"field_key": "history", "field_type": "textarea", "label": "History of Presenting Illness", "config": {"span": "full"}},
                    {"field_key": "past_history", "field_type": "multiselect", "label": "Past History",
                     "config": {"picklist_code": "past_history", "span": "half"}},
                    {"field_key": "allergies", "field_type": "text", "label": "Allergies", "config": {"span": "half"}},
                ],
            },
            {"ref": "shared_vitals", "display_order": 3},
            {
                "code": "exam_dx", "title": "Examination & Diagnosis", "display_order": 4,
                "fields": [
                    {"field_key": "examination", "field_type": "textarea", "label": "Examination", "config": {"span": "full"}},
                    {"field_key": "diagnosis", "field_type": "textarea", "label": "Diagnosis",
                     "config": {"picklist_code": "diagnosis", "select_from_list": True, "span": "half"}},
                    {"field_key": "investigations_advised", "field_type": "multiselect", "label": "Investigations Advised",
                     "config": {"picklist_code": "investigations", "span": "half"}},
                ],
            },
            {
                "code": "rx", "title": "Prescription & Advice", "display_order": 5,
                "fields": [
                    {"field_key": "medicines", "field_type": "grid", "label": "Medicines",
                     "config": {"grid_schema": {"columns": [
                         {"key": "type", "label": "Type", "type": "picklist", "picklist_code": "medication_type"},
                         {"key": "medicine", "label": "Medicine", "type": "picklist", "picklist_code": "medicine", "allow_inline_create": True},
                         {"key": "dose", "label": "Dose", "type": "picklist", "picklist_code": "dose_qty"},
                         {"key": "frequency", "label": "Frequency", "type": "picklist", "picklist_code": "frequency"},
                         {"key": "days", "label": "Days", "type": "number"},
                         {"key": "instruction", "label": "Instruction", "type": "picklist", "picklist_code": "medicine_instruction"},
                     ], "allow_add": True}}},
                    {"field_key": "advice", "field_type": "textarea", "label": "Advice",
                     "config": {"picklist_code": "discharge_advice", "select_from_list": True, "span": "half"}},
                    {"field_key": "follow_up_date", "field_type": "date", "label": "Follow up Date", "config": {"span": "half"}},
                ],
            },
        ],
    },
]
