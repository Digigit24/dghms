"""OpenAI integration for the clinical form AI wizard.

This module builds a strict system prompt + JSON schema so the model returns a
Celiyo-compatible **form draft**. Drafts are validated and applied by
``ai_views._apply_form_draft`` into real ``ClinicalForm`` /
``ClinicalFormSection`` (reusable) / ``FormSectionPlacement`` /
``ClinicalFormField`` / ``ClinicalPicklist`` / ``ClinicalPicklistItem`` records.

The AI can:
  * create a new form (with sections, fields, picklists, tabs),
  * create picklists only,
  * additively update an existing form (add sections, add fields, add tabs).

Everything the AI produces lands in ``staging`` status and must be reviewed and
published by a human — the AI never publishes.

The generator also accepts an optional image (photo/scan of a paper form) and
transcribes it into the same schema (vision).
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog
from django.conf import settings
from openai import OpenAI

from .models import ClinicalForm, ClinicalFormField

logger = structlog.get_logger(__name__)

# All field types supported by the clinical engine (kept in sync with the model).
FIELD_TYPES = [choice[0] for choice in ClinicalFormField.FieldType.choices]

# Operations the AI can request.
OPERATIONS = ["create_form", "update_form", "create_picklists"]


# ---------------------------------------------------------------------------
# JSON schema (advisory — passed to the model alongside the system prompt).
# ---------------------------------------------------------------------------

FORM_DRAFT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["operation"],
    "properties": {
        "operation": {
            "type": "string",
            "enum": OPERATIONS,
            "description": (
                "What to do: 'create_form' (new form), 'update_form' (additively "
                "extend an existing form referenced by target_form_code), or "
                "'create_picklists' (only add reusable option lists)."
            ),
        },
        "target_form_code": {
            "type": "string",
            "maxLength": 64,
            "description": "REQUIRED for update_form. The code of the existing form to extend.",
        },
        "code": {
            "type": "string",
            "maxLength": 64,
            "description": "Stable snake_case identifier for the form (create_form). e.g. 'diabetes_opd_followup'.",
        },
        "name": {"type": "string", "maxLength": 200, "description": "Human-readable form name."},
        "description": {"type": "string", "description": "Short purpose/context of the form."},
        "entity_type": {
            "type": "string",
            "enum": [c[0] for c in ClinicalForm.EntityType.choices],
            "description": "Encounter scope: opd_visit, ipd_admission, or generic.",
        },
        "config": {
            "type": "object",
            "additionalProperties": True,
            "description": (
                "Form-level display config. Common keys: 'icon' (lucide icon name), "
                "'color' (theme color), 'repeatable' (bool — many records per encounter, e.g. "
                "round notes), 'custom_component' (string — only for special built-in renderers)."
            ),
        },
        "tabs": {
            "type": "array",
            "description": (
                "Optional tab bar. Each section is assigned to a tab via section.tab. "
                "type 'form' = renders that tab's sections; type 'component' = a built-in panel."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "label"],
                "properties": {
                    "key": {"type": "string", "maxLength": 40, "description": "snake_case tab key."},
                    "label": {"type": "string", "maxLength": 60},
                    "type": {"type": "string", "enum": ["form", "component"], "description": "Default 'form'."},
                    "component": {"type": "string", "description": "Registry key when type='component'."},
                    "order": {"type": "integer", "minimum": 0},
                },
            },
        },
        "sections": {
            "type": "array",
            "description": "Sections to create/attach. Omit for create_picklists.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code", "title", "fields"],
                "properties": {
                    "code": {"type": "string", "maxLength": 64, "description": "snake_case, unique within the form."},
                    "title": {"type": "string", "maxLength": 200},
                    "description": {"type": "string"},
                    "display_order": {"type": "integer", "minimum": 0},
                    "is_collapsed": {"type": "boolean"},
                    "tab": {"type": "string", "description": "Tab key this section belongs to (if the form has tabs)."},
                    "config": {
                        "type": "object",
                        "additionalProperties": True,
                        "description": "Section config. Keys: 'span' (full|half|third), 'render' ('banner' for read-only header).",
                    },
                    "fields": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["field_key", "field_type", "label"],
                            "properties": {
                                "field_key": {"type": "string", "maxLength": 64, "description": "snake_case, unique within the form."},
                                "field_type": {"type": "string", "enum": FIELD_TYPES},
                                "label": {"type": "string", "maxLength": 255},
                                "label_mr": {"type": "string", "maxLength": 255, "description": "Optional Marathi label."},
                                "help_text": {"type": "string", "maxLength": 500},
                                "display_order": {"type": "integer", "minimum": 0},
                                "is_required": {"type": "boolean"},
                                "is_read_only": {"type": "boolean"},
                                "default_value": {"type": ["string", "number", "boolean", "array", "object", "null"]},
                                "picklist_code": {
                                    "type": "string",
                                    "maxLength": 64,
                                    "description": "For picklist/multiselect: references a picklist by code (defined in 'picklists' or already existing).",
                                },
                                "config": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "description": "Field config — see the config vocabulary in the system prompt.",
                                },
                            },
                        },
                    },
                },
            },
        },
        "picklists": {
            "type": "array",
            "description": "Reusable option lists referenced by picklist_code.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code", "name", "items"],
                "properties": {
                    "code": {"type": "string", "maxLength": 64},
                    "name": {"type": "string", "maxLength": 200},
                    "description": {"type": "string"},
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["label", "value"],
                            "properties": {
                                "label": {"type": "string", "maxLength": 255},
                                "value": {"type": "string", "maxLength": 255},
                                "label_mr": {"type": "string", "maxLength": 255},
                                "display_order": {"type": "integer", "minimum": 0},
                            },
                        },
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    """You are the clinical form designer for Celiyo HMS, a multi-tenant hospital \
management system used by doctors and nurses in OPD and IPD.

