"""Seed hospital-grade system clinical forms and picklists.

Adds:
  Picklists  — discharge_type, condition_at_discharge, chief_complaints,
               route_of_administration, drug_frequency, drug_timing,
               lab_investigations, discharge_advice
  OPD Forms  — system_opd_consultation
  IPD Forms  — system_ipd_admission, system_ipd_monitoring_entry,
               system_ipd_medication_chart, system_ipd_nursing_notes,
               system_ipd_incidence_register, system_ipd_mrd_checklist,
               system_ipd_discharge_checklist

All records use tenant_id = 00000000-0000-0000-0000-000000000000 (system tenant).
Run `python manage.py seed_system_forms --tenant-id <uuid>` to seed for real tenants.
"""

import uuid

from django.db import migrations

# ---------------------------------------------------------------------------
# System tenant UUID — same convention as migration 0002
# ---------------------------------------------------------------------------
_SYSTEM_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000000")

# ---------------------------------------------------------------------------
# Picklist definitions
# ---------------------------------------------------------------------------
NEW_SYSTEM_PICKLISTS = [
    {
        "code": "discharge_type",
        "name": "Discharge Type",
        "description": "How the patient was discharged.",
        "is_system": True,
        "items": [
            {"label": "Discharge to Home", "value": "discharge_home", "display_order": 1},
            {"label": "DAMA (Against Medical Advice)", "value": "dama", "display_order": 2},
            {"label": "Transfer to Another Facility", "value": "transfer", "display_order": 3},
            {"label": "Death", "value": "death", "display_order": 4},
            {"label": "Absconded", "value": "absconded", "display_order": 5},
        ],
    },
    {
        "code": "condition_at_discharge",
        "name": "Condition at Discharge",
        "description": "Patient condition at the time of discharge.",
        "is_system": True,
        "items": [
            {"label": "Cured", "value": "cured", "display_order": 1},
            {"label": "Improved", "value": "improved", "display_order": 2},
            {"label": "Not Improved", "value": "not_improved", "display_order": 3},
            {"label": "Stable", "value": "stable", "display_order": 4},
        ],
    },
    {
        "code": "chief_complaints",
        "name": "Chief Complaints",
        "description": "Common presenting complaints. Tenants can add more items.",
        "is_system": True,
        "items": [
            {"label": "Fever", "value": "fever", "display_order": 1},
            {"label": "Cold", "value": "cold", "display_order": 2},
            {"label": "Cough", "value": "cough", "display_order": 3},
            {"label": "Sore Throat", "value": "sore_throat", "display_order": 4},
            {"label": "Abdomen Pain", "value": "abdomen_pain", "display_order": 5},
            {"label": "Epigastric Pain", "value": "epigastric_pain", "display_order": 6},
            {"label": "Chest Pain", "value": "chest_pain", "display_order": 7},
            {"label": "Breathlessness", "value": "breathlessness", "display_order": 8},
            {"label": "Headache", "value": "headache", "display_order": 9},
            {"label": "Vomiting", "value": "vomiting", "display_order": 10},
            {"label": "Nausea", "value": "nausea", "display_order": 11},
            {"label": "Diarrhoea", "value": "diarrhoea", "display_order": 12},
            {"label": "Constipation", "value": "constipation", "display_order": 13},
            {"label": "Weakness", "value": "weakness", "display_order": 14},
            {"label": "Giddiness / Dizziness", "value": "giddiness", "display_order": 15},
            {"label": "Body Ache", "value": "body_ache", "display_order": 16},
            {"label": "Burning Micturition", "value": "burning_micturition", "display_order": 17},
            {"label": "Swelling", "value": "swelling", "display_order": 18},
            {"label": "Rash / Skin Eruptions", "value": "rash", "display_order": 19},
            {"label": "Joint Pain", "value": "joint_pain", "display_order": 20},
            {"label": "Back Pain", "value": "back_pain", "display_order": 21},
            {"label": "Palpitations", "value": "palpitations", "display_order": 22},
            {"label": "Loss of Appetite", "value": "loss_of_appetite", "display_order": 23},
            {"label": "Weight Loss", "value": "weight_loss", "display_order": 24},
        ],
    },
    {
        "code": "route_of_administration",
        "name": "Route of Administration",
        "description": "Drug administration routes.",
        "is_system": True,
        "items": [
            {"label": "Oral (PO)", "value": "oral", "display_order": 1},
            {"label": "Intravenous (IV)", "value": "iv", "display_order": 2},
            {"label": "Intramuscular (IM)", "value": "im", "display_order": 3},
            {"label": "Subcutaneous (SC)", "value": "sc", "display_order": 4},
            {"label": "Topical", "value": "topical", "display_order": 5},
            {"label": "Inhalation", "value": "inhalation", "display_order": 6},
            {"label": "Sublingual (SL)", "value": "sublingual", "display_order": 7},
            {"label": "Rectal (PR)", "value": "rectal", "display_order": 8},
            {"label": "Nasal", "value": "nasal", "display_order": 9},
            {"label": "Ophthalmic", "value": "ophthalmic", "display_order": 10},
            {"label": "Otic (Ear)", "value": "otic", "display_order": 11},
        ],
    },
    {
        "code": "drug_frequency",
        "name": "Drug Frequency",
        "description": "Medication dosing frequency abbreviations.",
        "is_system": True,
        "items": [
            {"label": "OD – Once Daily", "value": "od", "display_order": 1},
            {"label": "BD – Twice Daily", "value": "bd", "display_order": 2},
            {"label": "TDS – Three Times Daily", "value": "tds", "display_order": 3},
            {"label": "QID – Four Times Daily", "value": "qid", "display_order": 4},
            {"label": "SOS – As Needed", "value": "sos", "display_order": 5},
            {"label": "Stat – Immediately (Single Dose)", "value": "stat", "display_order": 6},
            {"label": "HS – At Bedtime", "value": "hs", "display_order": 7},
            {"label": "Weekly", "value": "weekly", "display_order": 8},
            {"label": "Fortnightly", "value": "fortnightly", "display_order": 9},
            {"label": "Monthly", "value": "monthly", "display_order": 10},
        ],
    },
    {
        "code": "drug_timing",
        "name": "Drug Timing",
        "description": "When to take medication relative to food.",
        "is_system": True,
        "items": [
            {"label": "After Food", "value": "after_food", "display_order": 1},
            {"label": "Before Food", "value": "before_food", "display_order": 2},
            {"label": "With Food", "value": "with_food", "display_order": 3},
            {"label": "Empty Stomach", "value": "empty_stomach", "display_order": 4},
            {"label": "At Bedtime", "value": "at_bedtime", "display_order": 5},
        ],
    },
    {
        "code": "lab_investigations",
        "name": "Lab Investigations",
        "description": "Common laboratory and radiology tests. Tenants can add more items.",
        "is_system": True,
        "items": [
            {"label": "Complete Blood Count (CBC)", "value": "cbc", "display_order": 1},
            {"label": "CRP (C-Reactive Protein)", "value": "crp", "display_order": 2},
            {"label": "ESR", "value": "esr", "display_order": 3},
            {"label": "Urine Routine & Microscopy", "value": "urine_routine", "display_order": 4},
            {"label": "Widal Test", "value": "widal", "display_order": 5},
            {"label": "Blood Sugar Fasting (BSF)", "value": "bsf", "display_order": 6},
            {"label": "Blood Sugar Random (BSR)", "value": "bsr", "display_order": 7},
            {"label": "HbA1c", "value": "hba1c", "display_order": 8},
            {"label": "Lipid Profile", "value": "lipid_profile", "display_order": 9},
            {"label": "Liver Function Test (LFT)", "value": "lft", "display_order": 10},
            {"label": "Kidney Function Test (KFT / RFT)", "value": "kft", "display_order": 11},
            {"label": "Serum Electrolytes", "value": "electrolytes", "display_order": 12},
            {"label": "Thyroid Profile (TSH)", "value": "tsh", "display_order": 13},
            {"label": "ECG", "value": "ecg", "display_order": 14},
            {"label": "2D Echocardiography", "value": "2d_echo", "display_order": 15},
            {"label": "Chest X-Ray", "value": "xray_chest", "display_order": 16},
            {"label": "USG Abdomen & Pelvis", "value": "usg_abdomen", "display_order": 17},
            {"label": "CT Scan", "value": "ct_scan", "display_order": 18},
            {"label": "MRI", "value": "mri", "display_order": 19},
            {"label": "Blood Culture & Sensitivity", "value": "blood_culture", "display_order": 20},
            {"label": "Urine Culture & Sensitivity", "value": "urine_culture", "display_order": 21},
            {"label": "Sputum Culture & Sensitivity", "value": "sputum_culture", "display_order": 22},
            {"label": "Dengue NS1 / IgM IgG", "value": "dengue", "display_order": 23},
            {"label": "Malaria Antigen / Smear", "value": "malaria", "display_order": 24},
            {"label": "COVID-19 RTPCR", "value": "covid_rtpcr", "display_order": 25},
            {"label": "Prothrombin Time (PT / INR)", "value": "pt_inr", "display_order": 26},
            {"label": "Coagulation Profile (APTT)", "value": "aptt", "display_order": 27},
            {"label": "Serum Uric Acid", "value": "uric_acid", "display_order": 28},
            {"label": "Serum Calcium", "value": "calcium", "display_order": 29},
            {"label": "Vitamin D3", "value": "vit_d3", "display_order": 30},
        ],
    },
    {
        "code": "discharge_advice",
        "name": "Discharge / Consultation Advice",
        "description": "Common advice given at consultation or discharge. Tenants can add more items.",
        "is_system": True,
        "items": [
            {"label": "Soft Diet", "value": "soft_diet", "display_order": 1},
            {"label": "Normal Diet", "value": "normal_diet", "display_order": 2},
            {"label": "Liquid Diet", "value": "liquid_diet", "display_order": 3},
            {"label": "Low Salt Diet", "value": "low_salt_diet", "display_order": 4},
            {"label": "Diabetic Diet", "value": "diabetic_diet", "display_order": 5},
            {"label": "High Protein Diet", "value": "high_protein_diet", "display_order": 6},
            {"label": "Drink Plenty of Water", "value": "plenty_water", "display_order": 7},
            {"label": "Complete Bed Rest", "value": "bed_rest", "display_order": 8},
            {"label": "Avoid Exertion / Heavy Work", "value": "avoid_exertion", "display_order": 9},
            {"label": "Wound Care at Home", "value": "wound_care", "display_order": 10},
            {"label": "Keep Wound Dry", "value": "keep_wound_dry", "display_order": 11},
            {"label": "Follow Up as Advised", "value": "follow_up", "display_order": 12},
            {"label": "Report if Symptoms Worsen", "value": "report_worsening", "display_order": 13},
            {"label": "Avoid Spicy / Oily Food", "value": "avoid_spicy", "display_order": 14},
            {"label": "No Alcohol / Smoking", "value": "no_alcohol_smoking", "display_order": 15},
        ],
    },
]

