from contextlib import nullcontext
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce


ZERO = Decimal("0.00")


class Command(BaseCommand):
    help = (
        "Report or repair OPDBill monetary-field drift from OPDBillItem rows "
        "and the BillPayment ledger. Dry-run is the default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            default=None,
            help="Limit the report to a single tenant UUID.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write corrected bill and Visit monetary fields.",
        )
        parser.add_argument(
            "--summary-only",
            action="store_true",
            default=False,
            help="Only print aggregate mismatch counts.",
        )

    @staticmethod
    def _expected_values(bill):
        total = bill.items_total or ZERO
        received = bill.ledger_received or ZERO

        if bill.discount_percent > ZERO:
            discount = (
                total * bill.discount_percent / Decimal("100.00")
            ).quantize(Decimal("0.01"))
        else:
            # Preserve the existing supported fixed-discount behavior.
            discount = bill.discount_amount or ZERO

        payable = total - discount
        if received >= payable:
            balance = ZERO
            payment_status = "paid"
        elif received > ZERO:
            balance = payable - received
            payment_status = "partial"
        else:
            balance = payable
            payment_status = "unpaid"

        return {
            "total_amount": total,
            "discount_amount": discount,
            "payable_amount": payable,
            "received_amount": received,
            "balance_amount": balance,
            "payment_status": payment_status,
        }

    def handle(self, *args, **options):
        from apps.opd.models import OPDBill
        from apps.opd.models import OPDBillItem
        from apps.payments.models import BillPayment

        tenant_id = options.get("tenant_id")
        apply = options["apply"]
        summary_only = options["summary_only"]
        money_field = DecimalField(max_digits=12, decimal_places=2)

        item_totals = (
            OPDBillItem.objects.filter(bill_id=OuterRef("pk"))
            .values("bill_id")
            .annotate(total=Sum("total_price"))
            .values("total")[:1]
        )
        payment_totals = (
            BillPayment.objects.filter(
                tenant_id=OuterRef("tenant_id"),
                opd_bill_id=OuterRef("pk"),
            )
            .values("opd_bill_id")
            .annotate(total=Sum("amount"))
            .values("total")[:1]
        )
        bills = OPDBill.objects.select_related("visit").annotate(
            items_total=Coalesce(
                Subquery(item_totals, output_field=money_field),
                Value(ZERO, output_field=money_field),
            ),
            ledger_received=Coalesce(
                Subquery(payment_totals, output_field=money_field),
                Value(ZERO, output_field=money_field),
            ),
        ).order_by("id")
        if tenant_id:
            bills = bills.filter(tenant_id=tenant_id)

        checked = mismatched = updated = 0
        item_total_mismatches = 0
        nonzero_item_total_mismatches = 0
        ledger_received_mismatches = 0
        stored_total_without_items = 0
        affected_visit_ids = set()
        mismatch_by_status = {}

        if not apply:
            self.stdout.write(self.style.WARNING(
                "DRY RUN - no OPDBill or Visit rows will be updated.\n"
            ))

        write_context = transaction.atomic() if apply else nullcontext()
        with write_context:
            # Avoid server-side named cursors: the deployed PostgreSQL pooler
            # can invalidate them between fetches (InvalidCursorName).
            for bill in bills:
                checked += 1
                expected = self._expected_values(bill)
                changed_fields = [
                    field
                    for field, value in expected.items()
                    if getattr(bill, field) != value
                ]
                if not changed_fields:
                    continue

                mismatched += 1
                if "total_amount" in changed_fields:
                    item_total_mismatches += 1
                    if expected["total_amount"] > ZERO:
                        nonzero_item_total_mismatches += 1
                    elif bill.total_amount > ZERO:
                        stored_total_without_items += 1
                if "received_amount" in changed_fields:
                    ledger_received_mismatches += 1

                transition = f"{bill.payment_status}->{expected['payment_status']}"
                mismatch_by_status[transition] = mismatch_by_status.get(transition, 0) + 1
                if not summary_only:
                    stored = ", ".join(
                        f"{field}={getattr(bill, field)}" for field in expected
                    )
                    computed = ", ".join(
                        f"{field}={value}" for field, value in expected.items()
                    )
                    self.stdout.write(
                        f"bill_id={bill.id} bill_number={bill.bill_number} "
                        f"tenant_id={bill.tenant_id} changed={','.join(changed_fields)} "
                        f"stored({stored}) expected({computed})"
                    )

                if apply:
                    # QuerySet.update avoids payment/transaction side effects while
                    # repairing historical aggregates. Visits are recomputed below.
                    OPDBill.objects.filter(pk=bill.pk).update(**expected)
                    if bill.visit_id:
                        affected_visit_ids.add(bill.visit_id)
                    updated += 1

            if apply and affected_visit_ids:
                from apps.opd.models import Visit

                for visit in Visit.objects.filter(id__in=affected_visit_ids):
                    aggregates = OPDBill.objects.filter(visit=visit).aggregate(
                        total=Coalesce(
                            Sum("total_amount"),
                            Value(ZERO, output_field=money_field),
                        ),
                        paid=Coalesce(
                            Sum("received_amount"),
                            Value(ZERO, output_field=money_field),
                        ),
                    )
                    visit.total_amount = aggregates["total"]
                    visit.paid_amount = aggregates["paid"]
                    visit.update_payment_status()

        self.stdout.write("")
        self.stdout.write(f"Checked bills: {checked}")
        self.stdout.write(f"Mismatched bills: {mismatched}")
        self.stdout.write(f"Item-total mismatches: {item_total_mismatches}")
        self.stdout.write(
            "Nonzero line-items with wrong stored total: "
            f"{nonzero_item_total_mismatches}"
        )
        self.stdout.write(
            f"Stored totals with no line items: {stored_total_without_items}"
        )
        self.stdout.write(
            f"Ledger received-amount mismatches: {ledger_received_mismatches}"
        )
        if mismatch_by_status:
            self.stdout.write("Transitions:")
            for transition, count in sorted(mismatch_by_status.items()):
                self.stdout.write(f"  {transition}: {count}")
        if apply:
            self.stdout.write(self.style.SUCCESS(f"Updated bills: {updated}"))
            self.stdout.write(self.style.SUCCESS(
                f"Recomputed visits: {len(affected_visit_ids)}"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "DRY RUN complete - no rows updated."
            ))