Your job: turn a natural-language request (and, when provided, a photo/scan of a \
paper form) into ONE valid JSON object that matches the schema at the end. Return \
ONLY the JSON object — no markdown, no commentary.

## What you can produce (top-level "operation")
- "create_form": a brand-new form with sections, fields, picklists, and optional tabs.
- "update_form": ADDITIVELY extend an existing form named by "target_form_code" — \
add new sections, add new fields to existing sections (match by section "code"), \
add picklists, add tabs. NEVER rename or delete existing sections/fields; only add. \
If the user asks to remove or rename things, add what is safe and note nothing else.
- "create_picklists": only produce the top-level "picklists" array (no sections).

Everything you output is saved in STAGING and reviewed by a human before it goes \
live. You never publish. Prefer completeness and clinical correctness.

## Field types (use the most specific one)
- text: short single-line text.
- textarea: multi-line notes. Add config {"select_from_list": true} + "picklist_code" \
  to offer reusable phrase snippets that the user can insert (type-ahead), while still \
  allowing free text.
- rich_text: long formatted narrative.
- number: numeric. Add config {"min", "max", "step"} for vitals (e.g. temperature \
  {"min":30,"max":45,"step":0.1}).
- boolean: a single checkbox.
- yes_no: Yes / No / NA selector. Add config {"with_remarks": true} to include a remarks box.
- date / time / datetime: calendar/clock inputs. Add config {"default_now": true} to \
  auto-fill the current date/time when the form opens (e.g. a note timestamp).
- picklist: single choice from a reusable list — set "picklist_code". Add config \
  {"allow_inline_create": true} to let users add new options on the fly (e.g. medicine name).
- multiselect: multiple choices from a reusable list — set "picklist_code".
- calculated: read-only computed value. Put the expression in config {"formula": \
  "weight / ((height/100) ** 2)"} referencing other field_keys.
- grid: a repeating table. Put columns in config {"grid_schema": {"columns": [ \
  {"key":"drug","label":"Drug","type":"text"}, {"key":"dose","label":"Dose","type":"text"}, \
  {"key":"status","label":"Status","type":"picklist","picklist_code":"medicine_status"} ]}}. \
  Column "type" is one of text/number/date/time/datetime/textarea/picklist.
- file: file/image upload.
- signature: signature capture (paper is signed physically; this records who/when).
- heading: a non-interactive sub-heading inside a section.
- api_select: options come from a LIVE app API rather than a picklist. Set config \
  {"api": "doctors"} to pick a doctor. Use for people/entities that live in other modules.
- pain_faces: Wong-Baker 0–10 face pain scale.
- data_ref: reference to another record/value (advanced; rarely needed).

## Field config vocabulary (put these inside a field's "config")
- "span": "full" | "half" | "third" — width of the field/section in the grid.
- "min","max","step": numeric bounds.
- "formula": expression for calculated fields.
- "grid_schema": columns for grid fields (see above).
- "picklist_code": (also a top-level field key) list to bind picklist/multiselect/grid columns.
- "select_from_list": true — attach a picklist to a textarea/rich_text as insertable snippets.
- "allow_inline_create": true — allow creating new picklist items inline.
- "options": inline [{"label","value"}] — only when a list is tiny, fixed, and not reused; \
  otherwise prefer a real picklist.
- "api": "doctors" — for api_select fields.
- "default_now": true — auto-fill current date/time on open (date/time/datetime).
- "source": "encounter.uhid" | "encounter.patient_name" | "encounter.age_gender" | \
  "encounter.ipd_no" | "encounter.doa" | "encounter.consulting_doctor" — read-only value \
  pulled from the encounter/patient context (use inside a banner section).
- "pull": {"source_form_code":"...","source_field_key":"...","label":"..."} — prefill \
  a value from another form in the same encounter.
- "visibility_rule": {"all":[{"field":"<field_key>","op":"eq","value":"..."}]} (or "any") \
  — show the field only when the rule matches. ops: eq, ne, in, gt, lt, truthy, falsy.

## Sections
- Each section has a stable snake_case "code" unique within the form, a "title", and \
  "fields". Order with "display_order".
- A patient banner section (read-only header) uses config {"render":"banner"} and fields \
  with "source":"encounter.*" and is_read_only true.

