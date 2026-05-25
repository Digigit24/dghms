# apps/opd/management/commands/seed_jeevisha_template.py
"""
Seed the Jeevisha Pain OPD clinical-notes template.

Creates a new ClinicalNoteTemplate (or updates an existing one with the same
code) with sections, subsections, and fields matching the Jeevisha Hospital
paper consultation form.

Section/subsection markers are encoded as regular text fields with a
``field_name`` prefix (``__sec_``, ``__sub_``) and JSON metadata in
``help_text``. The frontend parses these to render groupings, columns,
and layouts -- the backend stores them as ordinary fields.

Usage:
    python manage.py seed_jeevisha_template --tenant-id=<UUID>
    python manage.py seed_jeevisha_template --tenant-id=<UUID> --reset
    python manage.py seed_jeevisha_template --tenant-id=<UUID> --dry-run
    python manage.py seed_jeevisha_template --tenant-id=<UUID> --reset --no-input
"""
import json
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.opd.models import (
    ClinicalNoteTemplate,
    ClinicalNoteTemplateField,
    ClinicalNoteTemplateFieldOption,
    ClinicalNoteTemplateFieldResponse,
)


# ----------------------------------------------------------------------------
# Template identity
# ----------------------------------------------------------------------------

TEMPLATE_CODE = 'JEEVISHA_PAIN_OPD'
TEMPLATE_NAME = 'Jeevisha Pain OPD'
TEMPLATE_DESCRIPTION = (
    'Clinical notes template for Jeevisha Spine | Pain | Regenerative Hospital. '
    'Mirrors the printed paper consultation form layout.'
)


# ----------------------------------------------------------------------------
# help_text JSON helper
# ----------------------------------------------------------------------------

def _h(**kwargs):
    """Serialize a help_text JSON config compactly (CharField max_length=500)."""
    return json.dumps(kwargs, separators=(',', ':'))


# ----------------------------------------------------------------------------
# Field specification
#
# Order in this list IS the display_order. Each entry becomes one row in
# ClinicalNoteTemplateField. Options for multiselect/select fields live in
# OPTIONS_SPEC below, keyed by field_name.
# ----------------------------------------------------------------------------

