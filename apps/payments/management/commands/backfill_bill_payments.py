"""
Management command: backfill_bill_payments
==========================================

Backfills the bill_payments ledger table from historical OPD and IPD billing
records.

Since OPD/IPD models store only a *cumulative* received_amount (not individual
payment events), this command creates ONE BillPayment entry per bill that has
received_amount > 0.  The entry captures the full received amount and uses the
bill's updated_at as the payment date (best proxy for when payment occurred).

Running this command twice is safe — it skips bills that already have a ledger
entry (idempotent via update_or_create keyed on opd_bill / ipd_bill).

Usage:
    python manage.py backfill_bill_payments
    python manage.py backfill_bill_payments --dry-run
    python manage.py backfill_bill_payments --tenant-id <uuid>
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Backfill BillPayment ledger from existing OPD and IPD billing records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be created without writing to the database.",
        )
        parser.add_argument(
            "--tenant-id",
            type=str,
            default=None,
            help="Limit backfill to a single tenant UUID.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        tenant_id_filter = options.get("tenant_id")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will be written.\n"))

        opd_created, opd_skipped = self._backfill_opd(dry_run, tenant_id_filter)
        ipd_created, ipd_skipped = self._backfill_ipd(dry_run, tenant_id_filter)

        total_created = opd_created + ipd_created
        total_skipped = opd_skipped + ipd_skipped

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'[DRY RUN] Would create' if dry_run else 'Created'} "
                f"{total_created} BillPayment records "
                f"({opd_created} OPD, {ipd_created} IPD). "
                f"Skipped {total_skipped} already-present."
            )
        )

    # ──────────────────────────────────────────────────────────────────────────
    # OPD
    # ──────────────────────────────────────────────────────────────────────────

    def _backfill_opd(self, dry_run: bool, tenant_id_filter):
        from apps.opd.models import OPDBill
        from apps.payments.models import BillPayment

        qs = OPDBill.objects.filter(
            received_amount__gt=Decimal("0.00")
        ).select_related("visit__patient").order_by("id")

        if tenant_id_filter:
            qs = qs.filter(tenant_id=tenant_id_filter)

        created = skipped = 0

        for bill in qs.iterator(chunk_size=500):
            # Already has a ledger entry?
            if BillPayment.objects.filter(opd_bill=bill).exists():
                skipped += 1
                continue

            patient_name = ""
            encounter_number = ""
            try:
                if bill.visit and bill.visit.patient:
                    patient_name = bill.visit.patient.full_name or ""
                if bill.visit:
                    encounter_number = bill.visit.visit_number or ""
            except Exception:
                pass

            payment_date = (bill.updated_at.date() if bill.updated_at else
                            bill.bill_date.date() if bill.bill_date else
                            None)

            # Map OPD mode → BillPayment choices (they overlap except 'multiple')
            mode = (bill.payment_mode or "cash").lower()
            if mode not in ("cash", "card", "upi", "bank", "insurance",
                            "cheque", "razorpay", "multiple", "other"):
                mode = "other"

            if dry_run:
                self.stdout.write(
                    f"  [OPD] bill_id={bill.id} bill_number={bill.bill_number} "
                    f"patient={patient_name!r} amount={bill.received_amount} "
                    f"mode={mode} date={payment_date}"
                )
                created += 1
                continue

            try:
                with transaction.atomic():
                    BillPayment.objects.create(
                        tenant_id=bill.tenant_id,
                        bill_type="opd",
                        opd_bill=bill,
                        bill_number=bill.bill_number or str(bill.id),
                        patient_name=patient_name,
                        encounter_number=encounter_number,
                        amount=bill.received_amount,
                        payment_mode=mode,
                        payment_date=payment_date or bill.bill_date.date(),
                        notes="[Backfilled from historical OPD billing]",
                    )
                    created += 1
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"  OPD bill {bill.id} failed: {exc}")
                )

        self.stdout.write(f"OPD: {created} created, {skipped} skipped.")
        return created, skipped

    # ──────────────────────────────────────────────────────────────────────────
    # IPD
    # ──────────────────────────────────────────────────────────────────────────

    def _backfill_ipd(self, dry_run: bool, tenant_id_filter):
        from apps.ipd.models import IPDBilling
        from apps.payments.models import BillPayment

        qs = IPDBilling.objects.filter(
            received_amount__gt=Decimal("0.00")
        ).select_related("admission__patient").order_by("id")

        if tenant_id_filter:
            qs = qs.filter(tenant_id=tenant_id_filter)

        created = skipped = 0

        for billing in qs.iterator(chunk_size=500):
            if BillPayment.objects.filter(ipd_bill=billing).exists():
                skipped += 1
                continue

            patient_name = ""
            encounter_number = ""
            try:
                if billing.admission and billing.admission.patient:
                    patient_name = billing.admission.patient.full_name or ""
                if billing.admission:
                    encounter_number = billing.admission.admission_id or ""
            except Exception:
                pass

            payment_date = (billing.updated_at.date() if billing.updated_at else
                            billing.bill_date.date() if billing.bill_date else
                            None)

            mode = (billing.payment_mode or "cash").lower()
            if mode not in ("cash", "card", "upi", "bank", "insurance",
                            "cheque", "razorpay", "multiple", "other"):
                # IPD has 'netbanking' — map to 'bank'
                if mode == "netbanking":
                    mode = "bank"
                else:
                    mode = "other"

            if dry_run:
                self.stdout.write(
                    f"  [IPD] bill_id={billing.id} bill_number={billing.bill_number} "
                    f"patient={patient_name!r} amount={billing.received_amount} "
                    f"mode={mode} date={payment_date}"
                )
                created += 1
                continue

            try:
                with transaction.atomic():
                    BillPayment.objects.create(
                        tenant_id=billing.tenant_id,
                        bill_type="ipd",
                        ipd_bill=billing,
                        bill_number=billing.bill_number or str(billing.id),
                        patient_name=patient_name,
                        encounter_number=encounter_number,
                        amount=billing.received_amount,
                        payment_mode=mode,
                        payment_date=payment_date or billing.bill_date.date(),
                        notes="[Backfilled from historical IPD billing]",
                    )
                    created += 1
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"  IPD billing {billing.id} failed: {exc}")
                )

        self.stdout.write(f"IPD: {created} created, {skipped} skipped.")
        return created, skipped
