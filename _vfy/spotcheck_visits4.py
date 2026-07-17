from apps.opd.models import OPDBill
from django.db.models import Count

qs = OPDBill.objects.filter(tenant_id="615da126-a7d8-4112-a5ae-45bca4c623b6")
print("Total OPDBill rows for tenant:", qs.count())
zero_total = qs.filter(total_amount=0)
print("OPDBill rows with total_amount=0:", zero_total.count())
nonzero_total = qs.exclude(total_amount=0)
print("OPDBill rows with total_amount != 0:", nonzero_total.count())

# among zero-total bills, how many have items with nonzero total_price?
from apps.opd.models import OPDBillItem
zero_ids = list(zero_total.values_list("id", flat=True))
items_for_zero = OPDBillItem.objects.filter(bill_id__in=zero_ids).exclude(total_price=0)
print("zero-total bills that actually have nonzero line items:", items_for_zero.values("bill_id").distinct().count())

# date range of zero-total bills
print("Zero-total bill date range:", zero_total.order_by("bill_date").first().bill_date if zero_total.exists() else None,
      "to", zero_total.order_by("-bill_date").first().bill_date if zero_total.exists() else None)
print("Nonzero-total bill date range:", nonzero_total.order_by("bill_date").first().bill_date if nonzero_total.exists() else None,
      "to", nonzero_total.order_by("-bill_date").first().bill_date if nonzero_total.exists() else None)
