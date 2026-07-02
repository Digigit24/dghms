"""Reusable (shared) section definitions.

These are seeded once with their literal code (no form-code prefix) and placed
into multiple forms via FormSectionPlacement — proving section reuse. Forms
reference them with ``{"ref": "<code>", "display_order": N}``.
"""

SHARED_SECTIONS = [
    {
        # Patient banner: read-only header reused by every IPD/OPD paper
        # (UHID / DOA / IPD ID / Name / Consulting Doctor). Values come from the
        # encounter at render time (config.source), not user input.
        "code": "shared_patient_banner",
        "title": "Patient",
        "description": "Standard patient header shown on every clinical paper.",
        "is_system": True,
        "config": {"render": "banner"},
        "fields": [
            {"field_key": "uhid", "field_type": "text", "label": "UHID",
             "is_read_only": True, "config": {"source": "encounter.uhid", "span": "third"}},
            {"field_key": "ipd_no", "field_type": "text", "label": "IPD No.",
             "is_read_only": True, "config": {"source": "encounter.ipd_no", "span": "third"}},
            {"field_key": "patient_name", "field_type": "text", "label": "Patient Name",
             "is_read_only": True, "config": {"source": "encounter.patient_name", "span": "third"}},
            {"field_key": "age_gender", "field_type": "text", "label": "Age / Gender",
             "is_read_only": True, "config": {"source": "encounter.age_gender", "span": "third"}},
            {"field_key": "doa", "field_type": "text", "label": "DOA",
             "is_read_only": True, "config": {"source": "encounter.doa", "span": "third"}},
            {"field_key": "consulting_doctor", "field_type": "text", "label": "Consulting Doctor",
             "is_read_only": True, "config": {"source": "encounter.consulting_doctor", "span": "third"}},
        ],
    },
    {
        # Core vitals reused by assessment, round notes, OPD, etc.
        "code": "shared_vitals",
        "title": "Vital Signs",
        "description": "Core vital measurements.",
        "is_system": True,
        "fields": [
            {"field_key": "temperature", "field_type": "number", "label": "Temperature (°F)",
             "config": {"min": 90, "max": 110, "step": 0.1, "span": "third"}},
            {"field_key": "pulse", "field_type": "number", "label": "Pulse (/min)",
             "config": {"min": 30, "max": 220, "span": "third"}},
            {"field_key": "resp_rate", "field_type": "number", "label": "Respiratory Rate (/min)",
             "config": {"min": 8, "max": 60, "span": "third"}},
            {"field_key": "bp_systolic", "field_type": "number", "label": "BP Systolic (mmHg)",
             "config": {"min": 60, "max": 260, "span": "third"}},
            {"field_key": "bp_diastolic", "field_type": "number", "label": "BP Diastolic (mmHg)",
             "config": {"min": 30, "max": 160, "span": "third"}},
            {"field_key": "spo2", "field_type": "number", "label": "SPO2 (%)",
             "config": {"min": 50, "max": 100, "span": "third"}},
            {"field_key": "weight", "field_type": "number", "label": "Weight (kg)",
             "config": {"min": 0.5, "max": 300, "step": 0.1, "span": "third"}},
            {"field_key": "height", "field_type": "number", "label": "Height (cm)",
             "config": {"min": 30, "max": 250, "span": "third"}},
            {"field_key": "bmi", "field_type": "calculated", "label": "BMI", "is_read_only": True,
             "config": {"formula": "weight / ((height/100) ** 2)", "span": "third"}},
        ],
    },
]
