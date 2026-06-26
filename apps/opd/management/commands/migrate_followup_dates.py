"""
Management command: migrate_followup_dates

Copies next_followup_date from the old ClinicalNote model into the canonical
Visit.follow_up_date field so the frontend can read follow-up dates from a
single source of truth.

PRODUCTION SAFETY:
  - Only touches rows where Visit.follow_up_date IS NULL and
    ClinicalNote.next_followup_date IS NOT NULL.
  - Does NOT delete or modify ClinicalNote records — the old column is preserved.
  - Always run with --dry-run first to verify the count before committing.

Usage:
    # Step 1 — verify (no DB writes)
    python manage.py migrate_followup_dates --dry-run

    # Step 2 — commit
    python manage.py migrate_followup_dates
"""

from django.core.management.base import BaseCommand
from apps.opd.models import Visit


class Command(BaseCommand):
    help = (
        "Copy ClinicalNote.next_followup_date → Visit.follow_up_date "
        "where Visit.follow_up_date is NULL (production-safe, additive only)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be changed without writing to the database.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be written.'))

        # Query from the Visit side — avoids the OneToOneField reverse-lookup issue.
        # Selects visits that:
        #   - have no follow_up_date set yet (destination is empty)
        #   - have a linked ClinicalNote with a next_followup_date (source has data)
        visits = (
            Visit.objects
            .filter(
                follow_up_date__isnull=True,
                clinical_note__next_followup_date__isnull=False,
            )
            .select_related('clinical_note')
        )

        total = visits.count()
        self.stdout.write(f'Records to migrate: {total}')

        if total == 0:
            self.stdout.write(self.style.SUCCESS('Nothing to do — all follow-up dates are already in sync.'))
            return

        migrated = 0
        errors = 0

        for visit in visits.iterator(chunk_size=500):
            try:
                visit.follow_up_date = visit.clinical_note.next_followup_date
                visit.follow_up_required = True

                if not dry_run:
                    visit.save(update_fields=['follow_up_date', 'follow_up_required'])

                migrated += 1

                if migrated % 100 == 0:
                    self.stdout.write(f'  Processed {migrated}/{total}…')

            except Exception as exc:
                errors += 1
                self.stderr.write(
                    self.style.ERROR(
                        f'  ERROR on Visit id={visit.id}: {exc}'
                    )
                )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\nDRY RUN complete — would have migrated {migrated} records '
                    f'({errors} errors).'
                )
            )
        else:
            if errors:
                self.stdout.write(
                    self.style.WARNING(
                        f'\nMigrated {migrated} records with {errors} errors. '
                        'Check stderr for details.'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nSuccessfully migrated {migrated} follow-up dates.'
                    )
                )
