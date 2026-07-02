"""Form groups - power the IPD Files drawer, the EMR left rail, and tab sets."""

FORM_GROUPS = [
    # ---- IPD Files & More drawer (parent + Clinical / Operative children) ----
    {
        "code": "ipd_files", "name": "IPD Files & More", "group_type": "drawer_section",
        "entity_type": "ipd_admission", "display_order": 1, "is_system": True, "items": [],
    },
    # Clinical column - EXACT order & labels from the legacy "More" popup.
    {
        "code": "ipd_files_clinical", "name": "Clinical", "group_type": "left_rail",
        "entity_type": "ipd_admission", "display_order": 1, "parent": "ipd_files", "is_system": True,
        "items": [
            {"form": "ipd_emr", "display_order": 1,
             "config": {"label": "Doctor's Initial Assessment / IPD Patient EMR"}},
            {"form": "round_notes", "display_order": 2, "config": {"label": "Round Notes"}},
            {"form": "short_round_notes", "display_order": 3, "config": {"label": "Short Round Notes"}},
            {"form": "monitoring_chart", "display_order": 4, "config": {"label": "Monitor Chart"}},
            {"form": "discharge_card", "display_order": 5, "config": {"label": "Discharge Card"}},
            {"form": "prescription", "display_order": 6, "config": {"label": "Prescription"}},
        ],
    },
    # Operative column - EXACT order & labels from the legacy "More" popup.
    {
        "code": "ipd_files_operative", "name": "Operative", "group_type": "left_rail",
        "entity_type": "ipd_admission", "display_order": 2, "parent": "ipd_files", "is_system": True,
        "items": [
            {"form": "ot_schedule", "display_order": 1, "config": {"label": "Schedule"}},
            {"form": "operative_notes", "display_order": 2, "config": {"label": "OT Notes"}},
            {"form": "incident_register", "display_order": 3, "config": {"label": "Incidence Register"}},
            {"form": "investigation", "display_order": 4, "config": {"label": "Investigation"}},
        ],
    },
    # ---- Discharge papers ----
    {
        "code": "discharge_papers", "name": "Discharge Papers", "group_type": "workflow",
        "entity_type": "ipd_admission", "display_order": 2, "is_system": True,
        "items": [
            {"form": "discharge_card", "display_order": 1},
            {"form": "mrd_checklist", "display_order": 2},
            {"form": "indoor_case_paper", "display_order": 3},
        ],
    },
    # ---- Incident management ----
    {
        "code": "incident_management", "name": "Incident Management", "group_type": "drawer_section",
        "entity_type": "ipd_admission", "display_order": 3, "is_system": True,
        "items": [
            {"form": "incident_register", "display_order": 1},
        ],
    },
    # ---- OPD clinical ----
    {
        "code": "opd_clinical", "name": "OPD Clinical", "group_type": "left_rail",
        "entity_type": "opd_visit", "display_order": 1, "is_system": True,
        "items": [
            {"form": "opd_consultation", "display_order": 1},
        ],
    },
]
