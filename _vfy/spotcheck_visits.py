from apps.opd.models import Visit, OPDBill
from apps.payments.models import BillPayment

visit_numbers = [
    "OPD/20260714/001",
    "OPD/20260713/001",
    "OPD/20260709/001",
    "OPD/20260708/001",
]

for vn in visit_numbers:
    print("=" * 80)
    print(f"Visit number: {vn}")
    visits = Visit.objects.filter(visit_number=vn)
    count = visits.count()
    print(f"  matches found: {count}")
    for visit in visits:
        print(f"  visit_id={visit.id} tenant_id={visit.tenant_id}")
        print(
            f"  CURRENT Visit fields: total_amount={visit.total_amount} "
            f"paid_amount={getattr(visit, 'paid_amount', None)} "
            f"balance_amount={getattr(visit, 'balance_amount', None)} "
            f"payment_status={visit.payment_status}"
        )
        bills = OPDBill.objects.filter(visit=visit)
        if not bills.exists():
            print("  No OPDBill rows linked to this visit.")
        for bill in bills:
            print(
                f"  OPDBill id={bill.id} bill_number={bill.bill_number} "
                f"total_amount={bill.total_amount} received_amount={getattr(bill, 'received_amount', None)} "
                f"payment_status={getattr(bill, 'payment_status', None)}"
            )
            payments = BillPayment.objects.filter(opd_bill=bill)
            if not payments.exists():
                print("    No BillPayment ledger rows for this bill.")
            for p in payments:
                print(
                    f"    BillPayment id={p.id} amount={p.amount} mode={p.payment_mode} "
                    f"date={p.payment_date} created_at={p.created_at}"
                )
