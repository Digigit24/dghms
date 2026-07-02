"""Management command to seed system clinical forms and picklists."""

import uuid

import structlog
from django.core.management.base import BaseCommand

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# 0002 seed data — vitals form & base picklists
# Shared seed data definitions. Keep in sync with migration 0002_seed_system_forms.
SYSTEM_VITALS_FORM = {
    "code": "system_vitals",
    "name": "System Vitals",
    "description": "Default vitals form for OPD/IPD encounters.",
    "version": 1,
    "status": "published",
    "is_system": True,
    "entity_type": "generic",
    "config": {"layout": "vertical"},
    "sections": [
        {
            "code": "vital_signs",
            "title": "Vital Signs",
            "description": "Core vital measurements.",
            "display_order": 1,
            "is_collapsed": False,
            "fields": [
                {
                    "field_key": "temperature",
                    "field_type": "number",
                    "label": "Temperature (°C)",
                    "display_order": 1,
                    "is_required": False,
                    "config": {"min": 30, "max": 45, "step": 0.1},
                },
                {
                    "field_key": "pulse",
                    "field_type": "number",
                    "label": "Pulse (bpm)",
                    "display_order": 2,
                    "is_required": False,
                    "config": {"min": 30, "max": 200},
                },
                {
                    "field_key": "bp_systolic",
                    "field_type": "number",
                    "label": "BP Systolic (mmHg)",
                    "display_order": 3,
                    "is_required": False,
                    "config": {"min": 70, "max": 250},
                },
                {
                    "field_key": "bp_diastolic",
                    "field_type": "number",
                    "label": "BP Diastolic (mmHg)",
                    "display_order": 4,
                    "is_required": False,
                    "config": {"min": 40, "max": 150},
                },
                {
                    "field_key": "respiratory_rate",
                    "field_type": "number",
                    "label": "Respiratory Rate (/min)",
                    "display_order": 5,
                    "is_required": False,
                    "config": {"min": 10, "max": 60},
                },
            ],
        },
        {
            "code": "measurements",
            "title": "Measurements",
            "description": "Anthropometric measurements.",
            "display_order": 2,
            "is_collapsed": False,
            "fields": [
                {
                    "field_key": "weight",
                    "field_type": "number",
                    "label": "Weight (kg)",
                    "display_order": 1,
                    "is_required": False,
                    "config": {"min": 0.5, "max": 300, "step": 0.1},
                },
                {
                    "field_key": "height",
                    "field_type": "number",
                    "label": "Height (cm)",
                    "display_order": 2,
                    "is_required": False,
                    "config": {"min": 30, "max": 250},
                },
                {
                    "field_key": "bmi",
                    "field_type": "calculated",
                    "label": "BMI",
                    "display_order": 3,
                    "is_required": False,
                    "is_read_only": True,
                    "config": {"formula": "weight / ((height/100) ** 2)"},
                },
                {
                    "field_key": "pain_scale",
                    "field_type": "picklist",
                    "label": "Pain Scale",
                    "display_order": 4,
                    "is_required": False,
                    "config": {"picklist_code": "pain_scale"},
                },
            ],
        },
    ],
}

SYSTEM_PICKLISTS = [
    {
        "code": "yes_no",
        "name": "Yes / No",
        "description": "Binary yes/no choice.",
        "is_system": True,
        "items": [
            {"label": "Yes", "value": "yes", "display_order": 1},
            {"label": "No", "value": "no", "display_order": 2},
        ],
    },
    {
        "code": "pain_scale",
        "name": "Pain Scale (0-10)",
        "description": "Numeric pain scale from 0 to 10.",
        "is_system": True,
        "items": [
            {"label": "0 - No pain", "value": "0", "display_order": 1},
            {"label": "1", "value": "1", "display_order": 2},
            {"label": "2", "value": "2", "display_order": 3},
            {"label": "3", "value": "3", "display_order": 4},
            {"label": "4", "value": "4", "display_order": 5},
            {"label": "5", "value": "5", "display_order": 6},
            {"label": "6", "value": "6", "display_order": 7},
            {"label": "7", "value": "7", "display_order": 8},
            {"label": "8", "value": "8", "display_order": 9},
            {"label": "9", "value": "9", "display_order": 10},
            {"label": "10 - Worst pain", "value": "10", "display_order": 11},
        ],
    },
]


