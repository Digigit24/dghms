# apps/opd/management/commands/seed_jeevisha_template_v2.py
"""
Seed V2 of the Jeevisha Pain OPD clinical-notes template.

V2 differs from V1 in exactly one way: the five examination multiselects
(L/S Spine, C Spine, Left Knee, Right Knee, Shoulder) are converted from
``field_type="multiselect"`` to ``field_type="json"``. Their options no
longer live in the ClinicalNoteTemplateFieldOption table — instead, the
option list AND the widget config are embedded inside the field's
``help_text`` JSON:

    {
      "widget": "multiselect_with_option_notes",
      "hide_label": true,
      "orientation": "vertical",
      "options": [
        {"label": "SLR", "value": "slr"},
        ...
      ]
    }

The renderer reads ``cfg.options`` to draw checkboxes and stores the
selected option values plus per-option notes in ``value_json`` on the
response. ``selected_options`` is unused for these fields.

Everything else (sections, subsections, other field types, ``pmh_conditions``
multiselect, ``diet`` select) is identical to V1 and is reused via import.

Notes:
  * V2 uses its own template code (``JEEVISHA_PAIN_OPD_V2``) so V1 is left
    untouched. The new template will land at the next free id.
  * If you previously ran an older V2 that seeded option rows for these
    fields, run with ``--reset`` to wipe orphan options on first migration.
  * ``help_text`` is a CharField(500). The five embeddings are 270–350
    chars each, well under the limit. The build step asserts this so a
    future option-list addition fails loudly instead of being truncated
    silently.

Usage:
    python manage.py seed_jeevisha_template_v2 --tenant-id=<UUID>
    python manage.py seed_jeevisha_template_v2 --tenant-id=<UUID> --reset
    python manage.py seed_jeevisha_template_v2 --tenant-id=<UUID> --dry-run

Example:
    python manage.py seed_jeevisha_template_v2 \
        --tenant-id=615da126-a7d8-4112-a5ae-45bca4c623b6
"""
import copy
import json

from apps.opd.management.commands import seed_jeevisha_template as v1


# ----------------------------------------------------------------------------
# V2 template identity
# ----------------------------------------------------------------------------

TEMPLATE_CODE_V2 = 'JEEVISHA_PAIN_OPD_V2'
TEMPLATE_NAME_V2 = 'Jeevisha Pain OPD (V2 — json findings)'
TEMPLATE_DESCRIPTION_V2 = (
    'V2 of the Jeevisha clinical-notes template. The 5 examination findings '
    '(L/S Spine, C Spine, Left/Right Knee, Shoulder) are stored as '
    'field_type="json" with options embedded in help_text. Each selected '
    'option carries its own short text note inside value_json — '
    'selected_options is not used for these fields. All other fields are '
    'identical to V1.'
)


# ----------------------------------------------------------------------------
# Fields converted from multiselect → json, with options embedded inline.
# The key is field_name (matches V1 spec). The value is the option list that
# would otherwise live in OPTIONS_SPEC. Keeping them here keeps the
# conversion self-documenting.
# ----------------------------------------------------------------------------

JSON_WIDGET_FIELDS = {
    'ls_spine_findings': [
        {'label': 'SLR', 'value': 'slr'},
        {'label': "Patrick's", 'value': 'patricks'},
        {'label': 'FAIR', 'value': 'fair'},
        {'label': 'Sp Tenderness', 'value': 'sp_tenderness'},
        {'label': 'P/S Tenderness', 'value': 'ps_tenderness'},
        {'label': 'Flex / Ext', 'value': 'flex_ext'},
    ],
    'c_spine_findings': [
        {'label': 'Axial', 'value': 'axial'},
        {'label': 'Spurling', 'value': 'spurling'},
        {'label': 'Sp Tenderness', 'value': 'sp_tenderness'},
        {'label': 'P/S Tenderness', 'value': 'ps_tenderness'},
        {'label': 'Flex / Ext / Rot', 'value': 'flex_ext_rot'},
        {'label': 'Trap TP', 'value': 'trap_tp'},
    ],
    'left_knee_findings': [
        {'label': 'Crepitus', 'value': 'crepitus'},
        {'label': 'Tender', 'value': 'tender'},
        {'label': "Apley's", 'value': 'apleys'},
        {'label': 'Drawer', 'value': 'drawer'},
        {'label': 'ROM', 'value': 'rom'},
    ],
    'right_knee_findings': [
        {'label': 'Crepitus', 'value': 'crepitus'},
        {'label': 'Tender', 'value': 'tender'},
        {'label': "Apley's", 'value': 'apleys'},
        {'label': 'Drawer', 'value': 'drawer'},
        {'label': 'ROM', 'value': 'rom'},
    ],
    'shoulder_findings': [
        {'label': 'ROM Active', 'value': 'rom_active'},
        {'label': 'ROM Passive', 'value': 'rom_passive'},
        {'label': "Neer's", 'value': 'neers'},
        {'label': "O'Brien", 'value': 'obrien'},
        {'label': 'Rotator Cuff', 'value': 'rotator_cuff'},
    ],
}