# ---------------------------------------------------------------------------
# Form definitions
# ---------------------------------------------------------------------------

SYSTEM_OPD_CONSULTATION = {
    "code": "system_opd_consultation",
    "name": "OPD Consultation",
    "description": "Standard outpatient consultation — vitals, complaints, examination, diagnosis, prescription, investigations and follow-up.",
    "version": 1,
    "status": "published",
    "is_system": True,
    "entity_type": "opd_visit",
    "config": {"layout": "vertical"},
    "sections": [
        {
            "code": "opd_vitals",
            "title": "Vitals",
            "description": "Patient vitals at the time of visit.",
            "display_order": 1,
            "is_collapsed": False,
            "fields": [
                {
                    "field_key": "bp",
                    "field_type": "text",
                    "label": "Blood Pressure (mmHg)",
                    "display_order": 1,
                    "config": {"placeholder": "e.g. 120/80"},
                },
                {
                    "field_key": "pulse",
                    "field_type": "number",
                    "label": "Pulse (bpm)",
                    "display_order": 2,
                    "config": {"min": 20, "max": 300},
                },
                {
                    "field_key": "spo2",
                    "field_type": "number",
                    "label": "SPO2 (%)",
                    "display_order": 3,
                    "config": {"min": 50, "max": 100},
                },
                {
                    "field_key": "temperature",
                    "field_type": "number",
                    "label": "Temperature (°F)",
                    "display_order": 4,
                    "config": {"min": 90, "max": 110, "step": 0.1},
                },
                {
                    "field_key": "weight",
                    "field_type": "number",
                    "label": "Weight (kg)",
                    "display_order": 5,
                    "config": {"min": 1, "max": 300, "step": 0.1},
                },
            ],
        },
        {
            "code": "opd_complaints",
            "title": "Chief Complaints",
            "description": "Presenting complaints and brief history.",
            "display_order": 2,
            "is_collapsed": False,
            "fields": [
                {
                    "field_key": "chief_complaints",
                    "field_type": "multiselect",
                    "label": "Chief Complaints",
                    "display_order": 1,
                    "config": {"picklist_code": "chief_complaints", "allow_new_items": True},
                },
                {
                    "field_key": "complaints_detail",
                    "field_type": "textarea",
                    "label": "Complaint Details / Duration",
                    "display_order": 2,
                    "config": {"rows": 3, "placeholder": "Describe onset, duration, character…"},
                },
                {
                    "field_key": "past_history",
                    "field_type": "textarea",
                    "label": "Past / Relevant History",
                    "display_order": 3,
                    "config": {"rows": 2},
                },
            ],
        },
        {
            "code": "opd_examination",
            "title": "Examination Findings",
            "description": "General and systemic examination.",
            "display_order": 3,
            "is_collapsed": False,
            "fields": [
                {
                    "field_key": "general_examination",
                    "field_type": "textarea",
                    "label": "General Examination",
                    "display_order": 1,
                    "config": {"rows": 3},
                },
                {
                    "field_key": "systemic_examination",
                    "field_type": "textarea",
                    "label": "Systemic Examination",
                    "display_order": 2,
                    "config": {"rows": 3},
                },
            ],
        },
        {
            "code": "opd_diagnosis",
            "title": "Diagnosis",
            "description": "Provisional and/or final diagnosis.",
            "display_order": 4,
            "is_collapsed": False,
            "fields": [
                {
                    "field_key": "diagnosis",
                    "field_type": "textarea",
                    "label": "Diagnosis",
                    "display_order": 1,
                    "is_required": True,
                    "config": {"rows": 2, "placeholder": "e.g. Viral Fever with Gastritis"},
                },
                {
                    "field_key": "icd_code",
                    "field_type": "text",
                    "label": "ICD-10 Code",
                    "display_order": 2,
                    "config": {"placeholder": "e.g. A90, J06.9"},
                },
            ],
        },
        {
            "code": "opd_prescription",
            "title": "Prescription",
            "description": "Medications prescribed. List each drug with dosage, route, frequency and duration.",
            "display_order": 5,
            "is_collapsed": False,
            "fields": [
                {
                    "field_key": "prescription_notes",
                    "field_type": "textarea",
                    "label": "Prescription",
                    "display_order": 1,
                    "config": {
                        "rows": 10,
                        "placeholder": "1. DRUG NAME - Dosage - Route - Frequency - Duration\n2. …",
                    },
                },
            ],
        },
        {
            "code": "opd_investigations",
            "title": "Investigations",
            "description": "Tests prescribed to the patient.",
            "display_order": 6,
            "is_collapsed": False,
            "fields": [
                {
                    "field_key": "investigations",
                    "field_type": "multiselect",
                    "label": "Tests Prescribed",
                    "display_order": 1,
                    "config": {"picklist_code": "lab_investigations", "allow_new_items": True},
                },
                {
                    "field_key": "investigation_notes",
                    "field_type": "textarea",
                    "label": "Investigation Notes",
                    "display_order": 2,
                    "config": {"rows": 2},
                },
            ],
        },
        {
            "code": "opd_advice_followup",
            "title": "Advice & Follow-up",
            "description": "Advice given and next visit details.",
            "display_order": 7,
            "is_collapsed": False,
            "fields": [
                {
                    "field_key": "advice",
                    "field_type": "multiselect",
                    "label": "Advice",
                    "display_order": 1,
                    "config": {"picklist_code": "discharge_advice", "allow_new_items": True},
                },
                {
                    "field_key": "advice_notes",
                    "field_type": "textarea",
                    "label": "Additional Advice / Instructions",
                    "display_order": 2,
                    "config": {"rows": 2},
                },
                {
                    "field_key": "next_visit_date",
                    "field_type": "date",
                    "label": "Next Visit Date",
                    "display_order": 3,
                },
                {
                    "field_key": "referral_to",
                    "field_type": "text",
                    "label": "Referral To (if any)",
                    "display_order": 4,
                    "config": {"placeholder": "e.g. Cardiologist, ENT"},
                },
            ],
        },
    ],
}