# ---------------------------------------------------------------------------
# 0003 seed data — hospital system forms
# Keep in sync with migration 0003_seed_hospital_system_forms.
# ---------------------------------------------------------------------------
HOSPITAL_SYSTEM_PICKLISTS = [
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
        ],
    },
    {
        "code": "investigations",
        "name": "Investigations",
        "description": "Common laboratory investigations. Tenants can add more items.",
        "is_system": True,
        "items": [
            {"label": "Dengue NS1 / IgM IgG", "value": "dengue", "display_order": 1},
            {"label": "Malaria Antigen / Smear", "value": "malaria", "display_order": 2},
            {"label": "COVID-19 RTPCR", "value": "covid_rtpcr", "display_order": 3},
            {"label": "Prothrombin Time (PT / INR)", "value": "pt_inr", "display_order": 4},
            {"label": "Coagulation Profile (APTT)", "value": "aptt", "display_order": 5},
            {"label": "Serum Uric Acid", "value": "uric_acid", "display_order": 6},
            {"label": "Serum Calcium", "value": "calcium", "display_order": 7},
            {"label": "Vitamin D3", "value": "vit_d3", "display_order": 8},
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


class Command(BaseCommand):
    help = "Seed system clinical forms and picklists for a tenant."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=str, required=True, help="UUID of the tenant.")
        parser.add_argument("--user-id", type=str, default=None, help="UUID of the acting user.")

    def handle(self, *args, **options):
        from apps.clinical.models import (
            ClinicalForm,
            ClinicalFormField,
            ClinicalFormSection,
            ClinicalPicklist,
            ClinicalPicklistItem,
            FormSectionPlacement,
        )

        tenant_id = uuid.UUID(options["tenant_id"])
        user_id = uuid.UUID(options["user_id"]) if options.get("user_id") else None

        picklist_map = {}
        for pl_def in SYSTEM_PICKLISTS:
            pl, _ = ClinicalPicklist.objects.get_or_create(
                tenant_id=tenant_id,
                code=pl_def["code"],
                defaults={
                    "name": pl_def["name"],
                    "description": pl_def.get("description", ""),
                    "is_system": pl_def.get("is_system", True),
                    "created_by_user_id": user_id,
                },
            )
            picklist_map[pl_def["code"]] = pl
            for item_def in pl_def.get("items", []):
                ClinicalPicklistItem.objects.get_or_create(
                    tenant_id=tenant_id,
                    picklist=pl,
                    value=item_def["value"],
                    defaults={
                        "label": item_def["label"],
                        "display_order": item_def.get("display_order", 0),
                        "created_by_user_id": user_id,
                    },
                )

        form_def = SYSTEM_VITALS_FORM
        form, _ = ClinicalForm.objects.get_or_create(
            tenant_id=tenant_id,
            code=form_def["code"],
            defaults={
                "name": form_def["name"],
                "description": form_def.get("description", ""),
                "version": form_def.get("version", 1),
                "status": form_def.get("status", "published"),
                "is_system": form_def.get("is_system", True),
                "entity_type": form_def.get("entity_type", "generic"),
                "config": form_def.get("config", {}),
                "created_by_user_id": user_id,
            },
        )
        for section_def in form_def.get("sections", []):
            section_code = f"{form_def['code']}_{section_def['code']}"[:64]
            section, _ = ClinicalFormSection.objects.get_or_create(
                tenant_id=tenant_id,
                code=section_code,
                defaults={
                    "title": section_def["title"],
                    "description": section_def.get("description", ""),
                    "is_system": form_def.get("is_system", True),
                    "config": section_def.get("config", {}),
                    "created_by_user_id": user_id,
                },
            )
            FormSectionPlacement.objects.get_or_create(
                tenant_id=tenant_id,
                form=form,
                section=section,
                instance_key="",
                defaults={
                    "display_order": section_def.get("display_order", 0),
                    "is_collapsed": section_def.get("is_collapsed", False),
                    "created_by_user_id": user_id,
                },
            )
            for field_def in section_def.get("fields", []):
                picklist = picklist_map.get(field_def.get("config", {}).get("picklist_code"))
                ClinicalFormField.objects.get_or_create(
                    tenant_id=tenant_id,
                    section=section,
                    field_key=field_def["field_key"],
                    defaults={
                        "field_type": field_def["field_type"],
                        "label": field_def["label"],
                        "display_order": field_def.get("display_order", 0),
                        "is_required": field_def.get("is_required", False),
                        "is_read_only": field_def.get("is_read_only", False),
                        "config": field_def.get("config", {}),
                        "picklist": picklist,
                        "created_by_user_id": user_id,
                    },
                )

        self.stdout.write(self.style.SUCCESS("System forms seeded successfully."))

# Form definitions are large; load them directly from the migration file to avoid
# duplication. The filename starts with a digit so we use spec_from_file_location.
def _load_hospital_forms():
    import importlib.util
    import os
    migration_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "migrations",
                     "0003_seed_hospital_system_forms.py")
    )
    spec = importlib.util.spec_from_file_location("_migration_0003", migration_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "NEW_SYSTEM_FORMS", [])