FIELD_SPEC = [
    # ====================================================================
    # SECTION 1 — CHIEF COMPLAINT (3-column patient header area)
    # ====================================================================
    {
        'field_name': '__sec_chief_complaint',
        'field_label': 'Chief Complaint',
        'field_type': 'text',
        'help_text': _h(role='section', columns=3, hide_label=True),
    },

    # --- Column 1: Pain history ---
    {
        'field_name': '__sub_pain_history',
        'field_label': 'Pain History',
        'field_type': 'text',
        'help_text': _h(role='subsection', parent='__sec_chief_complaint', hide_label=True),
    },
    {
        'field_name': 'co_pain_site',
        'field_label': 'Site',
        'field_type': 'text',
        'help_text': _h(prefix='C/O Pain :', inline_label=True, compact=True),
    },
    {
        'field_name': 'co_pain_type',
        'field_label': 'Type',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'duration',
        'field_label': 'Duration',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'radiation',
        'field_label': 'Radiation',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'aggravated_on',
        'field_label': 'Aggravated on',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'relieved_on',
        'field_label': 'Relieved on',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },

    # --- Column 2: Neurological symptoms ---
    {
        'field_name': '__sub_neuro_symptoms',
        'field_label': 'Neuro Symptoms',
        'field_type': 'text',
        'help_text': _h(role='subsection', parent='__sec_chief_complaint', hide_label=True),
    },
    {
        'field_name': 'tingling',
        'field_label': 'Tingling',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'numbness',
        'field_label': 'Numbness',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'burning',
        'field_label': 'Burning',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'weakness',
        'field_label': 'Weakness',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'ems',
        'field_label': 'EMS',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'associated_features',
        'field_label': 'Associated Features',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },

    # --- Column 3: Visit info ---
    {
        'field_name': '__sub_visit_info',
        'field_label': 'Visit Info',
        'field_type': 'text',
        'help_text': _h(role='subsection', parent='__sec_chief_complaint', hide_label=True),
    },
    {
        'field_name': 'direct_referral',
        'field_label': 'Direct / Referral',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'bowel_bladder',
        'field_label': 'B/B',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'acidity_sleep_appetite',
        'field_label': 'Acidity / Sleep / Appetite',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'treatment_history',
        'field_label': 'Treatment History',
        'field_type': 'textarea',
        'help_text': _h(inline_label=True, compact=True),
    },

    # ====================================================================
    # SECTION 2 — PAST MEDICAL HISTORY (inline row)
    # ====================================================================
    {
        'field_name': '__sec_pmh',
        'field_label': 'Past Medical History',
        'field_type': 'text',
        'help_text': _h(role='section', columns=1, layout='inline_row'),
    },
    {
        'field_name': 'pmh_conditions',
        'field_label': 'Conditions',
        'field_type': 'multiselect',
        'help_text': _h(hide_label=True, inline_options=True),
    },
    {
        'field_name': 'allergies',
        'field_label': 'Allergies',
        'field_type': 'textarea',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'addiction',
        'field_label': 'Addiction',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'occupation',
        'field_label': 'Occupation',
        'field_type': 'text',
        'help_text': _h(inline_label=True, compact=True),
    },
    {
        'field_name': 'diet',
        'field_label': 'Veg / Non-veg',
        'field_type': 'select',
        'help_text': _h(inline_label=True, compact=True),
    },

    # ====================================================================
    # SECTION 3 — EXAMINATION (3 columns: L/S Spine | C Spine | Body Diagram)
    # ====================================================================
    {
        'field_name': '__sec_examination',
        'field_label': 'Examination',
        'field_type': 'text',
        'help_text': _h(role='section', columns=3, column_widths=['1fr', '1fr', '1.5fr']),
    },

    # --- Subsection: L/S Spine ---
    {
        'field_name': '__sub_ls_spine',
        'field_label': 'L/S Spine',
        'field_type': 'text',
        'help_text': _h(role='subsection', parent='__sec_examination'),
    },
    {
        'field_name': 'ls_spine_findings',
        'field_label': 'L/S Spine Findings',
        'field_type': 'multiselect',
        'help_text': _h(hide_label=True, orientation='vertical', allow_notes=True),
    },

    # --- Subsection: C Spine ---
    {
        'field_name': '__sub_c_spine',
        'field_label': 'C Spine',
        'field_type': 'text',
        'help_text': _h(role='subsection', parent='__sec_examination'),
    },
    {
        'field_name': 'c_spine_findings',
        'field_label': 'C Spine Findings',
        'field_type': 'multiselect',
        'help_text': _h(hide_label=True, orientation='vertical', allow_notes=True),
    },

    # --- Subsection: Body Diagram (canvas with anatomy background) ---
    {
        'field_name': '__sub_body_diagram',
        'field_label': 'Body Diagram',
        'field_type': 'text',
        'help_text': _h(role='subsection', parent='__sec_examination', hide_label=True, row_span=2),
    },
    {
        'field_name': 'body_diagram_canvas',
        'field_label': 'Mark pain points',
        'field_type': 'image',
        'help_text': _h(hide_label=True, canvas=True, background_asset='anatomy_front_back.svg'),
    },

    # ====================================================================
    # SECTION 4 — KNEE (2 columns: Left | Right)
    # ====================================================================
    {
        'field_name': '__sec_knee',
        'field_label': 'Knee',
        'field_type': 'text',
        'help_text': _h(role='section', columns=2),
    },
    {
        'field_name': '__sub_knee_left',
        'field_label': 'Left',
        'field_type': 'text',
        'help_text': _h(role='subsection', parent='__sec_knee'),
    },
    {
        'field_name': 'left_knee_findings',
        'field_label': 'Left Knee Findings',
        'field_type': 'multiselect',
        'help_text': _h(hide_label=True, orientation='vertical', allow_notes=True),
    },
    {
        'field_name': '__sub_knee_right',
        'field_label': 'Right',
        'field_type': 'text',
        'help_text': _h(role='subsection', parent='__sec_knee'),
    },
    {
        'field_name': 'right_knee_findings',
        'field_label': 'Right Knee Findings',
        'field_type': 'multiselect',
        'help_text': _h(hide_label=True, orientation='vertical', allow_notes=True),
    },

    # ====================================================================
    # SECTION 5 — SHOULDER
    # ====================================================================
    {
        'field_name': '__sec_shoulder',
        'field_label': 'Shoulder',
        'field_type': 'text',
        'help_text': _h(role='section', columns=1),
    },
    {
        'field_name': 'shoulder_findings',
        'field_label': 'Shoulder Findings',
        'field_type': 'multiselect',
        'help_text': _h(hide_label=True, orientation='vertical', allow_notes=True),
    },

    # ====================================================================
    # SECTION 6 — PROVISIONAL DIAGNOSIS + Rx
    # ====================================================================
    {
        'field_name': '__sec_diagnosis',
        'field_label': 'Provisional Diagnosis',
        'field_type': 'text',
        'help_text': _h(role='section', columns=1),
    },
    {
        'field_name': 'provisional_diagnosis',
        'field_label': 'Diagnosis',
        'field_type': 'textarea',
        'help_text': _h(hide_label=True),
    },
    {
        'field_name': 'prescription',
        'field_label': 'Rx',
        'field_type': 'textarea',
        'help_text': _h(inline_label=True),
    },

    # ====================================================================
    # SECTION 7 — PLAN
    # ====================================================================
    {
        'field_name': '__sec_plan',
        'field_label': 'Plan',
        'field_type': 'text',
        'help_text': _h(role='section', columns=1),
    },
    {
        'field_name': 'plan_text',
        'field_label': 'Plan',
        'field_type': 'textarea',
        'help_text': _h(hide_label=True),
    },

    # ====================================================================
    # SECTION 8 — PHYSIOTHERAPY
    # ====================================================================
    {
        'field_name': '__sec_physio',
        'field_label': 'Physiotherapy',
        'field_type': 'text',
        'help_text': _h(role='section', columns=1),
    },
    {
        'field_name': 'physiotherapy_text',
        'field_label': 'Physiotherapy',
        'field_type': 'textarea',
        'help_text': _h(hide_label=True),
    },

    # ====================================================================
    # SECTION 9 — FOLLOW UP
    # ====================================================================
    {
        'field_name': '__sec_followup',
        'field_label': 'Follow up',
        'field_type': 'text',
        'help_text': _h(role='section', columns=1),
    },
    {
        'field_name': 'follow_up',
        'field_label': 'Follow up',
        'field_type': 'datetime',
        'help_text': _h(inline_label=True, compact=True),
    },
]