SYSTEM_IPD_ADMISSION = {
    "code": "system_ipd_admission",
    "name": "IPD Admission Form",
    "description": "Standard IPD admission form capturing patient details, guardian info, admission & discharge summary, diagnosis, and MLC information.",
    "version": 1,
    "status": "published",
    "is_system": True,
    "entity_type": "ipd_admission",
    "config": {"layout": "vertical"},
    "sections": [
        {
            "code": "admission_patient_info",
            "title": "Patient Information",
            "description": "Key patient identifiers and demographics.",
            "display_order": 1,
            "is_collapsed": False,
            "fields": [
                {"field_key": "height_cm", "field_type": "number", "label": "Height (cm)", "display_order": 1, "config": {"min": 30, "max": 250}},
                {"field_key": "weight_kg", "field_type": "number", "label": "Weight (kg)", "display_order": 2, "config": {"min": 1, "max": 300, "step": 0.1}},
                {"field_key": "bmi", "field_type": "calculated", "label": "BMI", "display_order": 3, "is_read_only": True, "config": {"formula": "weight_kg / ((height_cm / 100) ** 2)"}},
                {"field_key": "marital_status", "field_type": "text", "label": "Marital Status", "display_order": 4},
                {"field_key": "aadhar_no", "field_type": "text", "label": "Aadhar No.", "display_order": 5},
                {"field_key": "patient_category", "field_type": "text", "label": "Patient Category", "display_order": 6, "config": {"placeholder": "e.g. Patient Paying, BPL, CGHS"}},
                {"field_key": "referred_by", "field_type": "text", "label": "Referred By", "display_order": 7, "config": {"placeholder": "Self / Doctor Name / Hospital"}},
            ],
        },
        {
            "code": "admission_guardian_info",
            "title": "Guardian / Relative Information",
            "description": "Next of kin or guardian details.",
            "display_order": 2,
            "is_collapsed": False,
            "fields": [
                {"field_key": "guardian_name", "field_type": "text", "label": "Guardian Name", "display_order": 1},
                {"field_key": "guardian_relation", "field_type": "text", "label": "Relation to Patient", "display_order": 2},
                {"field_key": "guardian_contact", "field_type": "text", "label": "Guardian Contact No.", "display_order": 3},
                {"field_key": "guardian_address", "field_type": "textarea", "label": "Guardian Address", "display_order": 4, "config": {"rows": 2}},
            ],
        },
        {
            "code": "admission_details",
            "title": "Admission Details",
            "description": "Bed, room and admission details.",
            "display_order": 3,
            "is_collapsed": False,
            "fields": [
                {"field_key": "bed_no", "field_type": "text", "label": "Bed No.", "display_order": 1},
                {"field_key": "ward_room", "field_type": "text", "label": "Ward / Room", "display_order": 2},
                {"field_key": "admission_complaints", "field_type": "textarea", "label": "Complaints at Admission", "display_order": 3, "config": {"rows": 3}},
            ],
        },
        {
            "code": "admission_discharge_summary",
            "title": "Discharge Summary",
            "description": "Filled at the time of discharge.",
            "display_order": 4,
            "is_collapsed": True,
            "fields": [
                {"field_key": "discharge_type", "field_type": "picklist", "label": "Discharge Type", "display_order": 1, "config": {"picklist_code": "discharge_type"}},
                {"field_key": "condition_at_discharge", "field_type": "picklist", "label": "Condition at Discharge", "display_order": 2, "config": {"picklist_code": "condition_at_discharge"}},
                {"field_key": "final_diagnosis", "field_type": "textarea", "label": "Final Diagnosis", "display_order": 3, "config": {"rows": 3}},
                {"field_key": "icd_code", "field_type": "text", "label": "ICD-10 Code", "display_order": 4},
                {"field_key": "treatment_given", "field_type": "textarea", "label": "Treatment Given", "display_order": 5, "config": {"rows": 3}},
                {"field_key": "discharge_instructions", "field_type": "textarea", "label": "Discharge Instructions", "display_order": 6, "config": {"rows": 3}},
                {"field_key": "room_transfers", "field_type": "textarea", "label": "Room Transfer Details", "display_order": 7, "config": {"rows": 2}},
            ],
        },
        {
            "code": "admission_mlc",
            "title": "Medico Legal Case (MLC)",
            "description": "Fill only if this is a medico-legal case.",
            "display_order": 5,
            "is_collapsed": True,
            "fields": [
                {"field_key": "is_mlc", "field_type": "boolean", "label": "Is MLC?", "display_order": 1, "default_value": False},
                {"field_key": "mlc_no", "field_type": "text", "label": "MLC No.", "display_order": 2},
                {"field_key": "constable_name", "field_type": "text", "label": "Constable Name", "display_order": 3},
                {"field_key": "police_station", "field_type": "text", "label": "Police Station", "display_order": 4},
                {"field_key": "police_buckle_no", "field_type": "text", "label": "Police Buckle No.", "display_order": 5},
                {"field_key": "pt_identification_remark", "field_type": "textarea", "label": "Patient Identification Remark", "display_order": 6, "config": {"rows": 2}},
            ],
        },
    ],
}

