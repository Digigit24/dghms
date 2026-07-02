"""Seed the full clinical engine foundation for a tenant.

Idempotent, tenant-scoped seeding of:
  picklists (+items, incl. label_mr) → picklist groups (+memberships)
  → shared sections → forms (+section placements, incl. shared-section reuse)
  → form groups (+items) → MRD checklist lines
  → document templates → print templates.

Usage:
  python manage.py seed_clinical_foundation --tenant-id <uuid> [--user-id <uuid>] [--wipe]

``--wipe`` deletes is_system clinical rows for the tenant first, then reseeds.
All data lives in apps/clinical/seeds/ so it can be edited without touching this loader.
"""

import uuid

import structlog
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.clinical.seeds import (
    DOCUMENT_TEMPLATES,
    FORM_GROUPS,
    FORMS,
    MRD_LINES,
    PICKLIST_GROUPS,
    PICKLISTS,
    PRINT_TEMPLATES,
    SHARED_SECTIONS,
)

logger = structlog.get_logger(__name__)


class Command(BaseCommand):
    help = "Seed system clinical forms, picklists, groups, documents (idempotent, per tenant)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=str, required=True, help="UUID of the tenant.")
        parser.add_argument("--user-id", type=str, default=None, help="Optional acting user UUID.")
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="Delete is_system clinical rows for the tenant before reseeding.",
        )

    def handle(self, *args, **options):
        try:
            tenant_id = uuid.UUID(str(options["tenant_id"]))
        except (ValueError, TypeError):
            raise CommandError("--tenant-id must be a valid UUID.")
        user_id = uuid.UUID(str(options["user_id"])) if options.get("user_id") else None

        with transaction.atomic():
            if options.get("wipe"):
                self._wipe(tenant_id)
            picklist_map = self._seed_picklists(tenant_id, user_id)
            self._seed_picklist_groups(tenant_id, user_id, picklist_map)
            section_map = self._seed_shared_sections(tenant_id, user_id, picklist_map)
            form_map = self._seed_forms(tenant_id, user_id, picklist_map, section_map)
            self._seed_form_groups(tenant_id, user_id, form_map)
            self._seed_mrd_lines(tenant_id, user_id)
            self._seed_documents(tenant_id, user_id)
            self._seed_print_templates(tenant_id, user_id)

        self.stdout.write(self.style.SUCCESS(f"✓ Clinical foundation seeded for tenant {tenant_id}."))

    # ------------------------------------------------------------------ wipe
    def _wipe(self, tenant_id):
        from apps.clinical.models import (
            ClinicalDocumentTemplate,
            ClinicalForm,
            ClinicalFormGroup,
            ClinicalFormSection,
            ClinicalPicklist,
            ClinicalPicklistGroup,
            ClinicalPrintTemplate,
            MrdChecklistLine,
        )

        # Records reference forms with PROTECT; only wipe structural/system rows.
        ClinicalFormGroup.objects.filter(tenant_id=tenant_id, is_system=True).delete()
        ClinicalForm.objects.filter(tenant_id=tenant_id, is_system=True).delete()  # cascades placements
        ClinicalFormSection.objects.filter(tenant_id=tenant_id, is_system=True).delete()
        ClinicalPicklistGroup.objects.filter(tenant_id=tenant_id, is_system=True).delete()
        ClinicalPicklist.objects.filter(tenant_id=tenant_id, is_system=True).delete()
        MrdChecklistLine.objects.filter(tenant_id=tenant_id, is_system=True).delete()
        ClinicalDocumentTemplate.objects.filter(tenant_id=tenant_id, is_system=True).delete()
        ClinicalPrintTemplate.objects.filter(tenant_id=tenant_id).delete()
        self.stdout.write(self.style.WARNING("Wiped existing is_system clinical rows for tenant."))

    # -------------------------------------------------------------- picklists
    def _seed_picklists(self, tenant_id, user_id):
        from apps.clinical.models import ClinicalPicklist, ClinicalPicklistItem

        picklist_map = {}
        for pl in PICKLISTS:
            obj, _ = ClinicalPicklist.objects.get_or_create(
                tenant_id=tenant_id,
                code=pl["code"],
                defaults={
                    "name": pl["name"],
                    "description": pl.get("description", ""),
                    "is_system": pl.get("is_system", True),
                    "created_by_user_id": user_id,
                },
            )
            picklist_map[pl["code"]] = obj
            for order, item in enumerate(pl.get("items", []), start=1):
                ClinicalPicklistItem.objects.get_or_create(
                    tenant_id=tenant_id,
                    picklist=obj,
                    value=item["value"],
                    defaults={
                        "label": item["label"],
                        "label_mr": item.get("label_mr", ""),
                        "label_hi": item.get("label_hi", ""),
                        "display_order": item.get("display_order", order),
                        "created_by_user_id": user_id,
                    },
                )
        logger.info("picklists_seeded", tenant_id=str(tenant_id), count=len(picklist_map))
        return picklist_map

    def _seed_picklist_groups(self, tenant_id, user_id, picklist_map):
        from apps.clinical.models import ClinicalPicklistGroup, ClinicalPicklistGroupMembership

        for grp in PICKLIST_GROUPS:
            obj, _ = ClinicalPicklistGroup.objects.get_or_create(
                tenant_id=tenant_id,
                code=grp["code"],
                defaults={
                    "name": grp["name"],
                    "description": grp.get("description", ""),
                    "is_system": grp.get("is_system", True),
                    "created_by_user_id": user_id,
                },
            )
            for order, pl_code in enumerate(grp.get("picklists", []), start=1):
                pl = picklist_map.get(pl_code)
                if not pl:
                    continue
                ClinicalPicklistGroupMembership.objects.get_or_create(
                    tenant_id=tenant_id,
                    group=obj,
                    picklist=pl,
                    defaults={"display_order": order, "created_by_user_id": user_id},
                )

    # --------------------------------------------------------- shared sections
    def _seed_shared_sections(self, tenant_id, user_id, picklist_map):
        """Seed reusable sections by their literal code (no form prefix)."""
        section_map = {}
        for sec in SHARED_SECTIONS:
            section = self._upsert_section(
                tenant_id, user_id, picklist_map, code=sec["code"], section_def=sec
            )
            section_map[sec["code"]] = section
        logger.info("shared_sections_seeded", tenant_id=str(tenant_id), count=len(section_map))
        return section_map

    def _upsert_section(self, tenant_id, user_id, picklist_map, code, section_def):
        from apps.clinical.models import ClinicalFormField, ClinicalFormSection

        section, _ = ClinicalFormSection.objects.get_or_create(
            tenant_id=tenant_id,
            code=code[:64],
            defaults={
                "title": section_def["title"],
                "description": section_def.get("description", ""),
                "is_system": section_def.get("is_system", True),
                "config": section_def.get("config", {}),
                "created_by_user_id": user_id,
            },
        )
        for order, fd in enumerate(section_def.get("fields", []), start=1):
            picklist = None
            cfg = fd.get("config", {})
            if fd["field_type"] in ("picklist", "multiselect") or cfg.get("picklist_code"):
                picklist = picklist_map.get(cfg.get("picklist_code"))
            ClinicalFormField.objects.get_or_create(
                tenant_id=tenant_id,
                section=section,
                field_key=fd["field_key"],
                defaults={
                    "field_type": fd["field_type"],
                    "label": fd["label"],
                    "label_mr": fd.get("label_mr", ""),
                    "help_text": fd.get("help_text", ""),
                    "display_order": fd.get("display_order", order),
                    "is_required": fd.get("is_required", False),
                    "is_read_only": fd.get("is_read_only", False),
                    "default_value": fd.get("default_value", None),
                    "config": cfg,
                    "picklist": picklist,
                    "created_by_user_id": user_id,
                },
            )
        return section

    # ------------------------------------------------------------------ forms
    def _seed_forms(self, tenant_id, user_id, picklist_map, section_map):
        from apps.clinical.models import ClinicalForm, FormSectionPlacement

        form_map = {}
        for form_def in FORMS:
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
            form_map[form_def["code"]] = form

            for order, sec in enumerate(form_def.get("sections", []), start=1):
                if "ref" in sec:
                    # Placement of a shared section defined in SHARED_SECTIONS.
                    section = section_map.get(sec["ref"])
                    if section is None:
                        raise CommandError(
                            f"Form '{form_def['code']}' references unknown shared section '{sec['ref']}'."
                        )
                else:
                    is_shared = sec.get("shared", False)
                    code = sec["code"] if is_shared else f"{form_def['code']}_{sec['code']}"
                    section = self._upsert_section(
                        tenant_id, user_id, picklist_map, code=code, section_def=sec
                    )
                    if is_shared:
                        section_map[sec["code"]] = section

                FormSectionPlacement.objects.get_or_create(
                    tenant_id=tenant_id,
                    form=form,
                    section=section,
                    instance_key=sec.get("instance_key", ""),
                    defaults={
                        "display_order": sec.get("display_order", order),
                        "is_collapsed": sec.get("is_collapsed", False),
                        "title_override": sec.get("title_override", ""),
                        "visibility_rule": sec.get("visibility_rule", {}),
                        "config": sec.get("placement_config", {}),
                        "created_by_user_id": user_id,
                    },
                )
            logger.info("form_seeded", tenant_id=str(tenant_id), form_code=form_def["code"])
        return form_map

    def _seed_form_groups(self, tenant_id, user_id, form_map):
        from apps.clinical.models import ClinicalFormGroup, ClinicalFormGroupItem

        # First pass: create groups (parent resolved in second pass).
        group_map = {}
        for grp in FORM_GROUPS:
            obj, _ = ClinicalFormGroup.objects.get_or_create(
                tenant_id=tenant_id,
                code=grp["code"],
                defaults={
                    "name": grp["name"],
                    "group_type": grp.get("group_type", "drawer_section"),
                    "entity_type": grp.get("entity_type", "generic"),
                    "display_order": grp.get("display_order", 0),
                    "is_system": grp.get("is_system", True),
                    "config": grp.get("config", {}),
                    "created_by_user_id": user_id,
                },
            )
            group_map[grp["code"]] = obj
        # Second pass: parents + items.
        for grp in FORM_GROUPS:
            obj = group_map[grp["code"]]
            parent_code = grp.get("parent")
            if parent_code and obj.parent_id is None:
                obj.parent = group_map.get(parent_code)
                obj.save(update_fields=["parent"])
            for order, item in enumerate(grp.get("items", []), start=1):
                form = form_map.get(item["form"] if isinstance(item, dict) else item)
                if not form:
                    continue
                ClinicalFormGroupItem.objects.get_or_create(
                    tenant_id=tenant_id,
                    group=obj,
                    form=form,
                    defaults={
                        "display_order": item.get("display_order", order) if isinstance(item, dict) else order,
                        "badge_when_filled": item.get("badge_when_filled", True) if isinstance(item, dict) else True,
                        "config": item.get("config", {}) if isinstance(item, dict) else {},
                        "created_by_user_id": user_id,
                    },
                )

    def _seed_mrd_lines(self, tenant_id, user_id):
        from apps.clinical.models import MrdChecklistLine

        for order, line in enumerate(MRD_LINES, start=1):
            MrdChecklistLine.objects.get_or_create(
                tenant_id=tenant_id,
                code=line["code"],
                defaults={
                    "label": line["label"],
                    "bucket": line.get("bucket", "gen"),
                    "source_type": line.get("source_type", "none"),
                    "source_code": line.get("source_code", ""),
                    "applicable_entity_types": line.get("applicable_entity_types", ["ipd_admission"]),
                    "display_order": line.get("display_order", order),
                    "is_system": True,
                    "created_by_user_id": user_id,
                },
            )

    def _seed_documents(self, tenant_id, user_id):
        from apps.clinical.models import ClinicalDocumentTemplate

        for order, doc in enumerate(DOCUMENT_TEMPLATES, start=1):
            ClinicalDocumentTemplate.objects.get_or_create(
                tenant_id=tenant_id,
                code=doc["code"],
                defaults={
                    "name": doc["name"],
                    "doc_type": doc["doc_type"],
                    "bucket": doc.get("bucket", "none"),
                    "languages": doc.get("languages", ["en", "mr"]),
                    "requires_signature": doc.get("requires_signature", False),
                    "applicable_entity_types": doc.get("applicable_entity_types", ["ipd_admission"]),
                    "display_order": doc.get("display_order", order),
                    "is_system": True,
                    "config": doc.get("config", {}),
                    "body_ref": doc.get("body_ref", {}),
                    "created_by_user_id": user_id,
                },
            )

    def _seed_print_templates(self, tenant_id, user_id):
        from apps.clinical.models import ClinicalPrintTemplate

        for tpl in PRINT_TEMPLATES:
            ClinicalPrintTemplate.objects.get_or_create(
                tenant_id=tenant_id,
                code=tpl["code"],
                defaults={
                    "target_type": tpl["target_type"],
                    "target_code": tpl.get("target_code", ""),
                    "layout": tpl.get("layout", "letterhead"),
                    "language": tpl.get("language", "en"),
                    "html": tpl.get("html", ""),
                    "config": tpl.get("config", {}),
                    "created_by_user_id": user_id,
                },
            )