# ----------------------------------------------------------------------------
# Options for multiselect / select fields (keyed by field_name)
# Tuples are (option_label, option_value).
# ----------------------------------------------------------------------------

OPTIONS_SPEC = {
    'pmh_conditions': [
        ('DM', 'dm'),
        ('HTN', 'htn'),
        ('TB', 'tb'),
        ('Thyroid', 'thyroid'),
    ],
    'diet': [
        ('Veg', 'veg'),
        ('Non-veg', 'non_veg'),
    ],
    'ls_spine_findings': [
        ('SLR', 'slr'),
        ("Patrick's", 'patricks'),
        ('FAIR', 'fair'),
        ('Sp Tenderness', 'sp_tenderness'),
        ('P/S Tenderness', 'ps_tenderness'),
        ('Flex / Ext', 'flex_ext'),
    ],
    'c_spine_findings': [
        ('Axial', 'axial'),
        ('Spurling', 'spurling'),
        ('Sp Tenderness', 'sp_tenderness'),
        ('P/S Tenderness', 'ps_tenderness'),
        ('Flex / Ext / Rot', 'flex_ext_rot'),
        ('Trap TP', 'trap_tp'),
    ],
    'left_knee_findings': [
        ('Crepitus', 'crepitus'),
        ('Tender', 'tender'),
        ("Apley's", 'apleys'),
        ('Drawer', 'drawer'),
        ('ROM', 'rom'),
    ],
    'right_knee_findings': [
        ('Crepitus', 'crepitus'),
        ('Tender', 'tender'),
        ("Apley's", 'apleys'),
        ('Drawer', 'drawer'),
        ('ROM', 'rom'),
    ],
    'shoulder_findings': [
        ('ROM Active', 'rom_active'),
        ('ROM Passive', 'rom_passive'),
        ("Neer's", 'neers'),
        ("O'Brien", 'obrien'),
        ('Rotator Cuff', 'rotator_cuff'),
    ],
}


