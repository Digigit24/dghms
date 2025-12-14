"""
Signal handlers for the patients app.

Handles automatic updates to patient records based on related model changes.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone


@receiver(post_save, sender='opd.Visit')
def update_patient_on_visit_create(sender, instance, created, **kwargs):
    """
    Update patient's total_visits and last_visit_date when a visit is created.

    Triggered after:
    - New OPD visit is created
    - Existing OPD visit is updated
    """
    from apps.patients.models import PatientProfile

    if instance.patient_id:
        patient = instance.patient

        # Count all visits except cancelled and no_show
        total_visits = patient.opd_visits.exclude(
            status__in=['cancelled', 'no_show']
        ).count()

        # Get the latest visit date (from all non-cancelled visits)
        latest_visit = patient.opd_visits.exclude(
            status__in=['cancelled', 'no_show']
        ).order_by('-visit_date', '-entry_time').first()
        last_visit_date = latest_visit.visit_date if latest_visit else None

        # Update patient record
        PatientProfile.objects.filter(id=patient.id).update(
            total_visits=total_visits,
            last_visit_date=timezone.datetime.combine(last_visit_date, timezone.datetime.min.time()) if last_visit_date else None
        )


@receiver(post_delete, sender='opd.Visit')
def update_patient_on_visit_delete(sender, instance, **kwargs):
    """
    Update patient's total_visits and last_visit_date when a visit is deleted.

    Triggered after:
    - OPD visit is deleted
    """
    from apps.patients.models import PatientProfile

    if instance.patient_id:
        patient_id = instance.patient_id

        try:
            patient = PatientProfile.objects.get(id=patient_id)

            # Count all visits except cancelled and no_show
            total_visits = patient.opd_visits.exclude(
                status__in=['cancelled', 'no_show']
            ).count()

            # Get the latest visit date (from all non-cancelled visits)
            latest_visit = patient.opd_visits.exclude(
                status__in=['cancelled', 'no_show']
            ).order_by('-visit_date', '-entry_time').first()
            last_visit_date = latest_visit.visit_date if latest_visit else None

            # Update patient record
            PatientProfile.objects.filter(id=patient.id).update(
                total_visits=total_visits,
                last_visit_date=timezone.datetime.combine(last_visit_date, timezone.datetime.min.time()) if last_visit_date else None
            )
        except PatientProfile.DoesNotExist:
            # Patient might have been deleted
            pass


@receiver(post_save, sender='patients.PatientVitals')
def log_vitals_update(sender, instance, created, **kwargs):
    """
    Optional: Log when patient vitals are recorded.
    Can be used for audit trails or notifications.
    """
    # Future: Add logging or notification logic here
    pass


@receiver(post_save, sender='patients.PatientAllergy')
def log_allergy_update(sender, instance, created, **kwargs):
    """
    Optional: Log when patient allergies are recorded.
    Can be used for critical alerts or notifications.
    """
    # Future: Add critical allergy notification logic here
    # For example: Send alert to all doctors if life_threatening allergy is added
    pass

