"""Seed system clinical forms and picklists for a default tenant."""

import uuid

from django.db import migrations


def _seed_picklists(apps, tenant_id, user_id, picklist_defs):
    ClinicalPicklist = apps.get_model("clinical", "ClinicalPicklist")
    ClinicalPicklistItem = apps.get_model("clinical", "ClinicalPicklistItem")
    picklist_map = {}
    for picklist_def in picklist_defs:
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
    return picklist_map


def _seed_form(apps, tenant_id, user_id, form_def, picklist_map):
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
            "created_by_user_id": user_id,
        },
    )

    for section_def in form_def["sections"]:
        section, _ = ClinicalFormSection.objects.get_or_create(
            tenant_id=tenant_id,
            form=form,
            code=section_def["code"],
            defaults={
                "title": section_def["title"],
                "description": section_def["description"],
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


def seed_system_forms_forward(apps, schema_editor):
    """Forward migration: seed system forms for the default system tenant."""
    from apps.clinical.management.commands.seed_system_forms import (
        SYSTEM_PICKLISTS,
        SYSTEM_VITALS_FORM,
    )

    # Default system tenant UUID. Use the management command to seed for real tenants.
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    user_id = None

    picklist_map = _seed_picklists(apps, tenant_id, user_id, SYSTEM_PICKLISTS)
    _seed_form(apps, tenant_id, user_id, SYSTEM_VITALS_FORM, picklist_map)


def seed_system_forms_reverse(apps, schema_editor):
    """Reverse migration: remove seeded system forms for the default tenant."""
    ClinicalForm = apps.get_model("clinical", "ClinicalForm")
    ClinicalPicklist = apps.get_model("clinical", "ClinicalPicklist")
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    ClinicalForm.objects.filter(tenant_id=tenant_id, code="system_vitals").delete()
    ClinicalPicklist.objects.filter(tenant_id=tenant_id, code__in=["yes_no", "pain_scale"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("clinical", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_system_forms_forward, seed_system_forms_reverse),
    ]
