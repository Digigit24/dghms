"""IPD clinical forms (foundation structure, faithful to the Praczin papers)."""

# Reusable column schema for the discharge medicine grid (matches the
# "Medicine on Discharge" table: Type / Medicine Name / Dose / Frequency / Days / Instruction).
_MEDICINE_GRID = {
    "columns": [
        {"key": "type", "label": "Type", "type": "picklist", "picklist_code": "medication_type"},
        {"key": "medicine", "label": "Medicine Name", "type": "picklist", "picklist_code": "medicine", "allow_inline_create": True},
        {"key": "dose", "label": "Dose", "type": "picklist", "picklist_code": "dose_qty"},
        {"key": "frequency", "label": "Frequency", "type": "picklist", "picklist_code": "frequency"},
        {"key": "days", "label": "Days", "type": "number"},
        {"key": "instruction", "label": "Instruction", "type": "picklist", "picklist_code": "medicine_instruction"},
    ],
    "min_rows": 1, "allow_add": True,
}


IPD_FORMS = [
    # =====================================================================
    # DISCHARGE CARD  (mirrors the discharge screenshots)
    # =====================================================================
    {
        "code": "discharge_card",
        "name": "Discharge Card",
        "description": "IPD discharge summary / card.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "file-text", "color": "blue"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "discharge_details", "title": "Discharge Details", "display_order": 2,
                "fields": [
                    {"field_key": "discharge_date", "field_type": "date", "label": "Discharge Date", "config": {"span": "half"}},
                    {"field_key": "discharge_time", "field_type": "time", "label": "Discharge Time", "config": {"span": "half"}},
                    {"field_key": "room_type", "field_type": "text", "label": "Room Type", "config": {"span": "third"}},
                    {"field_key": "room_no", "field_type": "text", "label": "Room No", "config": {"span": "third"}},
                    {"field_key": "bed_no", "field_type": "text", "label": "Bed No", "config": {"span": "third"}},
                    {"field_key": "weight_on_discharge", "field_type": "number", "label": "Weight on Discharge (Kg)", "config": {"span": "half"}},
                    {"field_key": "discharge_type", "field_type": "picklist", "label": "Type of Discharge",
                     "config": {"picklist_code": "discharge_type", "span": "half"}},
                ],
            },
            {
                "code": "mlc_details", "title": "MLC Details", "display_order": 3, "is_collapsed": True,
                "fields": [
                    {"field_key": "mlc_no", "field_type": "text", "label": "MLC No.", "config": {"span": "half"}},
                    {"field_key": "police_station", "field_type": "text", "label": "Police Station", "config": {"span": "half"}},
                    {"field_key": "constable_name", "field_type": "text", "label": "Constable Name", "config": {"span": "half"}},
                    {"field_key": "police_buccal_no", "field_type": "text", "label": "Police Buccal No.", "config": {"span": "half"}},
                ],
            },
            {
                "code": "clinical_summary", "title": "Clinical Summary", "display_order": 4,
                "fields": [
                    {"field_key": "diagnosis", "field_type": "textarea", "label": "Diagnosis",
                     "config": {"picklist_code": "diagnosis", "select_from_list": True, "span": "half"}},
                    {"field_key": "admission_history", "field_type": "textarea", "label": "Admission History",
                     "config": {"picklist_code": "admission_history", "select_from_list": True, "span": "half",
                                "pull": {"source_form_code": "ipd_emr", "source_field_key": "presenting_history", "label": "Get from IPD EMR"}}},
                    {"field_key": "past_history", "field_type": "textarea", "label": "Past History",
                     "config": {"picklist_code": "past_history", "select_from_list": True, "span": "half"}},
                    {"field_key": "radiology_report", "field_type": "textarea", "label": "Radiology Report", "config": {"span": "half"}},
                    {"field_key": "operative_notes", "field_type": "textarea", "label": "Operative Notes",
                     "config": {"span": "half", "pull": {"source_form_code": "operative_notes", "source_field_key": "procedure", "label": "Add Note"}}},
                    {"field_key": "investigation", "field_type": "textarea", "label": "Investigation",
                     "config": {"picklist_code": "investigations", "select_from_list": True, "span": "half"}},
                    {"field_key": "daily_notes", "field_type": "textarea", "label": "Daily Notes / Clinical Summary",
                     "config": {"span": "half", "pull": {"source_form_code": "round_notes", "source_field_key": "note", "label": "from Round Note"}}},
                    {"field_key": "course_in_hospital", "field_type": "textarea", "label": "Course in Hospital",
                     "config": {"picklist_code": "course_in_hospital", "select_from_list": True, "span": "half"}},
                    {"field_key": "treatment_given", "field_type": "textarea", "label": "Treatment Given",
                     "config": {"picklist_code": "treatment_given", "select_from_list": True, "span": "half",
                                "pull": {"source_form_code": "round_notes", "source_field_key": "treatment", "label": "from Round Note"}}},
                    {"field_key": "condition_on_discharge", "field_type": "textarea", "label": "Condition On Discharge",
                     "config": {"picklist_code": "condition_at_discharge", "select_from_list": True, "span": "half"}},
                    {"field_key": "other_mlc", "field_type": "textarea", "label": "Other MLC", "config": {"span": "half"}},
                    {"field_key": "special_instructions", "field_type": "textarea", "label": "Special Instructions",
                     "config": {"picklist_code": "special_instructions", "select_from_list": True, "span": "half"}},
                    {"field_key": "advice", "field_type": "textarea", "label": "Advice",
                     "config": {"picklist_code": "discharge_advice", "select_from_list": True, "span": "half"}},
                    {"field_key": "emergency_contact_no", "field_type": "text", "label": "Emergency Contact No.", "config": {"span": "half"}},
                ],
            },
            {
                "code": "follow_up", "title": "Follow Up", "display_order": 5,
                "fields": [
                    {"field_key": "follow_up_date", "field_type": "date", "label": "Follow up Date", "config": {"span": "third"}},
                    {"field_key": "follow_up_time", "field_type": "time", "label": "Follow up Time", "config": {"span": "third"}},
                    {"field_key": "print_prescription", "field_type": "boolean", "label": "Print Prescription", "default_value": True, "config": {"span": "third"}},
                ],
            },
            {
                "code": "medicine_on_discharge", "title": "Medicine on Discharge", "display_order": 6,
                "fields": [
                    {"field_key": "medicines", "field_type": "grid", "label": "Medicines",
                     "config": {"grid_schema": _MEDICINE_GRID}},
                    {"field_key": "prescription_language", "field_type": "multiselect", "label": "Prescription Language",
                     "default_value": ["english"],
                     "config": {"options": [{"label": "English", "value": "english"}, {"label": "Marathi", "value": "marathi"}, {"label": "Hindi", "value": "hindi"}]}},
                ],
            },
        ],
    },

    # =====================================================================
    # IPD PATIENT EMR / DOCTOR INITIAL ASSESSMENT
    # =====================================================================
    {
        "code": "ipd_emr",
        "name": "IPD Patient EMR / Doctor Initial Assessment",
        "description": "Initial assessment by doctor (2 pages) — IPD 3.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "stethoscope", "color": "blue"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "presenting", "title": "Presenting Complaints & History", "display_order": 2,
                "fields": [
                    {"field_key": "chief_complaints", "field_type": "multiselect", "label": "Chief Complaints",
                     "config": {"picklist_code": "chief_complaints", "span": "full"}},
                    {"field_key": "presenting_history", "field_type": "textarea", "label": "History of Presenting Illness", "config": {"span": "full"}},
                    {"field_key": "past_history", "field_type": "multiselect", "label": "Past History",
                     "config": {"picklist_code": "past_history", "span": "half"}},
                    {"field_key": "drug_allergy", "field_type": "text", "label": "Allergies / Drug Reactions", "config": {"span": "half"}},
                    {"field_key": "personal_history", "field_type": "textarea", "label": "Personal / Family History", "config": {"span": "full"}},
                ],
            },
            {"ref": "shared_vitals", "display_order": 3},
            {
                "code": "clinical_exam", "title": "Clinical Examination", "display_order": 4,
                "fields": [
                    {"field_key": "general_exam", "field_type": "textarea", "label": "General Examination", "config": {"span": "half"}},
                    {"field_key": "systemic_exam", "field_type": "textarea", "label": "Systemic Examination", "config": {"span": "half"}},
                    {"field_key": "cns", "field_type": "text", "label": "CNS", "config": {"span": "half"}},
                    {"field_key": "cvs", "field_type": "text", "label": "CVS", "config": {"span": "half"}},
                    {"field_key": "rs", "field_type": "text", "label": "RS", "config": {"span": "half"}},
                    {"field_key": "pa", "field_type": "text", "label": "P/A", "config": {"span": "half"}},
                ],
            },
            {
                "code": "assessment_plan", "title": "Provisional Diagnosis & Plan", "display_order": 5,
                "fields": [
                    {"field_key": "provisional_diagnosis", "field_type": "textarea", "label": "Provisional Diagnosis",
                     "config": {"picklist_code": "diagnosis", "select_from_list": True, "span": "half"}},
                    {"field_key": "investigations_advised", "field_type": "multiselect", "label": "Investigations Advised",
                     "config": {"picklist_code": "investigations", "span": "half"}},
                    {"field_key": "treatment_plan", "field_type": "textarea", "label": "Treatment Plan", "config": {"span": "full"}},
                ],
            },
        ],
    },

    # =====================================================================
    # NURSING INITIAL ASSESSMENT
    # =====================================================================
    {
        "code": "nursing_initial_assessment",
        "name": "Nursing Initial Assessment",
        "description": "Initial assessment by nursing — IPD 6.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "clipboard-list", "color": "teal"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {"ref": "shared_vitals", "display_order": 2},
            {
                "code": "nursing_assessment", "title": "Nursing Assessment", "display_order": 3,
                "fields": [
                    {"field_key": "consciousness", "field_type": "text", "label": "Level of Consciousness", "config": {"span": "half"}},
                    {"field_key": "mobility", "field_type": "text", "label": "Mobility", "config": {"span": "half"}},
                    {"field_key": "skin_condition", "field_type": "text", "label": "Skin Condition / Pressure Sores", "config": {"span": "half"}},
                    {"field_key": "fall_risk", "field_type": "yes_no", "label": "Fall Risk?", "config": {"picklist_code": "yes_no"}},
                    {"field_key": "pain_score", "field_type": "picklist", "label": "Pain Score", "config": {"picklist_code": "pain_scale", "span": "half"}},
                    {"field_key": "allergies", "field_type": "text", "label": "Known Allergies", "config": {"span": "half"}},
                    {"field_key": "nursing_notes", "field_type": "textarea", "label": "Nursing Notes", "config": {"span": "full"}},
                ],
            },
        ],
    },

    # =====================================================================
    # ROUND NOTES (structured, NABH) — feeds Discharge pulls
    # =====================================================================
    {
        "code": "round_notes",
        "name": "Round Notes",
        "description": "Daily structured doctor round note.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "notebook-pen", "color": "indigo", "repeatable_daily": True},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "round", "title": "Round Note", "display_order": 2,
                "fields": [
                    {"field_key": "round_datetime", "field_type": "datetime", "label": "Date & Time", "config": {"span": "half"}},
                    {"field_key": "subjective", "field_type": "textarea", "label": "Subjective / Complaints", "config": {"span": "half"}},
                    {"field_key": "objective", "field_type": "textarea", "label": "Objective / Examination", "config": {"span": "half"}},
                    {"field_key": "note", "field_type": "textarea", "label": "Assessment / Progress Note", "config": {"span": "half"}},
                    {"field_key": "treatment", "field_type": "textarea", "label": "Treatment / Plan", "config": {"span": "half"}},
                    {"field_key": "doctor_name", "field_type": "text", "label": "Doctor Name", "config": {"span": "half"}},
                ],
            },
        ],
    },

    # =====================================================================
    # SHORT ROUND NOTES
    # =====================================================================
    {
        "code": "short_round_notes",
        "name": "Short Round Notes",
        "description": "Quick structured progress note.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "pen-line", "color": "indigo", "repeatable_daily": True},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "short_round", "title": "Short Note", "display_order": 2,
                "fields": [
                    {"field_key": "round_datetime", "field_type": "datetime", "label": "Date & Time", "config": {"span": "half"}},
                    {"field_key": "note", "field_type": "textarea", "label": "Progress Note", "config": {"span": "full"}},
                    {"field_key": "doctor_name", "field_type": "text", "label": "Doctor", "config": {"span": "half"}},
                ],
            },
        ],
    },

    # =====================================================================
    # PRESCRIPTION
    # =====================================================================
    {
        "code": "prescription",
        "name": "Prescription",
        "description": "Medicine prescription.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "pill", "color": "emerald"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "rx", "title": "Prescription", "display_order": 2,
                "fields": [
                    {"field_key": "medicines", "field_type": "grid", "label": "Medicines",
                     "config": {"grid_schema": _MEDICINE_GRID}},
                    {"field_key": "advice", "field_type": "textarea", "label": "Advice",
                     "config": {"picklist_code": "discharge_advice", "select_from_list": True, "span": "full"}},
                    {"field_key": "prescription_language", "field_type": "multiselect", "label": "Prescription Language",
                     "default_value": ["english"],
                     "config": {"options": [{"label": "English", "value": "english"}, {"label": "Marathi", "value": "marathi"}, {"label": "Hindi", "value": "hindi"}]}},
                ],
            },
        ],
    },

    # =====================================================================
    # INDOOR CASE PAPER
    # =====================================================================
    {
        "code": "indoor_case_paper",
        "name": "Indoor Case Paper",
        "description": "Indoor case paper / case sheet.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "file", "color": "slate"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "case", "title": "Case Details", "display_order": 2,
                "fields": [
                    {"field_key": "occupation", "field_type": "text", "label": "Occupation", "config": {"span": "half"}},
                    {"field_key": "address", "field_type": "text", "label": "Address", "config": {"span": "half"}},
                    {"field_key": "relative_name", "field_type": "text", "label": "Name of Relative", "config": {"span": "half"}},
                    {"field_key": "relation", "field_type": "picklist", "label": "Relation", "config": {"picklist_code": "relation", "span": "half"}},
                    {"field_key": "diagnosis_injuries", "field_type": "textarea", "label": "Diagnosis & Injuries", "config": {"span": "full"}},
                    {"field_key": "treatment_summary", "field_type": "textarea", "label": "Treatment Summary", "config": {"span": "full"}},
                ],
            },
        ],
    },

    # =====================================================================
    # MLC FORM
    # =====================================================================
    {
        "code": "mlc_form",
        "name": "MLC Form",
        "description": "Medico-Legal Case form — GEN 5.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "scale", "color": "red"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "mlc", "title": "MLC Details", "display_order": 2,
                "fields": [
                    {"field_key": "mlc_no", "field_type": "text", "label": "MLC No.", "config": {"span": "half"}},
                    {"field_key": "police_station", "field_type": "text", "label": "Police Station", "config": {"span": "half"}},
                    {"field_key": "constable_name", "field_type": "text", "label": "Constable Name", "config": {"span": "half"}},
                    {"field_key": "police_buccal_no", "field_type": "text", "label": "Police Buccal No.", "config": {"span": "half"}},
                    {"field_key": "identification_marks", "field_type": "textarea", "label": "Patient Identification Remarks", "config": {"span": "full"}},
                    {"field_key": "brought_by", "field_type": "text", "label": "Brought By", "config": {"span": "half"}},
                    {"field_key": "incident_datetime", "field_type": "datetime", "label": "Date & Time of Incident", "config": {"span": "half"}},
                    {"field_key": "alleged_history", "field_type": "textarea", "label": "Alleged History", "config": {"span": "full"}},
                ],
            },
        ],
    },

    # =====================================================================
    # TRANSFER / REFERRAL FORM
    # =====================================================================
    {
        "code": "transfer_referral_form",
        "name": "Transfer / Referral Form",
        "description": "Transfer or referral to another facility — GEN 4.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "send", "color": "amber"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "transfer", "title": "Transfer / Referral", "display_order": 2,
                "fields": [
                    {"field_key": "referred_to", "field_type": "text", "label": "Referred / Transferred To", "config": {"span": "half"}},
                    {"field_key": "reason", "field_type": "textarea", "label": "Reason for Transfer / Referral", "config": {"span": "half"}},
                    {"field_key": "diagnosis", "field_type": "textarea", "label": "Diagnosis",
                     "config": {"picklist_code": "diagnosis", "select_from_list": True, "span": "half"}},
                    {"field_key": "treatment_given", "field_type": "textarea", "label": "Treatment Given", "config": {"span": "half"}},
                    {"field_key": "condition_during_transfer", "field_type": "text", "label": "Condition During Transfer", "config": {"span": "half"}},
                    {"field_key": "mode_of_transport", "field_type": "text", "label": "Mode of Transport", "config": {"span": "half"}},
                ],
            },
        ],
    },

    # =====================================================================
    # TRAUMA SHEET
    # =====================================================================
    {
        "code": "trauma_sheet",
        "name": "Trauma Sheet",
        "description": "Trauma assessment sheet — GEN 6.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "activity", "color": "red"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {"ref": "shared_vitals", "display_order": 2},
            {
                "code": "trauma", "title": "Trauma Assessment", "display_order": 3,
                "fields": [
                    {"field_key": "mechanism", "field_type": "textarea", "label": "Mechanism of Injury", "config": {"span": "half"}},
                    {"field_key": "gcs", "field_type": "text", "label": "GCS (E/V/M)", "config": {"span": "half"}},
                    {"field_key": "airway", "field_type": "text", "label": "Airway", "config": {"span": "third"}},
                    {"field_key": "breathing", "field_type": "text", "label": "Breathing", "config": {"span": "third"}},
                    {"field_key": "circulation", "field_type": "text", "label": "Circulation", "config": {"span": "third"}},
                    {"field_key": "injuries", "field_type": "textarea", "label": "Injuries / Findings", "config": {"span": "full"}},
                    {"field_key": "intervention", "field_type": "textarea", "label": "Intervention Done", "config": {"span": "full"}},
                ],
            },
        ],
    },

    # =====================================================================
    # MRD CHECKLIST (form view of GEN 8; auto-resolver also exists)
    # =====================================================================
    {
        "code": "mrd_checklist",
        "name": "MRD Checklist",
        "description": "Medical Records Department file checklist — GEN 8.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "list-checks", "color": "slate"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "mrd_meta", "title": "MRD Details", "display_order": 2,
                "fields": [
                    {"field_key": "pmr_no", "field_type": "text", "label": "PMR No", "config": {"span": "third"}},
                    {"field_key": "rack_no", "field_type": "text", "label": "Rack No", "config": {"span": "third"}},
                    {"field_key": "shelf_no", "field_type": "text", "label": "Shelf No", "config": {"span": "third"}},
                    {"field_key": "diagnosis", "field_type": "text", "label": "Diagnosis", "config": {"span": "half"}},
                    {"field_key": "icd_code", "field_type": "text", "label": "ICD Code", "config": {"span": "half"}},
                ],
            },
            {
                "code": "mrd_check", "title": "Checklist", "display_order": 3,
                "fields": [
                    {"field_key": "missing_clinical_record", "field_type": "yes_no", "label": "Any missing clinical record?", "default_value": "no", "config": {"picklist_code": "yes_no"}},
                    {"field_key": "discharge_status", "field_type": "picklist", "label": "Discharge Status", "config": {"picklist_code": "discharge_status", "span": "half"}},
                    {"field_key": "discharge_card_attached", "field_type": "yes_no", "label": "Discharge Card Attached?", "default_value": "yes", "config": {"picklist_code": "yes_no"}},
                    {"field_key": "all_consents_proper", "field_type": "yes_no", "label": "All Consents Proper?", "default_value": "yes", "config": {"picklist_code": "yes_no"}},
                    {"field_key": "feedback_collected", "field_type": "yes_no", "label": "Feedback Collected?", "default_value": "yes", "config": {"picklist_code": "yes_no"}},
                    {"field_key": "feedback_score", "field_type": "number", "label": "Feedback Total Score",
                     "config": {"span": "half", "visibility_rule": {"all": [{"field": "feedback_collected", "op": "eq", "value": "yes"}]}}},
                    {"field_key": "icd_coding_done", "field_type": "yes_no", "label": "ICD Coding Done?", "default_value": "yes", "config": {"picklist_code": "yes_no"}},
                    {"field_key": "feedback_negative_remark", "field_type": "yes_no", "label": "Feedback Negative Remark?", "default_value": "no", "config": {"picklist_code": "yes_no"}},
                ],
            },
        ],
    },
]