SYSTEM_IPD_MONITORING_ENTRY = {
    "code": "system_ipd_monitoring_entry",
    "name": "IPD Monitoring Chart Entry",
    "description": "One entry = one time-slot row in the monitoring chart. Record vitals, intake, output, BSL and nursing procedure per reading.",
    "version": 1,
    "status": "published",
    "is_system": True,
    "entity_type": "ipd_admission",
    "config": {"layout": "horizontal", "allow_multiple_records": True},
    "sections": [
        {
            "code": "monitoring_time",
            "title": "Time & Date",
            "display_order": 1,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "entry_datetime", "field_type": "datetime", "label": "Date & Time", "display_order": 1, "is_required": True},
            ],
        },
        {
            "code": "monitoring_vitals",
            "title": "Vitals",
            "display_order": 2,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "pulse", "field_type": "number", "label": "Pulse / min", "display_order": 1, "config": {"min": 0, "max": 300}},
                {"field_key": "bp", "field_type": "text", "label": "BP (mmHg)", "display_order": 2, "config": {"placeholder": "120/80"}},
                {"field_key": "temperature_f", "field_type": "number", "label": "Temp (°F)", "display_order": 3, "config": {"min": 90, "max": 110, "step": 0.1}},
                {"field_key": "resp_rate", "field_type": "number", "label": "Resp / min", "display_order": 4, "config": {"min": 0, "max": 80}},
                {"field_key": "cvp", "field_type": "number", "label": "CVP (cms H2O)", "display_order": 5, "config": {"step": 0.1}},
                {"field_key": "spo2", "field_type": "number", "label": "SPO2 (%)", "display_order": 6, "config": {"min": 0, "max": 100}},
                {"field_key": "o2_lit_min", "field_type": "number", "label": "O2 (Lit/min)", "display_order": 7, "config": {"step": 0.5}},
            ],
        },
        {
            "code": "monitoring_intake",
            "title": "Intake (ml)",
            "display_order": 3,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "intake_oral_ml", "field_type": "number", "label": "Oral (ml)", "display_order": 1, "config": {"min": 0}},
                {"field_key": "intake_rt_ml", "field_type": "number", "label": "R.T. (ml)", "display_order": 2, "config": {"min": 0}},
                {"field_key": "intake_iv_ml", "field_type": "number", "label": "IV Fluids (ml)", "display_order": 3, "config": {"min": 0}},
            ],
        },
        {
            "code": "monitoring_output",
            "title": "Output (ml)",
            "display_order": 4,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "output_rta_ml", "field_type": "number", "label": "R.T.A. (ml)", "display_order": 1, "config": {"min": 0}},
                {"field_key": "output_drain_ml", "field_type": "number", "label": "Drain (ml)", "display_order": 2, "config": {"min": 0}},
                {"field_key": "output_urine_ml", "field_type": "number", "label": "Urine (ml)", "display_order": 3, "config": {"min": 0}},
            ],
        },
        {
            "code": "monitoring_bsl_procedure",
            "title": "BSL & Procedure",
            "display_order": 5,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "bsl", "field_type": "number", "label": "BSL (mg/dL)", "display_order": 1, "config": {"min": 0}},
                {"field_key": "procedure_done", "field_type": "textarea", "label": "Procedure / Notes", "display_order": 2, "config": {"rows": 2}},
                {"field_key": "nurse_sign", "field_type": "text", "label": "Nurse Signature / Name", "display_order": 3},
            ],
        },
    ],
}

SYSTEM_IPD_MEDICATION_CHART = {
    "code": "system_ipd_medication_chart",
    "name": "IPD Medication Chart",
    "description": "One record = one medication order. Tracks drug, dosage, route, frequency and nurse administration signatures.",
    "version": 1,
    "status": "published",
    "is_system": True,
    "entity_type": "ipd_admission",
    "config": {"layout": "vertical", "allow_multiple_records": True},
    "sections": [
        {
            "code": "med_order",
            "title": "Medication Order",
            "display_order": 1,
            "is_collapsed": False,
            "description": "Doctor prescribes — fill Medication through Doctor Sign.",
            "fields": [
                {"field_key": "medication_name", "field_type": "text", "label": "Medication Name (CAPITALS)", "display_order": 1, "is_required": True, "config": {"placeholder": "e.g. AMOXICILLIN"}},
                {"field_key": "dosage", "field_type": "text", "label": "Dosage", "display_order": 2, "is_required": True, "config": {"placeholder": "e.g. 500 MG"}},
                {"field_key": "route", "field_type": "picklist", "label": "Route", "display_order": 3, "config": {"picklist_code": "route_of_administration"}},
                {"field_key": "frequency", "field_type": "picklist", "label": "Frequency", "display_order": 4, "config": {"picklist_code": "drug_frequency"}},
                {"field_key": "timing", "field_type": "picklist", "label": "Timing", "display_order": 5, "config": {"picklist_code": "drug_timing"}},
                {"field_key": "start_date", "field_type": "date", "label": "Start Date", "display_order": 6},
                {"field_key": "duration_days", "field_type": "number", "label": "Duration (days)", "display_order": 7, "config": {"min": 1}},
                {"field_key": "doctor_sign", "field_type": "text", "label": "Doctor Sign / Name", "display_order": 8},
            ],
        },
        {
            "code": "med_administration",
            "title": "Administration Record",
            "display_order": 2,
            "is_collapsed": False,
            "description": "Nurse fills for each administration time slot.",
            "fields": [
                {"field_key": "admin_time_1", "field_type": "text", "label": "Time 1", "display_order": 1},
                {"field_key": "nurse_sign_1", "field_type": "text", "label": "Nurse Sign 1", "display_order": 2},
                {"field_key": "admin_time_2", "field_type": "text", "label": "Time 2", "display_order": 3},
                {"field_key": "nurse_sign_2", "field_type": "text", "label": "Nurse Sign 2", "display_order": 4},
                {"field_key": "admin_time_3", "field_type": "text", "label": "Time 3", "display_order": 5},
                {"field_key": "nurse_sign_3", "field_type": "text", "label": "Nurse Sign 3", "display_order": 6},
                {"field_key": "admin_time_4", "field_type": "text", "label": "Time 4", "display_order": 7},
                {"field_key": "nurse_sign_4", "field_type": "text", "label": "Nurse Sign 4", "display_order": 8},
                {"field_key": "admin_notes", "field_type": "textarea", "label": "Administration Notes", "display_order": 9, "config": {"rows": 2}},
            ],
        },
    ],
}