HOSPITAL_SYSTEM_FORMS = _load_hospital_forms()


def seed_hospital_system_forms(tenant_id, user_id=None):
    """Idempotently seed hospital system forms (added in migration 0003) for a tenant.

    Data is defined as module-level constants above (HOSPITAL_SYSTEM_PICKLISTS /
    HOSPITAL_SYSTEM_FORMS) so both this function and the migration share the same
    definitions without circular imports.
    """
    from apps.clinical.models import (
        ClinicalForm,
        ClinicalFormField,
        ClinicalFormSection,
        ClinicalPicklist,
        ClinicalPicklistItem,
        FormSectionPlacement,
    )

    if isinstance(tenant_id, str):
        tenant_id = uuid.UUID(tenant_id)
    if user_id is not None and isinstance(user_id, str):
        user_id = uuid.UUID(user_id)

    # Merge existing picklists (yes_no, pain_scale) + new ones
    existing_map = {pl.code: pl for pl in ClinicalPicklist.objects.filter(tenant_id=tenant_id)}
    new_picklist_map = {}
    for pd in HOSPITAL_SYSTEM_PICKLISTS:
        pl, _ = ClinicalPicklist.objects.get_or_create(
            tenant_id=tenant_id,
            code=pd["code"],
            defaults={
                "name": pd["name"],
                "description": pd["description"],
                "is_system": pd["is_system"],
                "created_by_user_id": user_id,
            },
        )
        new_picklist_map[pd["code"]] = pl
        for item in pd["items"]:
            ClinicalPicklistItem.objects.get_or_create(
                tenant_id=tenant_id,
                picklist=pl,
                value=item["value"],
                defaults={
                    "label": item["label"],
                    "display_order": item["display_order"],
                    "created_by_user_id": user_id,
                },
            )
        logger.info("system_picklist_seeded", tenant_id=str(tenant_id), picklist_code=pd["code"])

    combined_map = {**existing_map, **new_picklist_map}

    for form_def in HOSPITAL_SYSTEM_FORMS:
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
                "created_by_user_id": user_id,
            },
        )
        for sd in form_def["sections"]:
            section_code = f"{form_def['code']}_{sd['code']}"[:64]
            section, _ = ClinicalFormSection.objects.get_or_create(
                tenant_id=tenant_id,
                code=section_code,
                defaults={
                    "title": sd["title"],
                    "description": sd.get("description", ""),
                    "is_system": form_def.get("is_system", True),
                    "created_by_user_id": user_id,
                },
            )
            FormSectionPlacement.objects.get_or_create(
                tenant_id=tenant_id,
                form=form,
                section=section,
                instance_key="",
                defaults={
                    "display_order": sd["display_order"],
                    "is_collapsed": sd["is_collapsed"],
                    "created_by_user_id": user_id,
                },
            )
            for fd in sd["fields"]:
                picklist = None
                if fd["field_type"] in ("picklist", "multiselect"):
                    picklist = combined_map.get(fd.get("config", {}).get("picklist_code"))
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
                        "created_by_user_id": user_id,
                    },
                )
        logger.info("system_form_seeded", tenant_id=str(tenant_id), form_code=form_def["code"])


