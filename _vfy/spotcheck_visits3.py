from apps.opd.models import OPDBillItem

item_ids = [1975, 1962, 1963]
for iid in item_ids:
    it = OPDBillItem.objects.get(id=iid)
    print(f"item id={it.id} bill_id={it.bill_id} name={it.item_name} qty={it.quantity} "
          f"unit_price={it.unit_price} total_price={it.total_price} system_calculated_price={it.system_calculated_price}")