SYSTEM_IPD_NURSING_NOTES = {
    "code": "system_ipd_nursing_notes",
    "name": "Nurses Continuation Sheet",
    "description": "Ongoing nursing notes and observations. One record per entry.",
    "version": 1,
    "status": "published",
    "is_system": True,
    "entity_type": "ipd_admission",
    "config": {"layout": "vertical", "allow_multiple_records": True},
    "sections": [
        {
            "code": "nursing_entry",
            "title": "Nursing Note",
            "display_order": 1,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "entry_datetime", "field_type": "datetime", "label": "Date & Time", "display_order": 1, "is_required": True},
                {"field_key": "bed_no", "field_type": "text", "label": "Bed No.", "display_order": 2},
                {"field_key": "weight_kg", "field_type": "number", "label": "Weight (kg)", "display_order": 3, "config": {"min": 0, "step": 0.1}},
                {"field_key": "nursing_notes", "field_type": "textarea", "label": "Nursing Notes / Observations", "display_order": 4, "is_required": True, "config": {"rows": 8}},
                {"field_key": "nurse_sign", "field_type": "text", "label": "Nurse Signature / Name", "display_order": 5},
            ],
        },
    ],
}

SYSTEM_IPD_INCIDENCE_REGISTER = {
    "code": "system_ipd_incidence_register",
    "name": "Incidence Register",
    "description": "NABH-mandated incidence reporting for IPD patients. Records adverse events and safety incidents.",
    "version": 1,
    "status": "published",
    "is_system": True,
    "entity_type": "ipd_admission",
    "config": {"layout": "vertical"},
    "sections": [
        {
            "code": "incidence_medication_error",
            "title": "Medication Error",
            "display_order": 1,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "medication_error", "field_type": "boolean", "label": "Is there any medication error?", "display_order": 1, "default_value": False},
                {"field_key": "medication_error_detail", "field_type": "textarea", "label": "Medication Error Details", "display_order": 2, "config": {"rows": 2}},
            ],
        },
        {
            "code": "incidence_needle_stick",
            "title": "Needle Stick Injury",
            "display_order": 2,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "needle_stick_injury", "field_type": "boolean", "label": "Is there any needle stick injury?", "display_order": 1, "default_value": False},
                {"field_key": "needle_stick_detail", "field_type": "textarea", "label": "Needle Stick Injury Details", "display_order": 2, "config": {"rows": 2}},
            ],
        },
        {
            "code": "incidence_blood_transfusion",
            "title": "Blood Transfusion",
            "display_order": 3,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "blood_transfusion_done", "field_type": "boolean", "label": "Any blood transfusion for this patient?", "display_order": 1, "default_value": False},
                {"field_key": "blood_transfusion_reaction", "field_type": "boolean", "label": "Any transfusion reaction?", "display_order": 2, "default_value": False},
                {"field_key": "blood_transfusion_detail", "field_type": "textarea", "label": "Transfusion Details / Reaction Notes", "display_order": 3, "config": {"rows": 2}},
            ],
        },
        {
            "code": "incidence_urinary_cath",
            "title": "Urinary Catheterization",
            "display_order": 4,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "urinary_cath_done", "field_type": "boolean", "label": "Is urinary catheterization processed?", "display_order": 1, "default_value": False},
                {"field_key": "urinary_cath_detail", "field_type": "textarea", "label": "Catheterization Details", "display_order": 2, "config": {"rows": 2}},
            ],
        },
        {
            "code": "incidence_vulnerability",
            "title": "Vulnerability Assessment",
            "display_order": 5,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "vulnerability_assessment_done", "field_type": "boolean", "label": "Is there any Vulnerability Assessment?", "display_order": 1, "default_value": False},
                {"field_key": "vulnerability_detail", "field_type": "textarea", "label": "Vulnerability Assessment Details", "display_order": 2, "config": {"rows": 2}},
            ],
        },
        {
            "code": "incidence_surgery",
            "title": "Surgery / OR Procedure",
            "display_order": 6,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "surgery_done", "field_type": "boolean", "label": "Performed any surgery or procedure?", "display_order": 1, "default_value": False},
                {"field_key": "operation_cancelled", "field_type": "boolean", "label": "Operation Cancelled?", "display_order": 2, "default_value": False},
                {"field_key": "wrong_patient_surgery", "field_type": "boolean", "label": "Wrong Patient Surgery?", "display_order": 3, "default_value": False},
                {"field_key": "wrong_site_surgery", "field_type": "boolean", "label": "Wrong Site Surgery?", "display_order": 4, "default_value": False},
                {"field_key": "post_op_death", "field_type": "boolean", "label": "Post Op Death?", "display_order": 5, "default_value": False},
                {"field_key": "repeat_surgery", "field_type": "boolean", "label": "Repeat Surgery?", "display_order": 6, "default_value": False},
                {"field_key": "pcml_case", "field_type": "boolean", "label": "PCML Case?", "display_order": 7, "default_value": False},
                {"field_key": "surgery_detail", "field_type": "textarea", "label": "Surgery / Procedure Details", "display_order": 8, "config": {"rows": 3}},
            ],
        },
        {
            "code": "incidence_bed_sore",
            "title": "Bed Sore",
            "display_order": 7,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "bed_sore", "field_type": "boolean", "label": "Is bed sore after admission?", "display_order": 1, "default_value": False},
                {"field_key": "bed_sore_detail", "field_type": "textarea", "label": "Bed Sore Details", "display_order": 2, "config": {"rows": 2}},
            ],
        },
        {
            "code": "incidence_fall",
            "title": "Incidence of Fall",
            "display_order": 8,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "fall_occurred", "field_type": "boolean", "label": "Any incidence of fall?", "display_order": 1, "default_value": False},
                {"field_key": "fall_detail", "field_type": "textarea", "label": "Fall Incidence Details", "display_order": 2, "config": {"rows": 2}},
            ],
        },
        {
            "code": "incidence_adr",
            "title": "Adverse Drug Reaction / Event",
            "display_order": 9,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "adr_occurred", "field_type": "boolean", "label": "Adverse Drug Reaction or Event?", "display_order": 1, "default_value": False},
                {"field_key": "redose_given", "field_type": "boolean", "label": "Re-dose?", "display_order": 2, "default_value": False},
                {"field_key": "readmission_14_days", "field_type": "boolean", "label": "Patient readmission within 14 days?", "display_order": 3, "default_value": False},
                {"field_key": "return_to_ot_7_days", "field_type": "boolean", "label": "Patient return to OT within 7 days?", "display_order": 4, "default_value": False},
                {"field_key": "adr_detail", "field_type": "textarea", "label": "ADR / Event Details", "display_order": 5, "config": {"rows": 3}},
            ],
        },
        {
            "code": "incidence_summary",
            "title": "Sentinel & Other Events",
            "display_order": 10,
            "is_collapsed": False,
            "description": "",
            "fields": [
                {"field_key": "sentinel_event", "field_type": "boolean", "label": "Is Sentinel Event?", "display_order": 1, "default_value": False},
                {"field_key": "return_to_icu_7_days", "field_type": "boolean", "label": "Patient return to ICU within 7 days?", "display_order": 2, "default_value": False},
                {"field_key": "return_to_emergency_7_days", "field_type": "boolean", "label": "Patient return to Emergency within 7 days?", "display_order": 3, "default_value": False},
                {"field_key": "infection_outbreak", "field_type": "boolean", "label": "Any Infection Out Break?", "display_order": 4, "default_value": False},
                {"field_key": "nosocomial_infection", "field_type": "boolean", "label": "Any Nosocomial Infection?", "display_order": 5, "default_value": False},
                {"field_key": "identification_error", "field_type": "boolean", "label": "Any Identification Error?", "display_order": 6, "default_value": False},
                {"field_key": "hypoglycemia", "field_type": "boolean", "label": "Is Hypoglycemia (BSL < 70 mg/dl)?", "display_order": 7, "default_value": False},
                {"field_key": "discrepancy_sponge_gauze", "field_type": "boolean", "label": "Is Discrepancy in Sponge/Gauze Count?", "display_order": 8, "default_value": False},
                {"field_key": "cautery_burns", "field_type": "boolean", "label": "Is Cautery Burns?", "display_order": 9, "default_value": False},
                {"field_key": "needle_inside_porta_cath", "field_type": "boolean", "label": "Is Needle left inside Porta Cath?", "display_order": 10, "default_value": False},
                {"field_key": "acute_limb_ischemia", "field_type": "boolean", "label": "Acute Limb Ischemia?", "display_order": 11, "default_value": False},
                {"field_key": "other_event_detail", "field_type": "textarea", "label": "Other Event Details / Remarks", "display_order": 12, "config": {"rows": 3}},
            ],
        },
    ],
}

