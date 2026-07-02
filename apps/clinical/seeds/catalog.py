"""MRD checklist lines, document templates (consents/stationery skeleton), print templates.

Document BODIES are intentionally NOT seeded here — only the registry skeleton so the
Consents & Stationery drawer lights up. Verbatim EN/MR bodies are loaded after the
live recording (Phase 4). Letterhead/logo/header come from tenant config at render time.
"""

# ---------------------------------------------------------------------------
# MRD checklist lines (HHH.pdf taxonomy). source_code points at a form/document
# code so the resolver can auto-mark Available / Missing per encounter.
# ---------------------------------------------------------------------------
MRD_LINES = [
    {"code": "IPD1", "label": "Admission registration + General consent + High risk consent", "bucket": "ipd", "source_type": "document", "source_code": "general_consent"},
    {"code": "IPD2", "label": "ICU admission consent form", "bucket": "ipd", "source_type": "document", "source_code": "icu_consent"},
    {"code": "IPD3", "label": "Initial Assessment Doctors (2 pages)", "bucket": "ipd", "source_type": "form", "source_code": "ipd_emr"},
    {"code": "IPD4", "label": "Treatment Sheet ward RMO", "bucket": "ipd", "source_type": "form", "source_code": "medication_chart"},
    {"code": "IPD5", "label": "Reassessment for Doctors", "bucket": "ipd", "source_type": "form", "source_code": "round_notes"},
    {"code": "IPD6", "label": "Initial assessment nursing", "bucket": "ipd", "source_type": "form", "source_code": "nursing_initial_assessment"},
    {"code": "IPD7", "label": "Nurses continuation sheet", "bucket": "ipd", "source_type": "form", "source_code": "nurses_continuation_sheet"},
    {"code": "IPD8", "label": "Monitoring Chart", "bucket": "ipd", "source_type": "form", "source_code": "monitoring_chart"},
    {"code": "IPD9", "label": "Intake Output Chart", "bucket": "ipd", "source_type": "form", "source_code": "monitoring_chart"},
    {"code": "IPD10", "label": "Graph of growth chart", "bucket": "ipd", "source_type": "none"},
    {"code": "SX1", "label": "Informed Consent for Surgery (2 pages)", "bucket": "sx", "source_type": "document", "source_code": "surgery_consent"},
    {"code": "SX2", "label": "Anaesthesia consent (2 pages)", "bucket": "sx", "source_type": "document", "source_code": "anaesthesia_consent"},
    {"code": "SX3", "label": "Pre-op and intra-op order of surgeon", "bucket": "sx", "source_type": "form", "source_code": "operative_notes"},
    {"code": "SX4", "label": "Post-op order + 1st post-op day", "bucket": "sx", "source_type": "form", "source_code": "first_post_op_day"},
    {"code": "SX5", "label": "Anaesthesia records (2 pages)", "bucket": "sx", "source_type": "form", "source_code": "pre_anaesthesia_assessment"},
    {"code": "SX6", "label": "Pre-op checklist + Surgical Safety checklist", "bucket": "sx", "source_type": "form", "source_code": "pre_operative_checklist"},
    {"code": "GEN1", "label": "Procedure consent", "bucket": "gen", "source_type": "document", "source_code": "procedure_consent"},
    {"code": "GEN2", "label": "BT Consent", "bucket": "gen", "source_type": "document", "source_code": "bt_consent"},
    {"code": "GEN3", "label": "DAMA Consent", "bucket": "gen", "source_type": "document", "source_code": "dama_consent"},
    {"code": "GEN4", "label": "Transfer / Referral form", "bucket": "gen", "source_type": "form", "source_code": "transfer_referral_form"},
    {"code": "GEN5", "label": "MLC Form", "bucket": "gen", "source_type": "form", "source_code": "mlc_form"},
    {"code": "GEN6", "label": "Trauma Sheet", "bucket": "gen", "source_type": "form", "source_code": "trauma_sheet"},
    {"code": "GEN7", "label": "Discharge Card", "bucket": "gen", "source_type": "form", "source_code": "discharge_card"},
    {"code": "GEN8", "label": "MRD Checklist", "bucket": "gen", "source_type": "form", "source_code": "mrd_checklist"},
    {"code": "GEN9", "label": "HRM High risk medication", "bucket": "gen", "source_type": "none"},
    {"code": "GEN10", "label": "Bill of hospital", "bucket": "gen", "source_type": "none"},
    {"code": "GEN11", "label": "Document of MJPJAY", "bucket": "gen", "source_type": "none"},
    {"code": "GEN12", "label": "Death Certificate", "bucket": "gen", "source_type": "document", "source_code": "death_certificate"},
    {"code": "MISC1", "label": "LAB reports", "bucket": "misc", "source_type": "form", "source_code": "investigation"},
    {"code": "MISC2", "label": "X-ray Report", "bucket": "misc", "source_type": "none"},
    {"code": "MISC3", "label": "USG Reports", "bucket": "misc", "source_type": "none"},
    {"code": "MISC4", "label": "Other Reports", "bucket": "misc", "source_type": "none"},
]


