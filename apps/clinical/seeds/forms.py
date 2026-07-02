"""Aggregated list of all system forms (foundation)."""

from apps.clinical.seeds.forms_charts import CHART_FORMS
from apps.clinical.seeds.forms_ipd import IPD_FORMS
from apps.clinical.seeds.forms_operative import OPERATIVE_FORMS
from apps.clinical.seeds.forms_opd import OPD_FORMS

FORMS = [
    *IPD_FORMS,
    *OPERATIVE_FORMS,
    *CHART_FORMS,
    *OPD_FORMS,
]