SYSTEM_IPD_MRD_CHECKLIST = {
    "code": "system_ipd_mrd_checklist",
    "name": "MRD Document Checklist",
    "description": "Medical Records Department document checklist. Tracks completeness of all IPD file documents at the time of discharge.",
    "version": 1,
    "status": "published",
    "is_system": True,
    "entity_type": "ipd_admission",
    "config": {"layout": "vertical"},
    "sections": [
        {
            "code": "mrd_ipd_documents",
            "title": "IPD Clinical Documents",
            "display_order": 1,
            "is_collapsed": False,
            "description": "Core IPD admission and clinical documents.",
            "fields": [
                {"field_key": "ipd1_admission_consent", "field_type": "picklist", "label": "IPD 1 — Admission Registration, General Consent & High Risk Consent", "display_order": 1, "config": {"picklist_code": "yes_no"}},
                {"field_key": "ipd2_icu_admission_consent", "field_type": "picklist", "label": "IPD 2 — ICU Admission Consent Form", "display_order": 2, "config": {"picklist_code": "yes_no"}},
                {"field_key": "ipd3_initial_assessment_doctors", "field_type": "picklist", "label": "IPD 3 — Initial Assessment Doctors (2 Pages)", "display_order": 3, "config": {"picklist_code": "yes_no"}},
                {"field_key": "ipd4_treatment_sheet", "field_type": "picklist", "label": "IPD 4 — Treatment Sheet Ward RMO", "display_order": 4, "config": {"picklist_code": "yes_no"}},
                {"field_key": "ipd5_reassessment_doctors", "field_type": "picklist", "label": "IPD 5 — Reassessment for Doctors", "display_order": 5, "config": {"picklist_code": "yes_no"}},
                {"field_key": "ipd6_initial_assessment_nursing", "field_type": "picklist", "label": "IPD 6 — Initial Assessment Nursing", "display_order": 6, "config": {"picklist_code": "yes_no"}},
                {"field_key": "ipd7_nurses_continuation", "field_type": "picklist", "label": "IPD 7 — Nurses Continuation Sheet", "display_order": 7, "config": {"picklist_code": "yes_no"}},
                {"field_key": "ipd8_monitoring_chart", "field_type": "picklist", "label": "IPD 8 — Monitoring Chart", "display_order": 8, "config": {"picklist_code": "yes_no"}},
                {"field_key": "ipd9_intake_output_chart", "field_type": "picklist", "label": "IPD 9 — Intake Output Chart", "display_order": 9, "config": {"picklist_code": "yes_no"}},
                {"field_key": "ipd10_graph_growth_chart", "field_type": "picklist", "label": "IPD 10 — Graph of Growth Chart", "display_order": 10, "config": {"picklist_code": "yes_no"}},
            ],
        },
        {
            "code": "mrd_surgery_documents",
            "title": "Surgery / OT Documents",
            "display_order": 2,
            "is_collapsed": False,
            "description": "Required only for surgical patients.",
            "fields": [
                {"field_key": "sx1_anesthesia_consent", "field_type": "picklist", "label": "SX 1 — Anesthesia Consent (2 Pages)", "display_order": 1, "config": {"picklist_code": "yes_no"}},
                {"field_key": "sx2_inform_consent_surgery", "field_type": "picklist", "label": "SX 2 — Inform Consent for Surgery (2 Pages)", "display_order": 2, "config": {"picklist_code": "yes_no"}},
                {"field_key": "sx3_pre_op_intra_op_order", "field_type": "picklist", "label": "SX 3 — Pre-op and Intra-op Order of Surgeon", "display_order": 3, "config": {"picklist_code": "yes_no"}},
                {"field_key": "sx4_post_op_order", "field_type": "picklist", "label": "SX 4 — Post Op Order + 1st Post Op Day", "display_order": 4, "config": {"picklist_code": "yes_no"}},
                {"field_key": "sx5_pre_op_checklist", "field_type": "picklist", "label": "SX 5 — Pre-op Checklist + Surgical Safety Checklist", "display_order": 5, "config": {"picklist_code": "yes_no"}},
                {"field_key": "sx6_anesthesia_records", "field_type": "picklist", "label": "SX 6 — Anesthesia Records (2 Pages)", "display_order": 6, "config": {"picklist_code": "yes_no"}},
            ],
        },
        {
            "code": "mrd_general_documents",
            "title": "General Documents",
            "display_order": 3,
            "is_collapsed": False,
            "description": "General documents applicable to all IPD admissions.",
            "fields": [
                {"field_key": "gen1_procedure_consent", "field_type": "picklist", "label": "GEN 1 — Procedure Consent", "display_order": 1, "config": {"picklist_code": "yes_no"}},
                {"field_key": "gen2_bt_consent", "field_type": "picklist", "label": "GEN 2 — BT Consent", "display_order": 2, "config": {"picklist_code": "yes_no"}},
                {"field_key": "gen3_dama_consent", "field_type": "picklist", "label": "GEN 3 — DAMA Consent", "display_order": 3, "config": {"picklist_code": "yes_no"}},
                {"field_key": "gen4_transfer_referral", "field_type": "picklist", "label": "GEN 4 — Transfer / Referral Form", "display_order": 4, "config": {"picklist_code": "yes_no"}},
                {"field_key": "gen5_mlc_form", "field_type": "picklist", "label": "GEN 5 — MLC Form", "display_order": 5, "config": {"picklist_code": "yes_no"}},
                {"field_key": "gen6_trauma_sheet", "field_type": "picklist", "label": "GEN 6 — Trauma Sheet", "display_order": 6, "config": {"picklist_code": "yes_no"}},
                {"field_key": "gen7_discharge_card", "field_type": "picklist", "label": "GEN 7 — Discharge Card", "display_order": 7, "config": {"picklist_code": "yes_no"}},
                {"field_key": "gen8_mrd_checklist", "field_type": "picklist", "label": "GEN 8 — MRD Checklist", "display_order": 8, "config": {"picklist_code": "yes_no"}},
            ],
        },
        {
            "code": "mrd_misc_documents",
            "title": "Additional / Miscellaneous Documents",
            "display_order": 4,
            "is_collapsed": True,
            "description": "Lab reports, X-rays, USG, and other records.",
            "fields": [
                {"field_key": "gen0_hrm_high_risk_medication", "field_type": "picklist", "label": "GEN 0 — HRM High Risk Medication", "display_order": 1, "config": {"picklist_code": "yes_no"}},
                {"field_key": "gen10_bill_or_hospital", "field_type": "picklist", "label": "GEN 10 — Bill or Hospital", "display_order": 2, "config": {"picklist_code": "yes_no"}},
                {"field_key": "gen11_document_mjpiay", "field_type": "picklist", "label": "GEN 11 — Document of MJPIAY", "display_order": 3, "config": {"picklist_code": "yes_no"}},
                {"field_key": "gen12_death_certificate", "field_type": "picklist", "label": "GEN 12 — Death Certificate", "display_order": 4, "config": {"picklist_code": "yes_no"}},
                {"field_key": "misc1_lab_reports", "field_type": "picklist", "label": "MISC 1 — LAB Reports", "display_order": 5, "config": {"picklist_code": "yes_no"}},
                {"field_key": "misc2_xray_report", "field_type": "picklist", "label": "MISC 2 — X-ray Report", "display_order": 6, "config": {"picklist_code": "yes_no"}},
                {"field_key": "misc3_usg_reports", "field_type": "picklist", "label": "MISC 3 — USG Reports", "display_order": 7, "config": {"picklist_code": "yes_no"}},
                {"field_key": "misc4_other_reports", "field_type": "picklist", "label": "MISC 4 — Other Reports", "display_order": 8, "config": {"picklist_code": "yes_no"}},
            ],
        },
        {
            "code": "mrd_filing_info",
            "title": "MRD Filing Information",
            "display_order": 5,
            "is_collapsed": True,
            "description": "Physical file location in the MRD.",
            "fields": [
                {"field_key": "diagnosis", "field_type": "textarea", "label": "Diagnosis", "display_order": 1, "config": {"rows": 2}},
                {"field_key": "icd_code", "field_type": "text", "label": "ICD Code", "display_order": 2},
                {"field_key": "filing_date", "field_type": "date", "label": "Date", "display_order": 3},
                {"field_key": "scanned_copy_no", "field_type": "text", "label": "Scanned Copy No.", "display_order": 4},
                {"field_key": "rack_no", "field_type": "text", "label": "Rack No.", "display_order": 5},
                {"field_key": "shelf_no", "field_type": "text", "label": "Shelf No.", "display_order": 6},
                {"field_key": "location", "field_type": "text", "label": "Location", "display_order": 7},
                {"field_key": "mrd_remarks", "field_type": "textarea", "label": "Medical Records Department Remarks", "display_order": 8, "config": {"rows": 2}},
            ],
        },
    ],
}