# ---------------------------------------------------------------------------
# Document templates — Consents (CONSENT.pdf) + Stationery (HHH.pdf) skeleton.
# bodies/HTML added later; languages en+mr.
# ---------------------------------------------------------------------------
def _consent(code, name, bucket="gen", sig=True, order=0):
    return {"code": code, "name": name, "doc_type": "consent", "bucket": bucket,
            "languages": ["en", "mr"], "requires_signature": sig,
            "applicable_entity_types": ["ipd_admission"], "display_order": order}


def _stationery(code, name, bucket="ipd", order=0):
    return {"code": code, "name": name, "doc_type": "stationery", "bucket": bucket,
            "languages": ["en", "mr"], "requires_signature": False,
            "applicable_entity_types": ["ipd_admission"], "display_order": order}


DOCUMENT_TEMPLATES = [
    # --- Consents ---
    _consent("general_consent", "General Consent for Admission + IV/IM/SC Injection", "ipd", order=1),
    _consent("high_risk_consent", "High Risk Consent", "ipd", order=2),
    _consent("icu_consent", "ICU Admission Consent", "ipd", order=3),
    _consent("surgery_consent", "Informed Consent for Surgery / Procedure", "sx", order=4),
    _consent("anaesthesia_consent", "Anaesthesia Consent (General + Regional / Sedation)", "sx", order=5),
    _consent("procedure_consent", "Procedure Consent", "gen", order=6),
    _consent("bt_consent", "Blood Transfusion (BT) Consent", "gen", order=7),
    _consent("dama_consent", "DAMA / LAMA Consent", "gen", order=8),
    _consent("hiv_consent", "Consent for HIV Antibody Testing", "gen", order=9),
    _consent("haemodialysis_consent", "Consent for Haemodialysis", "gen", order=10),
    _consent("cvc_consent", "Consent for Central Venous Catheterisation", "gen", order=11),
    _consent("thrombolysis_consent", "Consent for Thrombolysis", "gen", order=12),
    _consent("gastroscopy_consent", "Consent for Gastroscopy", "gen", order=13),
    _consent("colonoscopy_consent", "Consent for Colonoscopy", "gen", order=14),
    # --- Stationery (blank printable papers) ---
    _stationery("st_nurses_continuation", "Nurses Continuation Sheet", "ipd", order=1),
    _stationery("st_monitoring_chart", "Monitoring Chart", "ipd", order=2),
    _stationery("st_intake_output", "Intake / Output Chart", "ipd", order=3),
    _stationery("st_medication_chart", "Medication Chart", "ipd", order=4),
    _stationery("st_drug_chart", "Drug Chart", "ipd", order=5),
    _stationery("st_bt_chart", "Transfusion Monitoring Chart", "gen", order=6),
    _stationery("st_indoor_case_paper", "Indoor Case Paper", "ipd", order=7),
    _stationery("st_mrd_checklist", "MRD Checklist", "gen", order=8),
    _stationery("st_billing_chart", "Billing Chart", "gen", order=9),
    {"code": "death_certificate", "name": "Death Certificate", "doc_type": "certificate", "bucket": "gen",
     "languages": ["en", "mr"], "requires_signature": True, "applicable_entity_types": ["ipd_admission"], "display_order": 10},
]


# ---------------------------------------------------------------------------
# Print templates — generic scaffolds. target_code "*" = default fallback.
# Header/logo/address injected from tenant config; banner partial shared.
# ---------------------------------------------------------------------------
PRINT_TEMPLATES = [
    {"code": "form_letterhead_en", "target_type": "form", "target_code": "*", "layout": "letterhead", "language": "en",
     "html": "", "config": {"header_from": "tenant_config", "banner": "shared_patient_banner"}},
    {"code": "form_letterhead_mr", "target_type": "form", "target_code": "*", "layout": "letterhead", "language": "mr",
     "html": "", "config": {"header_from": "tenant_config", "banner": "shared_patient_banner"}},
    {"code": "form_blank_en", "target_type": "form", "target_code": "*", "layout": "blank", "language": "en",
     "html": "", "config": {"banner": "shared_patient_banner"}},
    {"code": "document_letterhead_en", "target_type": "document", "target_code": "*", "layout": "letterhead", "language": "en",
     "html": "", "config": {"header_from": "tenant_config"}},
    {"code": "document_letterhead_mr", "target_type": "document", "target_code": "*", "layout": "letterhead", "language": "mr",
     "html": "", "config": {"header_from": "tenant_config"}},
]