# Hard cap from ClinicalNoteTemplateField.help_text = CharField(max_length=500)
HELP_TEXT_MAX = 500


def _make_json_help_text(options):
    """Build the help_text JSON for a json-typed multiselect-with-notes field."""
    return json.dumps(
        {
            'widget': 'multiselect_with_option_notes',
            'hide_label': True,
            'orientation': 'vertical',
            'options': options,
        },
        separators=(',', ':'),
    )


def _build_v2_spec():
    """Clone V1's FIELD_SPEC and convert the listed multiselects to json."""
    spec = copy.deepcopy(v1.FIELD_SPEC)
    converted = 0
    for entry in spec:
        name = entry['field_name']
        if name not in JSON_WIDGET_FIELDS:
            continue

        entry['field_type'] = 'json'
        entry['help_text'] = _make_json_help_text(JSON_WIDGET_FIELDS[name])

        if len(entry['help_text']) > HELP_TEXT_MAX:
            raise RuntimeError(
                f'help_text for {name} is {len(entry["help_text"])} chars — '
                f'exceeds CharField(max_length={HELP_TEXT_MAX}). '
                f'Shorten option labels or bump the model field length.'
            )
        converted += 1

    if converted != len(JSON_WIDGET_FIELDS):
        missing = set(JSON_WIDGET_FIELDS) - {e['field_name'] for e in spec}
        raise RuntimeError(
            f'V2 expected to convert {len(JSON_WIDGET_FIELDS)} fields, '
            f'converted {converted}. Missing from V1 spec: {missing}. '
            f'Has V1\'s FIELD_SPEC changed?'
        )
    return spec


def _build_v2_options():
    """V1's OPTIONS_SPEC minus the fields we converted to json."""
    return {
        k: v for k, v in v1.OPTIONS_SPEC.items()
        if k not in JSON_WIDGET_FIELDS
    }


# ----------------------------------------------------------------------------
# Command — inherits V1's seeding logic. The patched module globals propagate
# through V1's _seed_fields and _verify because those methods read globals
# directly. The try/finally restores V1 even on exception so other commands
# using V1 in the same process continue to work.
# ----------------------------------------------------------------------------

class Command(v1.Command):
    help = 'Seed the Jeevisha Pain OPD V2 template (json findings with per-option notes).'

    def handle(self, *args, **opts):
        saved = (
            v1.TEMPLATE_CODE,
            v1.TEMPLATE_NAME,
            v1.TEMPLATE_DESCRIPTION,
            v1.FIELD_SPEC,
            v1.OPTIONS_SPEC,
        )
        try:
            v1.TEMPLATE_CODE = TEMPLATE_CODE_V2
            v1.TEMPLATE_NAME = TEMPLATE_NAME_V2
            v1.TEMPLATE_DESCRIPTION = TEMPLATE_DESCRIPTION_V2
            v1.FIELD_SPEC = _build_v2_spec()
            v1.OPTIONS_SPEC = _build_v2_options()
            super().handle(*args, **opts)
        finally:
            (
                v1.TEMPLATE_CODE,
                v1.TEMPLATE_NAME,
                v1.TEMPLATE_DESCRIPTION,
                v1.FIELD_SPEC,
                v1.OPTIONS_SPEC,
            ) = saved
