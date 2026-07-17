from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce


class Command(BaseCommand):
    help = "Report or repair Visit payment_status drift from OPDBill aggregates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            default=None,
            help="Limit report to a single tenant UUID.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write corrected Visit total_amount/paid_amount/balance_amount/payment_status.",
        )
        parser.add_argument(
            "--summary-only",
            action="store_true",
            default=False,
            help="Only print aggregate mismatch counts.",
        )

    def handle(self, *args, **options):
        tenant_id = options.get("tenant_id")
        apply = options["apply"]
        summary_only = options["summary_only"]

        from apps.opd.models import Visit

        money_field = DecimalField(max_digits=12, decimal_places=2)
        visits = Visit.objects.annotate(
            expected_total=Coalesce(
                Sum("opd_bills__total_amount"),
                Value(Decimal("0.00"), output_field=money_field),
            ),
            expected_paid=Coalesce(
                Sum("opd_bills__received_amount"),
                Value(Decimal("0.00"), output_field=money_field),
            ),
        ).order_by("id")
        if tenant_id:
            visits = visits.filter(tenant_id=tenant_id)

        checked = mismatched = updated = 0
        mismatch_by_status = {}

        if not apply:
            self.stdout.write(self.style.WARNING("DRY RUN - no Visit rows will be updated.\n"))

        for visit in visits.iterator(chunk_size=500):
            checked += 1
            expected_total = visit.expected_total or Decimal("0.00")
            expected_paid = visit.expected_paid or Decimal("0.00")
            if expected_paid >= expected_total:
                expected_status = "paid"
                expected_balance = Decimal("0.00")
            elif expected_paid > Decimal("0.00"):
                expected_status = "partial"
                expected_balance = expected_total - expected_paid
            else:
                expected_status = "unpaid"
                expected_balance = expected_total

            is_wrong = (
                visit.total_amount != expected_total
                or visit.paid_amount != expected_paid
                or visit.balance_amount != expected_balance
                or visit.payment_status != expected_status
            )
            if not is_wrong:
                continue

            mismatched += 1
            key = f"{visit.payment_status}->{expected_status}"
            mismatch_by_status[key] = mismatch_by_status.get(key, 0) + 1
            if not summary_only:
                self.stdout.write(
                    f"visit_id={visit.id} visit_number={visit.visit_number} "
                    f"stored(total={visit.total_amount}, paid={visit.paid_amount}, "
                    f"balance={visit.balance_amount}, status={visit.payment_status}) "
                    f"expected(total={expected_total}, paid={expected_paid}, "
                    f"balance={expected_balance}, status={expected_status})"
                )

            if apply:
                visit.total_amount = expected_total
                visit.paid_amount = expected_paid
                visit.balance_amount = expected_balance
                visit.payment_status = expected_status
                visit.save(
                    update_fields=[
                        "total_amount",
                        "paid_amount",
                        "balance_amount",
                        "payment_status",
                        "updated_at",
                    ]
                )
                updated += 1

        self.stdout.write("")
        self.stdout.write(f"Checked visits: {checked}")
        self.stdout.write(f"Mismatched visits: {mismatched}")
        if mismatch_by_status:
            self.stdout.write("Transitions:")
            for transition, count in sorted(mismatch_by_status.items()):
                self.stdout.write(f"  {transition}: {count}")
        if apply:
            self.stdout.write(self.style.SUCCESS(f"Updated visits: {updated}"))
        else:
            self.stdout.write(self.style.WARNING("DRY RUN complete - no rows updated."))
