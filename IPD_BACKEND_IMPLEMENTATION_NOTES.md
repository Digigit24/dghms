# IPD Billing - Backend Implementation Notes

## What's Already Done

✅ **Models Updated**:
- `IPDBilling` - Changed from OneToOneField to ForeignKey (allows multiple bills per admission)
- Added all payment fields to match OPD (payment_mode, payment_details, received_amount, etc.)
- Added `_calculate_derived_totals()` method with same logic as OPD
- Updated `save()` method to handle normal updates vs signal-triggered updates
- `IPDBillItem` - Renamed `billing` field to `bill` for consistency with OPD

✅ **Signals Created** (`apps/ipd/signals.py`):
- Auto-recalculate bill totals when items are added/updated/deleted
- Auto-update admission totals when bills are updated (if admission has those fields)

## What Needs to be Done

### 1. Serializers (Copy from OPD)

Create these serializers in `apps/ipd/serializers.py`:

```python
# COPY THESE FROM apps/opd/serializers.py and rename:
# OPDBill → IPDBilling
# OPDBillItem → IPDBillItem
# Visit → Admission

IPDBillListSerializer          # For list view
IPDBillDetailSerializer         # For detail view
IPDBillCreateUpdateSerializer   # For create/update (with validation)
IPDBillItemSerializer          # For bill items
```

**Key Changes Needed:**
1. Replace all `OPDBill` with `IPDBilling`
2. Replace all `OPDBillItem` with `IPDBillItem`
3. Replace `visit` field with `admission`
4. Replace `visit_number` with `admission_number`
5. Replace `doctor` ForeignKey with `doctor_id` UUID field

**Validation:**
- Copy the validation logic from `OPDBillCreateUpdateSerializer.validate()`
- It handles received_amount validation properly

### 2. Views (Copy from OPD)

Create these viewsets in `apps/ipd/views.py`:

```python
# COPY THESE FROM apps/opd/views.py and rename:

class IPDBillingViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    # Copy from OPDBillViewSet
    # Change queryset to IPDBilling
    # Change serializer classes
    # Keep all actions: list, retrieve, create, update, record_payment, statistics

class IPDBillItemViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    # Copy from OPDBillItemViewSet
    # Change queryset to IPDBillItem
    # Simplified - no custom perform_* methods needed (signals handle it)

# For Admission ViewSet (if not exists):
class AdmissionViewSet(...):
    # Add these custom actions (copy from VisitViewSet):

    @action(detail=True, methods=['get'])
    def unbilled_requisitions(self, request, pk=None):
        # Copy from VisitViewSet.unbilled_requisitions
        # Change Visit to Admission
        # Filter requisitions by content_type=Admission

    @action(detail=True, methods=['post'])
    def sync_clinical_charges(self, request, pk=None):
        # Copy from VisitViewSet.sync_clinical_charges
        # Change OPDBill to IPDBilling
        # Change OPDBillItem to IPDBillItem
        # Filter by admission instead of visit
```

### 3. URL Configuration

In `apps/ipd/urls.py`:

```python
from rest_framework.routers import DefaultRouter
from .views import IPDBillingViewSet, IPDBillItemViewSet

router = DefaultRouter()
router.register(r'ipd-bills', IPDBillingViewSet, basename='ipd-bill')
router.register(r'ipd-bill-items', IPDBillItemViewSet, basename='ipd-bill-item')

urlpatterns = router.urls
```

### 4. Admin (Optional)

In `apps/ipd/admin.py`:

```python
from common.admin_site import TenantModelAdmin, hms_admin_site
from .models import IPDBilling, IPDBillItem

class IPDBillItemInline(admin.TabularInline):
    model = IPDBillItem
    extra = 0
    fields = ['item_name', 'source', 'quantity', 'unit_price', 'total_price']
    readonly_fields = ['total_price']

@admin.register(IPDBilling, site=hms_admin_site)
class IPDBillingAdmin(TenantModelAdmin):
    list_display = ['bill_number', 'admission', 'bill_date', 'total_amount', 'payment_status']
    list_filter = ['payment_status', 'bill_date']
    search_fields = ['bill_number', 'admission__admission_id']
    readonly_fields = ['tenant_id', 'total_amount', 'payable_amount', 'balance_amount', 'payment_status']
    inlines = [IPDBillItemInline]
```

## Migration Required

**IMPORTANT:** The model changes require a database migration:

```bash
python manage.py makemigrations ipd
python manage.py migrate ipd
```

**Migration Impact:**
- Changes `admission` from OneToOneField to ForeignKey
- Adds new fields: `discount_percent`, `payable_amount`, `payment_mode`, `payment_details`, `doctor_id`, etc.
- Renames some fields for consistency
- Existing data: If you have existing IPD bills, they will remain linked to their admissions

## Testing Checklist

- [ ] Create new IPD bill
- [ ] Add manual bill items
- [ ] Sync clinical charges from requisitions
- [ ] Record payment (PATCH with received_amount)
- [ ] Verify totals recalculate automatically
- [ ] Verify multiple bills can exist for one admission
- [ ] Check payment status updates correctly (unpaid → partial → paid)
- [ ] Test discount percentage and manual discount amount
- [ ] Verify admission totals update when bills change (if implemented)

## Quick Start (Fastest Way)

1. **Copy OPD files:**
   ```bash
   # Backup first
   cp apps/opd/serializers.py apps/ipd/serializers.py.backup
   cp apps/opd/views.py apps/ipd/views.py.backup
   ```

2. **Search and Replace in copied files:**
   - `OPDBill` → `IPDBilling`
   - `OPDBillItem` → `IPDBillItem`
   - `Visit` → `Admission`
   - `visit` → `admission`
   - `visit_number` → `admission_number`
   - `opd_bills` → `ipd_bills`
   - `opd.OPDBill` → `ipd.IPDBilling`

3. **Make migrations and migrate:**
   ```bash
   python manage.py makemigrations ipd
   python manage.py migrate ipd
   ```

4. **Test the API:**
   ```bash
   # List bills
   curl -H "Authorization: Bearer $TOKEN" http://localhost:8002/api/ipd/ipd-bills/

   # Create bill
   curl -X POST -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"admission": 1, "payment_mode": "cash"}' \
        http://localhost:8002/api/ipd/ipd-bills/
   ```

## Benefits of This Approach

1. **Consistency**: IPD and OPD billing work identically
2. **Reusable Frontend**: Same UI components for both
3. **Auto-calculations**: No manual total calculation needed
4. **Signal-driven**: All updates trigger automatic recalculation
5. **Multiple Bills**: Supports interim bills during long admissions
6. **Payment Tracking**: Complete payment lifecycle (unpaid → partial → paid)
7. **Requisition Integration**: Auto-sync from clinical orders (lab, pharmacy, procedures)

## Encounter Type Integration

Both `Requisition` and `ClinicalNoteTemplateResponse` use `EncounterMixin`:

```python
# They already work with both OPD and IPD:
requisition = Requisition.objects.create(
    content_type=ContentType.objects.get_for_model(Admission),
    object_id=admission.id,
    # ... other fields
)

# Filtering for specific admission:
requisitions = Requisition.objects.filter(
    content_type__model='admission',
    object_id=admission_id
)
```

The `sync_clinical_charges` action uses this to find all unbilled requisitions for an admission!