# ----------------------------------------------------------------------------
# Management command
# ----------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Seed the Jeevisha Pain OPD clinical-notes template for a tenant.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            required=True,
            type=str,
            help='Tenant UUID this template belongs to.',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete the template\'s existing fields and options before seeding. '
                 'Destructive — also deletes any field responses on those fields.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would happen without writing to the database.',
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Skip the confirmation prompt when --reset is used.',
        )

    def handle(self, *args, **opts):
        tenant_id_raw = opts['tenant_id']
        reset = opts['reset']
        dry_run = opts['dry_run']
        no_input = opts['no_input']

        # Validate tenant UUID up front.
        try:
            tenant_id = uuid.UUID(tenant_id_raw)
        except (ValueError, TypeError):
            raise CommandError(f'Invalid tenant UUID: {tenant_id_raw!r}')

        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO(f'  Seed: {TEMPLATE_NAME}'))
        self.stdout.write(self.style.HTTP_INFO(f'  Tenant: {tenant_id}'))
        self.stdout.write(self.style.HTTP_INFO(f'  Code: {TEMPLATE_CODE}'))
        self.stdout.write(self.style.HTTP_INFO(f'  Fields in spec: {len(FIELD_SPEC)}'))
        self.stdout.write(self.style.HTTP_INFO(f'  Option groups: {len(OPTIONS_SPEC)}'))
        if dry_run:
            self.stdout.write(self.style.WARNING('  Mode: DRY-RUN (no writes)'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))

        # Dry-run mode: print plan and exit.
        if dry_run:
            self._print_plan(tenant_id)
            return

        # Existing-template safety check (for --reset).
        existing = ClinicalNoteTemplate.objects.filter(
            tenant_id=tenant_id, code=TEMPLATE_CODE
        ).first()

        if existing and reset and not no_input:
            response_count = ClinicalNoteTemplateFieldResponse.objects.filter(
                tenant_id=tenant_id,
                field_responses__field__template=existing,
            ).distinct().count() if False else 0
            # Simpler: just count fields that will be wiped.
            field_count = existing.fields.count()
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f'Template id={existing.id} already exists with {field_count} fields. '
                f'--reset will DELETE all of them and any patient responses on them.'
            ))
            confirm = input('Type "yes" to continue: ').strip().lower()
            if confirm != 'yes':
                self.stdout.write(self.style.ERROR('Aborted.'))
                return

        # Do the work.
        try:
            with transaction.atomic():
                template = self._upsert_template(tenant_id, reset=reset)
                self._seed_fields(template)
                self._verify(template)
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'Seeding failed: {exc}'))
            raise

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'✓ Seeded template {TEMPLATE_CODE} (id={template.id}) '
            f'with {len(FIELD_SPEC)} fields for tenant {tenant_id}'
        ))
        self.stdout.write('')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _upsert_template(self, tenant_id, reset):
        """Create or fetch the template. If --reset, wipe its fields first."""
        template, created = ClinicalNoteTemplate.objects.update_or_create(
            tenant_id=tenant_id,
            code=TEMPLATE_CODE,
            defaults={
                'name': TEMPLATE_NAME,
                'description': TEMPLATE_DESCRIPTION,
                'is_active': True,
                'display_order': 100,
            },
        )

        if created:
            self.stdout.write(f'  → Created template id={template.id}')
        else:
            self.stdout.write(f'  → Found existing template id={template.id}')
            if reset:
                count = template.fields.count()
                template.fields.all().delete()  # CASCADE removes options + responses
                self.stdout.write(self.style.WARNING(
                    f'  → Reset: deleted {count} existing fields (and their options)'
                ))

        return template

    def _seed_fields(self, template):
        """Walk FIELD_SPEC, upsert each field, sync options where applicable."""
        self.stdout.write('')
        self.stdout.write('  Fields:')

        for display_order, spec in enumerate(FIELD_SPEC):
            field, created = ClinicalNoteTemplateField.objects.update_or_create(
                template=template,
                field_name=spec['field_name'],
                defaults={
                    'tenant_id': template.tenant_id,
                    'field_label': spec['field_label'],
                    'field_type': spec['field_type'],
                    'help_text': spec.get('help_text', ''),
                    'placeholder': spec.get('placeholder', ''),
                    'default_value': spec.get('default_value', ''),
                    'is_required': spec.get('is_required', False),
                    'is_active': spec.get('is_active', True),
                    'display_order': display_order,
                    'column_width': spec.get('column_width', 12),
                },
            )
            verb = 'create' if created else 'update'
            role = self._role_for(spec)
            self.stdout.write(
                f'    [{display_order:02d}] {verb:6s} {spec["field_name"]:30s} '
                f'({spec["field_type"]:11s}) {role}'
            )

            # Sync options if this field has any.
            if field.field_name in OPTIONS_SPEC:
                self._sync_options(field, OPTIONS_SPEC[field.field_name])

    def _sync_options(self, field, option_pairs):
        """
        Replace all options on the field with the spec'd list.
        Match by option_value to preserve IDs for existing options where
        possible (so prior multiselect responses keep their links).
        """
        existing = {opt.option_value: opt for opt in field.options.all()}
        spec_values = {value for _label, value in option_pairs}

        # Delete options not in spec.
        for value, opt in existing.items():
            if value not in spec_values:
                opt.delete()

        # Upsert each spec option.
        for order, (label, value) in enumerate(option_pairs):
            ClinicalNoteTemplateFieldOption.objects.update_or_create(
                field=field,
                option_value=value,
                defaults={
                    'tenant_id': field.tenant_id,
                    'option_label': label,
                    'display_order': order,
                    'is_active': True,
                },
            )

        self.stdout.write(f'           options: {len(option_pairs)}')

    def _verify(self, template):
        """Sanity check after seeding."""
        actual_field_count = template.fields.count()
        expected = len(FIELD_SPEC)
        if actual_field_count != expected:
            raise CommandError(
                f'Verification failed: expected {expected} fields, found '
                f'{actual_field_count} after seeding.'
            )

        for field_name, opts in OPTIONS_SPEC.items():
            field = template.fields.filter(field_name=field_name).first()
            if not field:
                raise CommandError(f'Missing field {field_name} after seeding.')
            actual = field.options.count()
            if actual != len(opts):
                raise CommandError(
                    f'Field {field_name} has {actual} options, expected {len(opts)}.'
                )

    def _print_plan(self, tenant_id):
        """Dry-run output."""
        existing = ClinicalNoteTemplate.objects.filter(
            tenant_id=tenant_id, code=TEMPLATE_CODE
        ).first()

        self.stdout.write('')
        if existing:
            self.stdout.write(
                f'  Existing template found: id={existing.id}, '
                f'fields={existing.fields.count()}'
            )
        else:
            self.stdout.write('  No existing template — will create.')

        self.stdout.write('')
        self.stdout.write('  Plan:')
        for display_order, spec in enumerate(FIELD_SPEC):
            role = self._role_for(spec)
            opts = f', {len(OPTIONS_SPEC[spec["field_name"]])} options' \
                if spec['field_name'] in OPTIONS_SPEC else ''
            self.stdout.write(
                f'    [{display_order:02d}] {spec["field_name"]:30s} '
                f'({spec["field_type"]}){opts} {role}'
            )
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('  No changes written (dry-run).'))

    @staticmethod
    def _role_for(spec):
        """Extract role tag from help_text JSON for log readability."""
        try:
            cfg = json.loads(spec.get('help_text', '') or '{}')
        except json.JSONDecodeError:
            return ''
        role = cfg.get('role')
        if role == 'section':
            return f'-- section (cols={cfg.get("columns", 1)})'
        if role == 'subsection':
            return f'-- subsection of {cfg.get("parent", "?")}'
        return ''