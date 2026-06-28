"""OpenAI integration for the clinical form AI wizard.

The helper in this module builds a strict system prompt + JSON schema so the
model returns a DigiHMS-compatible form draft. The draft is then validated and
applied to real ``ClinicalForm`` / ``ClinicalFormSection`` /
``ClinicalFormField`` / ``ClinicalPicklist`` records.
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

# Allowed field types in the new clinical form engine.
FIELD_TYPES = [choice[0] for choice in ClinicalFormField.FieldType.choices]

# JSON Schema returned by the model. Keep this in sync with
# ``ClinicalForm``, ``ClinicalFormSection``, ``ClinicalFormField`` and
# ``ClinicalPicklist`` / ``ClinicalPicklistItem``.
FORM_DRAFT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code", "name", "sections"],
    "properties": {
        "code": {
            "type": "string",
            "maxLength": 64,
            "description": "Stable snake_case machine identifier for the form, e.g. 'diabetes_opd_followup'.",
        },
        "name": {
            "type": "string",
            "maxLength": 200,
            "description": "Human-readable form name, e.g. 'Diabetes OPD Follow-up'.",
        },
        "description": {
            "type": "string",
            "description": "Short purpose/context of the form.",
        },
        "config": {
            "type": "object",
            "description": "Optional display/layout configuration for the form.",
            "additionalProperties": True,
        },
        "sections": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code", "title", "fields"],
                "properties": {
                    "code": {
                        "type": "string",
                        "maxLength": 64,
                        "description": "Stable snake_case identifier for the section, unique within the form.",
                    },
                    "title": {
                        "type": "string",
                        "maxLength": 200,
                        "description": "Section heading.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional section description.",
                    },
                    "display_order": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Order among sections (0-based).",
                    },
                    "is_collapsed": {
                        "type": "boolean",
                        "description": "Whether the section should render collapsed by default.",
                    },
                    "config": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                    "fields": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["field_key", "field_type", "label"],
                            "properties": {
                                "field_key": {
                                    "type": "string",
                                    "maxLength": 64,
                                    "description": "Stable snake_case identifier unique within the form.",
                                },
                                "field_type": {
                                    "type": "string",
                                    "enum": FIELD_TYPES,
                                    "description": "Must be one of the supported DigiHMS field types.",
                                },
                                "label": {
                                    "type": "string",
                                    "maxLength": 255,
                                    "description": "User-facing question label.",
                                },
                                "help_text": {
                                    "type": "string",
                                    "maxLength": 500,
                                    "description": "Hint shown under the field.",
                                },
                                "display_order": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "description": "Order within the section.",
                                },
                                "is_required": {"type": "boolean"},
                                "is_read_only": {"type": "boolean"},
                                "default_value": {
                                    "type": ["string", "number", "boolean", "array", "object", "null"],
                                    "description": "Optional default value (any JSON-compatible value).",
                                },
                                "config": {
                                    "type": "object",
                                    "description": "Validation/display logic (min/max for numbers, formula for calculated, etc.).",
                                    "additionalProperties": True,
                                },
                                "picklist_code": {
                                    "type": "string",
                                    "maxLength": 64,
                                    "description": "Reference to a picklist defined in 'picklists' by code. Required for 'picklist' and 'multiselect' fields.",
                                },
                            },
                        },
                    },
                },
            },
        },
        "picklists": {
            "type": "array",
            "description": "Reusable option lists referenced by picklist_code in fields.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code", "name", "items"],
                "properties": {
                    "code": {
                        "type": "string",
                        "maxLength": 64,
                        "description": "Stable snake_case identifier for the picklist.",
                    },
                    "name": {
                        "type": "string",
                        "maxLength": 200,
                        "description": "Human-readable picklist name.",
                    },
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
                                "display_order": {"type": "integer", "minimum": 0},
                            },
                        },
                    },
                },
            },
        },
    },
}

SYSTEM_PROMPT = """You are a clinical form designer for DigiHMS, a hospital management system.

Your job is to convert a natural-language request into a structured clinical form definition matching the JSON schema below.

Rules:
- Use only the field types: text, textarea, number, boolean, date, datetime, picklist, multiselect, file, calculated.
- For picklist/multiselect fields, reference a reusable picklist defined in the top-level "picklists" array via "picklist_code".
- Choose field keys and section codes that are stable, lowercase, snake_case, and unique within the form.
- Keep labels concise and clinically meaningful.
- Include sensible validation config where appropriate (e.g. {"min": 0, "max": 250} for numeric vitals).
- For calculated fields, include a "formula" key in config (e.g. "weight / ((height/100) ** 2)").
- Do not include any prose outside the JSON object. Return only valid JSON.

JSON Schema:
""" + json.dumps(FORM_DRAFT_JSON_SCHEMA, indent=2)


_CODE_RE = re.compile(r"[^a-z0-9_]+")


def normalize_code(value: str, max_length: int = 64) -> str:
    """Return a snake_case code safe for DigiHMS identifiers."""
    cleaned = value.strip().lower()
    cleaned = cleaned.replace(" ", "_").replace("-", "_")
    cleaned = _CODE_RE.sub("", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:max_length] or "generated"


def _build_user_message(
    prompt: str,
    entity_type: str,
    extra_instructions: str = "",
) -> str:
    entity_label = dict(ClinicalForm.EntityType.choices).get(entity_type, entity_type)
    parts = [
        f"Design a clinical form for: {prompt}",
        f"The form should be used for {entity_label} encounters.",
    ]
    if extra_instructions:
        parts.append(f"Additional instructions: {extra_instructions}")
    return "\n\n".join(parts)


def generate_form_draft(
    prompt: str,
    entity_type: str = ClinicalForm.EntityType.GENERIC,
    extra_instructions: str = "",
) -> tuple[dict[str, Any] | None, str | None]:
    """Call OpenAI and return (draft_dict, error_message).

    If the call succeeds and the response parses, ``error_message`` is None.
    On any failure, ``draft_dict`` is None and ``error_message`` describes why.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        return None, "OPENAI_API_KEY is not configured."

    model = getattr(settings, "OPENAI_FORM_MODEL", "gpt-4o-mini") or "gpt-4o-mini"

    client = OpenAI(api_key=api_key)
    user_message = _build_user_message(prompt, entity_type, extra_instructions)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=4096,
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

    # Post-process codes to be safe.
    draft["code"] = normalize_code(draft.get("code", "generated_form"))
    for section in draft.get("sections", []):
        section["code"] = normalize_code(section.get("code", "section"))
        for field in section.get("fields", []):
            field["field_key"] = normalize_code(field.get("field_key", "field"))
            if field.get("picklist_code"):
                field["picklist_code"] = normalize_code(field["picklist_code"])
    for picklist in draft.get("picklists", []):
        picklist["code"] = normalize_code(picklist.get("code", "picklist"))

    return draft, None