def seed_system_forms(tenant_id, user_id=None):
    """Idempotently seed system forms and picklists for a tenant.

    Args:
        tenant_id: UUID (string or UUID) of the tenant.
        user_id: Optional UUID of the creating user.
    """
    from apps.clinical.models import (
        ClinicalForm,
        ClinicalFormField,
        ClinicalFormSection,
        ClinicalPicklist,
        ClinicalPicklistItem,
        FormSectionPlacement,
    )

    if isinstance(tenant_id, str):
        tenant_id = uuid.UUID(tenant_id)
    if user_id is not None and isinstance(user_id, str):
        user_id = uuid.UUID(user_id)

    picklist_map = {}
    for picklist_def in SYSTEM_PICKLISTS:
        picklist, _ = ClinicalPicklist.objects.get_or_create(
            tenant_id=tenant_id,
            code=picklist_def["code"],
            defaults={
                "name": picklist_def["name"],
                "description": picklist_def["description"],
                "is_system": picklist_def["is_system"],
                "created_by_user_id": user_id,
            },
        )
        picklist_map[picklist_def["code"]] = picklist
        for item_def in picklist_def["items"]:
            ClinicalPicklistItem.objects.get_or_create(
                tenant_id=tenant_id,
                picklist=picklist,
                value=item_def["value"],
                defaults={
                    "label": item_def["label"],
                    "display_order": item_def["display_order"],
                    "created_by_user_id": user_id,
                },
            )
        logger.info(
            "system_picklist_seeded",
            tenant_id=str(tenant_id),
            picklist_code=picklist_def["code"],
        )

    form_def = SYSTEM_VITALS_FORM
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
            "created_by_user_id": user_id,
        },
    )

    for section_def in form_def["sections"]:
        section_code = f"{form_def['code']}_{section_def['code']}"[:64]
        section, _ = ClinicalFormSection.objects.get_or_create(
            tenant_id=tenant_id,
            code=section_code,
            defaults={
                "title": section_def["title"],
                "description": section_def["description"],
                "is_system": form_def.get("is_system", True),
                "created_by_user_id": user_id,
            },
        )
        FormSectionPlacement.objects.get_or_create(
            tenant_id=tenant_id,
            form=form,
            section=section,
            instance_key="",
            defaults={
                "display_order": section_def["display_order"],
                "is_collapsed": section_def["is_collapsed"],
                "created_by_user_id": user_id,
            },
        )
        for field_def in section_def["fields"]:
            picklist = None
            if field_def["field_type"] == "picklist":
                picklist_code = field_def.get("config", {}).get("picklist_code")
                picklist = picklist_map.get(picklist_code)
            ClinicalFormField.objects.get_or_create(
                tenant_id=tenant_id,
                section=section,
                field_key=field_def["field_key"],
                defaults={
                    "field_type": field_def["field_type"],
                    "label": field_def["label"],
                    "display_order": field_def["display_order"],
                    "is_required": field_def.get("is_required", False),
                    "is_read_only": field_def.get("is_read_only", False),
                    "config": field_def.get("config", {}),
                    "picklist": picklist,
                    "created_by_user_id": user_id,
                },
            )

    logger.info(
        "system_form_seeded",
        tenant_id=str(tenant_id),
        form_code=form_def["code"],
    )
    return form


class Command(BaseCommand):
    help = "Seed system clinical forms and picklists for a tenant (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            type=str,
            required=True,
            help="UUID of the tenant to seed system data for.",
        )
        parser.add_argument(
            "--user-id",
            type=str,
            default=None,
            help="Optional UUID of the creating user.",
        )

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]
        user_id = options.get("user_id")
        seed_system_forms(tenant_id, user_id)
        seed_hospital_system_forms(tenant_id, user_id)
        self.stdout.write(
            self.style.SUCCESS(
                f"✓ System clinical forms seeded for tenant {tenant_id}."
            )
        )