SYSTEM_IPD_DISCHARGE_CHECKLIST = {
    "code": "system_ipd_discharge_checklist",
    "name": "Discharge Safety Checklist",
    "description": "Pre-discharge safety and quality checklist (MRD Check). Completed by Ward RMO and Nursing Incharge before patient discharge.",
    "version": 1,
    "status": "published",
    "is_system": True,
    "entity_type": "ipd_admission",
    "config": {"layout": "vertical"},
    "sections": [
        {
            "code": "discharge_safety_checks",
            "title": "Patient Safety Checks",
            "display_order": 1,
            "is_collapsed": False,
            "description": "Adverse event screening before discharge.",
            "fields": [
                {"field_key": "return_to_icu_7_days", "field_type": "picklist", "label": "Patient return to ICU within 7 days?", "display_order": 1, "config": {"picklist_code": "yes_no"}},
                {"field_key": "return_to_emergency_7_days", "field_type": "picklist", "label": "Patient return to Emergency within 7 days?", "display_order": 2, "config": {"picklist_code": "yes_no"}},
                {"field_key": "infection_outbreak", "field_type": "picklist", "label": "Any Infection Out Break?", "display_order": 3, "config": {"picklist_code": "yes_no"}},
                {"field_key": "nosocomial_infection", "field_type": "picklist", "label": "Any Nosocomial Infection?", "display_order": 4, "config": {"picklist_code": "yes_no"}},
                {"field_key": "identification_error", "field_type": "picklist", "label": "Any Identification Error?", "display_order": 5, "config": {"picklist_code": "yes_no"}},
                {"field_key": "hypoglycemia", "field_type": "picklist", "label": "Is Hypoglycemia (BSL < 70 mg/dl)?", "display_order": 6, "config": {"picklist_code": "yes_no"}},
                {"field_key": "acute_limb_ischemia", "field_type": "picklist", "label": "Acute Limb Ischemia?", "display_order": 7, "config": {"picklist_code": "yes_no"}},
                {"field_key": "cautery_burns", "field_type": "picklist", "label": "Is Cautery Burns?", "display_order": 8, "config": {"picklist_code": "yes_no"}},
                {"field_key": "discrepancy_sponge_gauze", "field_type": "picklist", "label": "Is Discrepancy in Sponge/Gauge Count?", "display_order": 9, "config": {"picklist_code": "yes_no"}},
                {"field_key": "needle_inside_porta_cath", "field_type": "picklist", "label": "Is Needle left inside Porta Cath?", "display_order": 10, "config": {"picklist_code": "yes_no"}},
                {"field_key": "sentinel_event", "field_type": "picklist", "label": "Is Sentinel Events?", "display_order": 11, "config": {"picklist_code": "yes_no"}},
            ],
        },
        {
            "code": "discharge_mrd_checks",
            "title": "MRD Checklist",
            "display_order": 2,
            "is_collapsed": False,
            "description": "Document and administrative checks before closing the file.",
            "fields": [
                {"field_key": "missing_clinical_records", "field_type": "picklist", "label": "Any missing clinical records?", "display_order": 1, "config": {"picklist_code": "yes_no"}},
                {"field_key": "discharge_status", "field_type": "picklist", "label": "Discharge Status", "display_order": 2, "config": {"picklist_code": "discharge_type"}},
                {"field_key": "discharge_card_attached", "field_type": "picklist", "label": "Discharge Card Attached?", "display_order": 3, "config": {"picklist_code": "yes_no"}},
                {"field_key": "all_consents_proper", "field_type": "picklist", "label": "All Consents Proper?", "display_order": 4, "config": {"picklist_code": "yes_no"}},
                {"field_key": "feedback_collected", "field_type": "picklist", "label": "Feedback Collected?", "display_order": 5, "config": {"picklist_code": "yes_no"}},
                {"field_key": "icd_coding_done", "field_type": "picklist", "label": "ICD Coding Done?", "display_order": 6, "config": {"picklist_code": "yes_no"}},
                {"field_key": "feedback_negative_remark", "field_type": "picklist", "label": "Feedback Negative Remark?", "display_order": 7, "config": {"picklist_code": "yes_no"}},
                {"field_key": "ward_rmo_sign", "field_type": "text", "label": "Ward RMO Signature / Name", "display_order": 8},
                {"field_key": "nursing_incharge_sign", "field_type": "text", "label": "Nursing Incharge Signature / Name", "display_order": 9},
                {"field_key": "billing_sign", "field_type": "text", "label": "Billing Signature / Name", "display_order": 10},
            ],
        },
    ],
}

