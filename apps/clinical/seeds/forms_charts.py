"""Nursing & monitoring chart forms (grid-heavy, foundation structure)."""

CHART_FORMS = [
    # =====================================================================
    # MONITORING CHART (Intake / Output / Vitals time grid)
    # =====================================================================
    {
        "code": "monitoring_chart",
        "name": "Monitoring Chart",
        "description": "Hourly monitoring / intake-output chart — IPD 8 / 9.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "line-chart", "color": "cyan"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "monitoring", "title": "Monitoring", "display_order": 2,
                "fields": [
                    {"field_key": "investigation", "field_type": "text", "label": "Investigation", "config": {"span": "full"}},
                    {"field_key": "monitoring_grid", "field_type": "grid", "label": "Monitoring",
                     "config": {"grid_schema": {"columns": [
                         {"key": "time", "label": "Time", "type": "time"},
                         {"key": "pulse", "label": "Pulse/min", "type": "number"},
                         {"key": "bp", "label": "BP mmHg", "type": "text"},
                         {"key": "temp", "label": "Temp °F", "type": "number"},
                         {"key": "resp", "label": "Resp/min", "type": "number"},
                         {"key": "spo2", "label": "SPO2", "type": "number"},
                         {"key": "cvp", "label": "CVP cmH2O", "type": "text"},
                         {"key": "o2", "label": "O2 L/min", "type": "number"},
                         {"key": "intake_oral", "label": "Oral (ml)", "type": "number"},
                         {"key": "intake_rt", "label": "R.T. (ml)", "type": "number"},
                         {"key": "intake_iv", "label": "I.V. Fluids (ml)", "type": "number"},
                         {"key": "output_rta", "label": "R.T.A. (ml)", "type": "number"},
                         {"key": "output_drain", "label": "Drain (ml)", "type": "number"},
                         {"key": "output_urine", "label": "Urine (ml)", "type": "number"},
                         {"key": "bsl", "label": "BSL", "type": "text"},
                         {"key": "procedure", "label": "Procedure", "type": "text"},
                         {"key": "nurse_sign", "label": "Nurse Sign", "type": "text"},
                     ], "allow_add": True}}},
                ],
            },
        ],
    },

    # =====================================================================
    # MEDICATION CHART
    # =====================================================================
    {
        "code": "medication_chart",
        "name": "Medication Chart",
        "description": "Medication administration chart.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "syringe", "color": "emerald"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "medication", "title": "Medication", "display_order": 2,
                "fields": [
                    {"field_key": "medication_grid", "field_type": "grid", "label": "Medications",
                     "config": {"grid_schema": {"columns": [
                         {"key": "medication", "label": "Medication", "type": "picklist", "picklist_code": "medicine", "allow_inline_create": True},
                         {"key": "dosage", "label": "Dosage", "type": "text"},
                         {"key": "route", "label": "Route", "type": "picklist", "picklist_code": "route_of_administration"},
                         {"key": "frequency", "label": "Frequency", "type": "picklist", "picklist_code": "frequency"},
                         {"key": "dr_sign", "label": "Dr. Sign", "type": "text"},
                         {"key": "time", "label": "Time", "type": "time"},
                         {"key": "nurse_sign", "label": "Nurse Sign", "type": "text"},
                     ], "allow_add": True}}},
                ],
            },
        ],
    },

    # =====================================================================
    # DRUG CHART (Drugs name x date)
    # =====================================================================
    {
        "code": "drug_chart",
        "name": "Medication / Drug Chart",
        "description": "Drug chart (drug name vs date).",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "pill", "color": "emerald"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "drugs", "title": "Drugs", "display_order": 2,
                "fields": [
                    {"field_key": "drug_grid", "field_type": "grid", "label": "Drugs",
                     "config": {"grid_schema": {"columns": [
                         {"key": "drug_name", "label": "Drug Name", "type": "picklist", "picklist_code": "medicine", "allow_inline_create": True},
                         {"key": "dose", "label": "Dose", "type": "text"},
                         {"key": "route", "label": "Route", "type": "picklist", "picklist_code": "route_of_administration"},
                         {"key": "frequency", "label": "Frequency", "type": "picklist", "picklist_code": "frequency"},
                         {"key": "start_date", "label": "Start Date", "type": "date"},
                         {"key": "stop_date", "label": "Stop Date", "type": "date"},
                     ], "allow_add": True}}},
                ],
            },
        ],
    },

    # =====================================================================
    # NURSES CONTINUATION SHEET
    # =====================================================================
    {
        "code": "nurses_continuation_sheet",
        "name": "Nurses Continuation Sheet",
        "description": "Nurses continuation / notes sheet — IPD 7.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "notebook", "color": "teal"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "notes", "title": "Nursing Notes", "display_order": 2,
                "fields": [
                    {"field_key": "weight", "field_type": "number", "label": "Weight", "config": {"span": "half"}},
                    {"field_key": "bed_no", "field_type": "text", "label": "Bed No", "config": {"span": "half"}},
                    {"field_key": "notes_grid", "field_type": "grid", "label": "Notes",
                     "config": {"grid_schema": {"columns": [
                         {"key": "datetime", "label": "Date & Time", "type": "datetime"},
                         {"key": "note", "label": "Nursing Notes", "type": "textarea"},
                         {"key": "signature", "label": "Signature", "type": "text"},
                     ], "allow_add": True}}},
                ],
            },
        ],
    },

    # =====================================================================
    # TRANSFUSION (BT) MONITORING CHART
    # =====================================================================
    {
        "code": "bt_monitoring_chart",
        "name": "Transfusion Monitoring Chart",
        "description": "Blood transfusion monitoring chart — GEN 2 related.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "droplet", "color": "red"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "bt_meta", "title": "Transfusion Details", "display_order": 2,
                "fields": [
                    {"field_key": "bank_no", "field_type": "text", "label": "Bank No", "config": {"span": "third"}},
                    {"field_key": "blood_group", "field_type": "text", "label": "Blood Group", "config": {"span": "third"}},
                    {"field_key": "blood_unit_no", "field_type": "text", "label": "Blood Unit No", "config": {"span": "third"}},
                    {"field_key": "tests_result", "field_type": "text", "label": "All Tests (Positive/Negative)", "config": {"span": "half"}},
                    {"field_key": "checked_by", "field_type": "text", "label": "Blood Unit Checked By", "config": {"span": "half"}},
                    {"field_key": "start_time", "field_type": "datetime", "label": "Transfusion Start", "config": {"span": "half"}},
                    {"field_key": "completion_time", "field_type": "datetime", "label": "Transfusion Completion", "config": {"span": "half"}},
                ],
            },
            {
                "code": "bt_grid", "title": "Monitoring", "display_order": 3,
                "fields": [
                    {"field_key": "bt_monitoring", "field_type": "grid", "label": "Vitals",
                     "config": {"grid_schema": {"columns": [
                         {"key": "interval", "label": "Time", "type": "text"},
                         {"key": "pulse", "label": "Pulse", "type": "number"},
                         {"key": "bp", "label": "BP", "type": "text"},
                         {"key": "resp_rate", "label": "Respiration Rate", "type": "number"},
                         {"key": "drop_rate", "label": "Blood Drop Rate/min", "type": "number"},
                         {"key": "remarks", "label": "Remarks", "type": "text"},
                     ], "allow_add": True,
                         "default_rows": ["0 Hr", "15 min", "30 min", "1 Hr", "1 Hr 30 min", "2 Hr", "2 Hr 30 min"]}}},
                ],
            },
        ],
    },
]