## Tabs (only when the form is clearly multi-view)
- Put a "tabs" array at the top level: [{"key","label","order"}]. Assign each section to a \
  tab with section "tab":"<key>". Use a component tab {"type":"component","component":"<key>"} \
  only if the user explicitly wants a built-in panel; otherwise use plain "form" tabs.

## Picklists
- Define reusable option lists once in the top-level "picklists" array and reference them by \
  "picklist_code" from fields (and grid columns). Reuse the SAME code across fields that share \
  options. Codes are snake_case. Provide sensible clinical items; include "label_mr" (Marathi) \
  when obvious. If a list already exists in the tenant, just reference its code without \
  redefining it.

## Images / photos
- If an image of a paper or printed form is provided, transcribe it FAITHFULLY: reproduce its \
  sections, field order, labels, and any printed option lists as picklists. Infer the best \
  field_type from how the paper field looks (checkbox -> boolean/yes_no; blank line -> text; \
  box of options -> picklist; table/grid -> grid). Keep the clinician's wording.

## Naming & quality
- Codes and field_keys: lowercase snake_case, stable, unique within the form.
- Labels: concise, clinically meaningful; keep the source wording for transcriptions.
- Mark genuinely mandatory fields is_required true; do not over-require.
- Add validation config where it clearly helps (numeric ranges for vitals).
- Prefer picklists over free text when options are known and finite.
- Do NOT invent tabs, components, or config keys not listed here.
- Output valid JSON only, matching the schema below.

JSON Schema:
"""
    + json.dumps(FORM_DRAFT_JSON_SCHEMA, indent=2)
)


_CODE_RE = re.compile(r"[^a-z0-9_]+")


def normalize_code(value: str, max_length: int = 64) -> str:
    """Return a snake_case code safe for Celiyo identifiers."""
    cleaned = (value or "").strip().lower()
    cleaned = cleaned.replace(" ", "_").replace("-", "_")
    cleaned = _CODE_RE.sub("", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:max_length] or "generated"


def _build_user_message(
    prompt: str,
    entity_type: str,
    extra_instructions: str = "",
    has_image: bool = False,
) -> str:
    entity_label = dict(ClinicalForm.EntityType.choices).get(entity_type, entity_type)
    parts = [
        f"Request: {prompt}" if prompt else "Design a clinical form based on the attached image.",
        f"Target encounter scope: {entity_label}.",
    ]
    if has_image:
        parts.append(
            "An image of a paper/printed form is attached. Transcribe it faithfully into the schema."
        )
    if extra_instructions:
        parts.append(f"Additional instructions: {extra_instructions}")
    parts.append("Return only the JSON object.")
    return "\n\n".join(parts)


def _normalize_draft_codes(draft: dict[str, Any]) -> dict[str, Any]:
    """Coerce all identifier fields to safe snake_case in place."""
    if draft.get("code"):
        draft["code"] = normalize_code(draft["code"])
    if draft.get("target_form_code"):
        draft["target_form_code"] = normalize_code(draft["target_form_code"])
    for section in draft.get("sections", []) or []:
        section["code"] = normalize_code(section.get("code", "section"))
        for field in section.get("fields", []) or []:
            field["field_key"] = normalize_code(field.get("field_key", "field"))
            if field.get("picklist_code"):
                field["picklist_code"] = normalize_code(field["picklist_code"])
    for picklist in draft.get("picklists", []) or []:
        picklist["code"] = normalize_code(picklist.get("code", "picklist"))
    return draft


def generate_form_draft(
    prompt: str,
    entity_type: str = ClinicalForm.EntityType.GENERIC,
    extra_instructions: str = "",
    image_data_url: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Call OpenAI and return ``(draft_dict, error_message)``.

    ``image_data_url`` is an optional ``data:image/...;base64,...`` string. When
    present a vision-capable model transcribes the paper form. On success
    ``error_message`` is None; on failure ``draft_dict`` is None.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        return None, "OPENAI_API_KEY is not configured."

    # gpt-4o is vision-capable and used for both text and image requests.
    model = getattr(settings, "OPENAI_FORM_MODEL", "gpt-4o") or "gpt-4o"

    client = OpenAI(api_key=api_key)
    user_text = _build_user_message(
        prompt, entity_type, extra_instructions, has_image=bool(image_data_url)
    )

    if image_data_url:
        user_content: Any = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    else:
        user_content = user_text

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=8192,
        )
    except Exception as exc:
        logger.error("openai_generation_failed", error=str(exc))
        return None, f"OpenAI request failed: {exc}"

    content = response.choices[0].message.content
    if not content:
        return None, "OpenAI returned an empty response."

    try:
        draft = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("openai_json_parse_failed", content=content[:500], error=str(exc))
        return None, f"OpenAI response was not valid JSON: {exc}"

    if not isinstance(draft, dict):
        return None, "OpenAI response was not a JSON object."

    # Default + sanitize the operation, then normalize all codes.
    if draft.get("operation") not in OPERATIONS:
        draft["operation"] = "create_form"
    draft = _normalize_draft_codes(draft)

    return draft, None