# All new forms in seed order
NEW_SYSTEM_FORMS = [
    SYSTEM_OPD_CONSULTATION,
    SYSTEM_IPD_ADMISSION,
    SYSTEM_IPD_MONITORING_ENTRY,
    SYSTEM_IPD_MEDICATION_CHART,
    SYSTEM_IPD_NURSING_NOTES,
    SYSTEM_IPD_INCIDENCE_REGISTER,
    SYSTEM_IPD_MRD_CHECKLIST,
    SYSTEM_IPD_DISCHARGE_CHECKLIST,
]

# Codes to delete on reverse migration
_NEW_FORM_CODES = [f["code"] for f in NEW_SYSTEM_FORMS]
_NEW_PICKLIST_CODES = [p["code"] for p in NEW_SYSTEM_PICKLISTS]


# ---------------------------------------------------------------------------
# Helper functions (self-contained — do NOT import from management commands)
# ---------------------------------------------------------------------------

def _seed_picklists(apps, tenant_id, picklist_defs):
    ClinicalPicklist = apps.get_model("clinical", "ClinicalPicklist")
    ClinicalPicklistItem = apps.get_model("clinical", "ClinicalPicklistItem")
    picklist_map = {}
    for pd in picklist_defs:
        pl, _ = ClinicalPicklist.objects.get_or_create(
            tenant_id=tenant_id,
            code=pd["code"],
            defaults={
                "name": pd["name"],
                "description": pd["description"],
                "is_system": pd["is_system"],
            },
        )
        picklist_map[pd["code"]] = pl
        for item in pd["items"]:
            ClinicalPicklistItem.objects.get_or_create(
                tenant_id=tenant_id,
                picklist=pl,
                value=item["value"],
                defaults={
                    "label": item["label"],
                    "display_order": item["display_order"],
                },
            )
    return picklist_map


def _seed_form(apps, tenant_id, form_def, picklist_map):
    ClinicalForm = apps.get_model("clinical", "ClinicalForm")
    ClinicalFormSection = apps.get_model("clinical", "ClinicalFormSection")
    ClinicalFormField = apps.get_model("clinical", "ClinicalFormField")

    form, _ = ClinicalForm.objects.get_or_create(
        tenant_id=tenant_id,
        code=form_def["code"],
        defaults={
            "name": form_def["name"],
            "description": form_def["description"],
            "version": form_def["version"],
            "status": form_def["status"],
            "is_system": form_def["is_system"],
            "entity_type": form_def["entity_type"],
            "config": form_def["config"],
        },
    )

    for sd in form_def["sections"]:
        section, _ = ClinicalFormSection.objects.get_or_create(
            tenant_id=tenant_id,
            form=form,
            code=sd["code"],
            defaults={
                "title": sd["title"],
                "description": sd.get("description", ""),
                "display_order": sd["display_order"],
                "is_collapsed": sd["is_collapsed"],
            },
        )
        for fd in sd["fields"]:
            # Resolve picklist FK for both picklist and multiselect field types
            picklist = None
            if fd["field_type"] in ("picklist", "multiselect"):
                picklist_code = fd.get("config", {}).get("picklist_code")
                if picklist_code:
                    picklist = picklist_map.get(picklist_code)

            ClinicalFormField.objects.get_or_create(
                tenant_id=tenant_id,
                section=section,
                field_key=fd["field_key"],
                defaults={
                    "field_type": fd["field_type"],
                    "label": fd["label"],
                    "display_order": fd["display_order"],
                    "is_required": fd.get("is_required", False),
                    "is_read_only": fd.get("is_read_only", False),
                    "default_value": fd.get("default_value", None),
                    "config": fd.get("config", {}),
                    "picklist": picklist,
                },
            )


def seed_hospital_forms_forward(apps, schema_editor):
    """Seed all new hospital system forms for the system tenant."""
    # Collect existing picklists from 0002 too (yes_no, pain_scale) so multiselect
    # fields that reference them can resolve correctly.
    ClinicalPicklist = apps.get_model("clinical", "ClinicalPicklist")

    existing_picklist_map = {
        pl.code: pl
        for pl in ClinicalPicklist.objects.filter(tenant_id=_SYSTEM_TENANT)
    }

    new_picklist_map = _seed_picklists(apps, _SYSTEM_TENANT, NEW_SYSTEM_PICKLISTS)

    # Merge both maps so forms can reference any picklist
    combined_map = {**existing_picklist_map, **new_picklist_map}

    for form_def in NEW_SYSTEM_FORMS:
        _seed_form(apps, _SYSTEM_TENANT, form_def, combined_map)


def seed_hospital_forms_reverse(apps, schema_editor):
    """Remove seeded hospital forms and picklists for the system tenant."""
    ClinicalForm = apps.get_model("clinical", "ClinicalForm")
    ClinicalPicklist = apps.get_model("clinical", "ClinicalPicklist")
    ClinicalForm.objects.filter(
        tenant_id=_SYSTEM_TENANT,
        code__in=_NEW_FORM_CODES,
    ).delete()
    ClinicalPicklist.objects.filter(
        tenant_id=_SYSTEM_TENANT,
        code__in=_NEW_PICKLIST_CODES,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("clinical", "0002_seed_system_forms"),
    ]

    operations = [
        migrations.RunPython(
            seed_hospital_forms_forward,
            seed_hospital_forms_reverse,
        ),
    ]
