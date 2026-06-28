"""Django signals for clinical cache invalidation.

Any write to a form, section, or field busts the cached form structure so
that the next read rebuilds it from the database.
"""

import structlog
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from common.cache import CeliyoCache
from .models import ClinicalForm, ClinicalFormSection, ClinicalFormField

logger = structlog.get_logger(__name__)


def _bust_form_cache(instance):
    """Invalidate cached structure for the affected form."""
    form_id = getattr(instance, "form_id", None)
    if form_id is None and isinstance(instance, ClinicalForm):
        form_id = instance.pk
    if form_id is None:
        return
    try:
        CeliyoCache().delete_pattern(f"clinical:form:{form_id}:*")
        logger.info("clinical_form_cache_busted", form_id=form_id)
    except Exception as exc:
        logger.warning("clinical_cache_bust_failed", form_id=form_id, error=str(exc))


@receiver(post_save, sender=ClinicalForm)
def form_saved(sender, instance, **kwargs):
    _bust_form_cache(instance)


@receiver(post_delete, sender=ClinicalForm)
def form_deleted(sender, instance, **kwargs):
    _bust_form_cache(instance)


@receiver(post_save, sender=ClinicalFormSection)
def section_saved(sender, instance, **kwargs):
    _bust_form_cache(instance)


@receiver(post_delete, sender=ClinicalFormSection)
def section_deleted(sender, instance, **kwargs):
    _bust_form_cache(instance)


@receiver(post_save, sender=ClinicalFormField)
def field_saved(sender, instance, **kwargs):
    _bust_form_cache(instance)


@receiver(post_delete, sender=ClinicalFormField)
def field_deleted(sender, instance, **kwargs):
    _bust_form_cache(instance)
