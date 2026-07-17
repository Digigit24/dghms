from apps.opd.models import Visit, OPDBill, OPDBillItem

bill_ids = [1235, 1232, 1231, 1230]
for bid in bill_ids:
    bill = OPDBill.objects.get(id=bid)
    print("=" * 60)
    print(f"Bill id={bid} bill_number={bill.bill_number} total_amount={bill.total_amount} "
          f"received_amount={getattr(bill,'received_amount',None)} payment_status={bill.payment_status} "
          f"created_at={bill.bill_date}")
    items = OPDBillItem.objects.filter(bill=bill)
    print(f"  item count: {items.count()}")
    for it in items:
        print(f"    item id={it.id} name={it.item_name} qty={it.quantity} "
              f"total={getattr(it,'total_amount', getattr(it,'amount', None))}")
