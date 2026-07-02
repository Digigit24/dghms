"""Operative / surgical clinical forms (foundation structure)."""


def _yes_no(field_key, label, default="no", with_remarks=False, **cfg):
    config = {"picklist_code": "yes_no", **cfg}
    if with_remarks:
        config["with_remarks"] = True
    return {"field_key": field_key, "field_type": "yes_no", "label": label,
            "default_value": default, "config": config}


OPERATIVE_FORMS = [
    # =====================================================================
    # PRE ANAESTHESIA ASSESSMENT (PAC)
    # =====================================================================
    {
        "code": "pre_anaesthesia_assessment",
        "name": "Pre Anaesthesia Assessment",
        "description": "PAC by anaesthetist — SX 5 / pre-op.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "syringe", "color": "purple"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "pac_procedure", "title": "Procedure", "display_order": 2,
                "fields": [
                    {"field_key": "procedure_to_be_done", "field_type": "text", "label": "Procedure To Be Done", "config": {"span": "half"}},
                    {"field_key": "procedure_planned_on", "field_type": "datetime", "label": "Procedure Planned On", "config": {"span": "half"}},
                ],
            },
            {
                "code": "pac_history", "title": "History", "display_order": 3,
                "fields": [
                    {"field_key": "medical_history", "field_type": "textarea", "label": "Medical History", "config": {"span": "half"}},
                    {"field_key": "surgical_history", "field_type": "textarea", "label": "Surgical History", "config": {"span": "half"}},
                    {"field_key": "anaesthesia_history", "field_type": "textarea", "label": "Anaesthesia History", "config": {"span": "half"}},
                    {"field_key": "current_medication", "field_type": "textarea", "label": "Current Medication List", "config": {"span": "half"}},
                    {"field_key": "allergies", "field_type": "text", "label": "Allergies / Drug Reactions", "config": {"span": "full"}},
                ],
            },
            {"ref": "shared_vitals", "display_order": 4, "title_override": "Physical Examination"},
            {
                "code": "pac_assessment", "title": "Assessment & Plan", "display_order": 5,
                "fields": [
                    {"field_key": "airway_assessment", "field_type": "text", "label": "Airway Assessment", "config": {"span": "half"}},
                    {"field_key": "cardiopulmonary_assessment", "field_type": "text", "label": "Cardiopulmonary Assessment", "config": {"span": "half"}},
                    {"field_key": "asa_grade", "field_type": "picklist", "label": "ASA Grade", "config": {"picklist_code": "asa_grade", "span": "half"}},
                    {"field_key": "emergency_or_planned", "field_type": "text", "label": "Emergency / Planned", "config": {"span": "half"}},
                    {"field_key": "anaesthesia_plan", "field_type": "textarea", "label": "Anaesthesia Plan", "config": {"picklist_code": "anesthesia_type", "select_from_list": True, "span": "full"}},
                    {"field_key": "premedication_advised", "field_type": "textarea", "label": "Premedication Advised", "config": {"span": "half"}},
                    {"field_key": "prophylactic_antibiotic", "field_type": "textarea", "label": "Prophylactic Antibiotic Advised", "config": {"span": "half"}},
                    {"field_key": "anaesthetist_name", "field_type": "text", "label": "Anaesthetist Name", "config": {"span": "full"}},
                ],
            },
        ],
    },

    # =====================================================================
    # PRE-OPERATIVE CHECKLIST (25-row yes/no/remarks, bilingual)
    # =====================================================================
    {
        "code": "pre_operative_checklist",
        "name": "Pre-Operative Check List",
        "description": "To be filled before sending patient from ward to OT — SX 6.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "check-square", "color": "purple"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "preop_meta", "title": "Surgery Details", "display_order": 2,
                "fields": [
                    {"field_key": "diagnosis", "field_type": "text", "label": "Diagnosis", "config": {"span": "half"}},
                    {"field_key": "surgery_name", "field_type": "text", "label": "Surgery Name", "config": {"span": "half"}},
                    {"field_key": "anaesthesia_planned", "field_type": "picklist", "label": "Anaesthesia Planned", "config": {"picklist_code": "anesthesia_type", "span": "half"}},
                ],
            },
            {
                "code": "preop_checklist", "title": "Checklist", "display_order": 3,
                "fields": [
                    _yes_no("identification", "Identification of patient (पेशंटचे नाव)", with_remarks=True),
                    _yes_no("general_consent", "General consent obtained (अनुमती पत्र)", with_remarks=True),
                    _yes_no("anaesthesia_consent", "Anaesthesia consent obtained (भुलेची संमती पत्र)", with_remarks=True),
                    _yes_no("surgery_consent", "Surgery / Procedural consent obtained (ऑपरेशन संमती पत्र)", with_remarks=True),
                    _yes_no("specific_consent", "Specific consent (if applicable)", with_remarks=True),
                    _yes_no("shaving", "Prepare the area of operation (शेविंग)", with_remarks=True),
                    _yes_no("enema", "Enema / Bowel wash given (if indicated)", with_remarks=True),
                    _yes_no("investigations_collected", "Pre-op investigations collected (ब्लड रिपोर्ट / फाइल)", with_remarks=True),
                    _yes_no("fitness", "Fitness (फिटनेस)", with_remarks=True),
                    _yes_no("iv_line", "I.V. line secured (इंट्राकॅथ लावणे)", with_remarks=True),
                    _yes_no("nbm", "N.B.M. confirmed (पेशंट उपाशीपोटी आहे का याची खात्री)", with_remarks=True),
                    _yes_no("pre_medication", "Pre-medication given & charted", with_remarks=True),
                    _yes_no("bath_given", "Bath given", with_remarks=True),
                    _yes_no("tpr_bp", "T.P.R. / B.P. checked (पल्स, बी.पी तपासणे)", with_remarks=True),
                    _yes_no("site_mark", "Site / Side mark", with_remarks=True),
                    _yes_no("blood_arranged", "Blood arranged, consent taken (रक्ताची सोय करणे)", with_remarks=True),
                    _yes_no("ornaments_removed", "Ornaments / dentures / lenses removed (दागिने काढून घेणे)", with_remarks=True),
                    _yes_no("ot_dress", "O.T. dress given (OT ड्रेस दिला)", with_remarks=True),
                    _yes_no("reports_to_anaesthetist", "Reports shown to anaesthetist (रिपोर्ट भुलीच्या डॉक्टरांना दाखवणे)", with_remarks=True),
                    _yes_no("deposit", "Deposit paid (डिपॉझीट जमा करणे)", with_remarks=True),
                ],
            },
        ],
    },

    # =====================================================================
    # SURGICAL SAFETY CHECKLIST (WHO Sign In / Time Out / Sign Out)
    # =====================================================================
    {
        "code": "surgical_safety_checklist",
        "name": "Surgical Safety Checklist",
        "description": "WHO surgical safety checklist (Sign In / Time Out / Sign Out).",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "shield-check", "color": "purple"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "sign_in", "title": "Sign In — Before Induction of Anaesthesia", "display_order": 2,
                "fields": [
                    _yes_no("identity_confirmed", "Patient confirmed identity, site, procedure & consent?", default="yes"),
                    _yes_no("site_marked", "Is the site marked?", default="yes"),
                    _yes_no("pac_done", "Is PAC done?", default="yes"),
                    _yes_no("anaesthesia_check", "Anaesthesia machine & medication check complete?", default="yes"),
                    _yes_no("pulse_ox", "Is the pulse oximeter functioning?", default="yes"),
                    _yes_no("known_allergy", "Does the patient have a known allergy?", default="no"),
                    _yes_no("difficult_airway", "Difficult airway / aspiration risk?", default="no"),
                    _yes_no("blood_loss_risk", "Risk of >500 ml blood loss (7 ml/kg in children)?", default="no"),
                ],
            },
            {
                "code": "time_out", "title": "Time Out — Before Skin Incision", "display_order": 3,
                "fields": [
                    _yes_no("team_introduced", "All team members introduced by name & role?", default="yes"),
                    _yes_no("name_procedure_confirmed", "Patient name, procedure & incision site confirmed?", default="yes"),
                    _yes_no("antibiotic_prophylaxis", "Antibiotic prophylaxis given within last 60 min?", default="yes"),
                    {"field_key": "anticipated_events", "field_type": "textarea", "label": "Anticipated critical events", "config": {"span": "full"}},
                    _yes_no("sterility_confirmed", "Has sterility been confirmed?", default="yes"),
                    _yes_no("imaging_displayed", "Is essential imaging displayed?", default="yes"),
                ],
            },
            {
                "code": "sign_out", "title": "Sign Out — Before Patient Leaves OT", "display_order": 4,
                "fields": [
                    _yes_no("procedure_recorded", "Name of the procedure recorded?", default="yes"),
                    _yes_no("counts_correct", "Instrument, sponge & needle counts correct?", default="yes"),
                    _yes_no("specimen_labeled", "Specimen labelled (incl. patient name)?", default="yes"),
                    _yes_no("equipment_issues", "Any equipment problems to be addressed?", default="no"),
                    {"field_key": "recovery_concerns", "field_type": "textarea", "label": "Key concerns for recovery & management", "config": {"span": "full"}},
                ],
            },
        ],
    },

    # =====================================================================
    # OPERATIVE NOTES
    # =====================================================================
    {
        "code": "operative_notes",
        "name": "Operative Notes",
        "description": "Operative notes / OT notes.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "scissors", "color": "rose"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "op_team", "title": "Surgical Team", "display_order": 2,
                "fields": [
                    {"field_key": "operation_date", "field_type": "date", "label": "Operation Date", "config": {"span": "third"}},
                    {"field_key": "start_time", "field_type": "time", "label": "Start Time", "config": {"span": "third"}},
                    {"field_key": "end_time", "field_type": "time", "label": "End Time", "config": {"span": "third"}},
                    {"field_key": "surgeon", "field_type": "text", "label": "Surgeon", "config": {"span": "half"}},
                    {"field_key": "assistant", "field_type": "text", "label": "Assistant", "config": {"span": "half"}},
                    {"field_key": "anaesthetist", "field_type": "text", "label": "Anaesthetist", "config": {"span": "half"}},
                    {"field_key": "anaesthesia_type", "field_type": "picklist", "label": "Anaesthesia Type", "config": {"picklist_code": "anesthesia_type", "span": "half"}},
                ],
            },
            {
                "code": "op_detail", "title": "Operative Detail", "display_order": 3,
                "fields": [
                    {"field_key": "pre_op_diagnosis", "field_type": "text", "label": "Pre-Operative Diagnosis", "config": {"picklist_code": "diagnosis", "select_from_list": True, "span": "half"}},
                    {"field_key": "procedure", "field_type": "textarea", "label": "Procedure Performed", "config": {"span": "half"}},
                    {"field_key": "position", "field_type": "picklist", "label": "Position", "config": {"picklist_code": "surgical_position", "span": "third"}},
                    {"field_key": "incision", "field_type": "picklist", "label": "Incision", "config": {"picklist_code": "incision_type", "span": "third"}},
                    {"field_key": "operative_time", "field_type": "text", "label": "Operative Time", "config": {"span": "third"}},
                    {"field_key": "procedure_details", "field_type": "textarea", "label": "Procedure Details", "config": {"span": "full"}},
                    {"field_key": "blood_loss", "field_type": "text", "label": "Estimated Blood Loss", "config": {"span": "third"}},
                    {"field_key": "mop_count", "field_type": "yes_no", "label": "Mop / Gauze / Instrument count verified", "default_value": "yes", "config": {"picklist_code": "yes_no"}},
                    {"field_key": "drain", "field_type": "yes_no", "label": "Drain", "default_value": "no", "config": {"picklist_code": "yes_no"}},
                    {"field_key": "closure", "field_type": "picklist", "label": "Skin Closure", "config": {"picklist_code": "incision_type", "span": "third"}},
                    {"field_key": "specimen", "field_type": "textarea", "label": "Histopathology Specimen", "config": {"span": "full"}},
                    {"field_key": "post_op_orders", "field_type": "textarea", "label": "Post-Op Orders", "config": {"span": "full"}},
                    {"field_key": "surgeon_name", "field_type": "text", "label": "Name & Signature of Surgeon", "config": {"span": "full"}},
                ],
            },
        ],
    },

    # =====================================================================
    # 1ST POST-OPERATIVE DAY
    # =====================================================================
    {
        "code": "first_post_op_day",
        "name": "1st Post-Operative Day",
        "description": "First post-op day note — SX 4.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "calendar-check", "color": "rose"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "post_op", "title": "Post-Operative Day 1", "display_order": 2,
                "fields": [
                    {"field_key": "observation", "field_type": "textarea", "label": "Observation", "config": {"span": "half"}},
                    {"field_key": "orders", "field_type": "textarea", "label": "Orders", "config": {"span": "half"}},
                    {"field_key": "diet", "field_type": "text", "label": "NBM / Liquids / Normal Diet", "config": {"span": "half"}},
                    {"field_key": "temp", "field_type": "text", "label": "Temp", "config": {"span": "third"}},
                    {"field_key": "pr", "field_type": "text", "label": "PR", "config": {"span": "third"}},
                    {"field_key": "bp", "field_type": "text", "label": "BP", "config": {"span": "third"}},
                    {"field_key": "bowel_sounds", "field_type": "text", "label": "Bowel Sounds", "config": {"span": "half"}},
                    {"field_key": "total_input", "field_type": "text", "label": "Total Input", "config": {"span": "third"}},
                    {"field_key": "output", "field_type": "text", "label": "Output", "config": {"span": "third"}},
                    {"field_key": "drainage", "field_type": "text", "label": "Drainage Quantity", "config": {"span": "third"}},
                    {"field_key": "surgeon_name", "field_type": "text", "label": "Surgeon Name", "config": {"span": "half"}},
                ],
            },
        ],
    },

    # =====================================================================
    # OT SCHEDULE
    # =====================================================================
    {
        "code": "ot_schedule",
        "name": "OT Schedule",
        "description": "Operation theatre schedule entry.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "calendar", "color": "rose"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "schedule", "title": "Schedule", "display_order": 2,
                "fields": [
                    {"field_key": "surgery_name", "field_type": "text", "label": "Surgery / Procedure", "config": {"span": "half"}},
                    {"field_key": "surgeon", "field_type": "text", "label": "Surgeon", "config": {"span": "half"}},
                    {"field_key": "anaesthetist", "field_type": "text", "label": "Anaesthetist", "config": {"span": "half"}},
                    {"field_key": "anaesthesia_type", "field_type": "picklist", "label": "Anaesthesia", "config": {"picklist_code": "anesthesia_type", "span": "half"}},
                    {"field_key": "scheduled_date", "field_type": "date", "label": "Scheduled Date", "config": {"span": "third"}},
                    {"field_key": "scheduled_time", "field_type": "time", "label": "Scheduled Time", "config": {"span": "third"}},
                    {"field_key": "ot_no", "field_type": "text", "label": "OT No", "config": {"span": "third"}},
                    {"field_key": "remarks", "field_type": "textarea", "label": "Remarks", "config": {"span": "full"}},
                ],
            },
        ],
    },

    # =====================================================================
    # INVESTIGATION
    # =====================================================================
    {
        "code": "investigation",
        "name": "Investigation",
        "description": "Investigations ordered / results.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "flask-conical", "color": "cyan"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "labs", "title": "Investigations", "display_order": 2,
                "fields": [
                    {"field_key": "investigations_ordered", "field_type": "multiselect", "label": "Investigations Ordered", "config": {"picklist_code": "investigations", "span": "full"}},
                    {"field_key": "lab_grid", "field_type": "grid", "label": "Lab Results",
                     "config": {"grid_schema": {"columns": [
                         {"key": "test", "label": "Test", "type": "picklist", "picklist_code": "lab_tests"},
                         {"key": "value", "label": "Value", "type": "text"},
                         {"key": "unit", "label": "Unit", "type": "text"},
                         {"key": "date", "label": "Date", "type": "date"},
                     ], "allow_add": True}}},
                    {"field_key": "radiology_report", "field_type": "textarea", "label": "Radiology Report", "config": {"span": "full"}},
                ],
            },
        ],
    },

    # =====================================================================
    # INCIDENT REGISTER  (conditional reveal: default No → Yes reveals section)
    # =====================================================================
    {
        "code": "incident_register",
        "name": "Incidence Register",
        "description": "Incident / audit register — Surgery OR Procedure with conditional reveals.",
        "entity_type": "ipd_admission",
        "status": "published",
        "config": {"icon": "alert-triangle", "color": "orange"},
        "sections": [
            {"ref": "shared_patient_banner", "display_order": 1},
            {
                "code": "surgery_or_procedure", "title": "Surgery OR Procedure", "display_order": 2,
                "fields": [
                    _yes_no("performed_surgery", "Performed any surgery or procedure?", default="no"),
                    {"field_key": "operation_no", "field_type": "text", "label": "Operation No",
                     "config": {"span": "third", "visibility_rule": {"all": [{"field": "performed_surgery", "op": "eq", "value": "yes"}]}}},
                    {"field_key": "operation_date", "field_type": "date", "label": "Date",
                     "config": {"span": "third", "visibility_rule": {"all": [{"field": "performed_surgery", "op": "eq", "value": "yes"}]}}},
                    {"field_key": "operation_time", "field_type": "time", "label": "Time",
                     "config": {"span": "third", "visibility_rule": {"all": [{"field": "performed_surgery", "op": "eq", "value": "yes"}]}}},
                ],
            },
            {
                # Whole section revealed only when a surgery was performed.
                "code": "surgery_audit", "title": "Surgery Audit", "display_order": 3,
                "visibility_rule": {"all": [{"field": "performed_surgery", "op": "eq", "value": "yes"}]},
                "fields": [
                    _yes_no("prophylactic_tablet", "Did you prescribe prophylactic antibiotic tablet?", default="no"),
                    _yes_no("prophylactic_injectable", "Did you prescribe injectable prophylactic antibiotic?", default="no"),
                    _yes_no("ssi", "Any surgery site infection occurred?", default="no"),
                    _yes_no("anesthesia_given", "Any anaesthesia given?", default="no"),
                    _yes_no("anesthesia_change", "Any change in anaesthesia?", default="no"),
                    _yes_no("reschedule_surgery", "Reschedule surgery?", default="no"),
                    _yes_no("operation_cancelled", "Operation Cancelled", default="no"),
                    _yes_no("wrong_site_surgery", "Wrong Site Surgery", default="no"),
                    _yes_no("wrong_patient_surgery", "Wrong Patient Surgery", default="no"),
                    _yes_no("post_op_death", "Post-op Death", default="no"),
                    _yes_no("repeat_surgery", "Repeat Surgery", default="no"),
                    _yes_no("pcml_case", "PCML Case", default="no"),
                ],
            },
            {
                "code": "sentinel_events", "title": "Sentinel Events", "display_order": 4,
                "fields": [
                    _yes_no("needle_left", "Is needle left inside Porta Cath?", default="no"),
                    _yes_no("sentinel_event", "Is Sentinel Event?", default="no"),
                    {"field_key": "incident_description", "field_type": "textarea", "label": "Incident Description",
                     "config": {"span": "full", "visibility_rule": {"any": [
                         {"field": "sentinel_event", "op": "eq", "value": "yes"},
                         {"field": "needle_left", "op": "eq", "value": "yes"}]}}},
                ],
            },
        ],
    },
]
