"""Clinical foundation seed data.

Editable data lists consumed by the ``seed_clinical_foundation`` management command.
Keep these as pure data (no DB access) so they can be edited freely and re-seeded.
"""

from apps.clinical.seeds.catalog import (
    DOCUMENT_TEMPLATES,
    MRD_LINES,
    PRINT_TEMPLATES,
)
from apps.clinical.seeds.forms import FORMS
from apps.clinical.seeds.groups import FORM_GROUPS
from apps.clinical.seeds.picklists import PICKLIST_GROUPS, PICKLISTS
from apps.clinical.seeds.sections import SHARED_SECTIONS

__all__ = [
    "PICKLISTS",
    "PICKLIST_GROUPS",
    "SHARED_SECTIONS",
    "FORMS",
    "FORM_GROUPS",
    "MRD_LINES",
    "DOCUMENT_TEMPLATES",
    "PRINT_TEMPLATES",
]
