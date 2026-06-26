# IPD Module — Complete Improvement Plan
**Project:** DigiHMS  
**Backend:** Django 5.2 + DRF (`apps/ipd/`)  
**Frontend:** React + SWR (`src/pages/ipd/`, `src/components/ipd/`)  
**Audit Date:** 2026-06-26  
**Constraint:** Production is live. No production data must be lost. All migrations must be additive or safe.

---

## AUDIT FINDINGS SUMMARY

### Critical Bugs (Breaking right now)
1. **Wrong client-side stats from paginated data** — `Admissions.tsx` computes `activeAdmissions`, `dischargedToday`, and `avgLengthOfStay` using `.filter()` on the current page's results only. A hospital with 3 pages of admissions will show "Active: 3" when there are actually 30.
2. **Double-filtering in `Admissions.tsx`** — Status filter and date range are sent to the backend AND re-applied client-side via `useMemo`. If the user changes filter, the UI filters what's already filtered server-side, causing logical errors and confusing empty states.
3. **No `search_fields` on `AdmissionViewSet`** — Frontend sends `?search=John` but backend ignores it silently (no error, just returns all records unfiltered).

### Backend Performance Issues
4. **N+1 queries on Ward list** — `WardSerializer` calls `get_available_beds_count()` and `get_occupied_beds_count()` as Python methods, each triggering a separate DB query per row. 20 wards = 40 extra queries per page load.
5. **`length_of_stay` computed in Python** — `Admission.calculate_length_of_stay()` is called per row in Python, not computed at the DB level. Cannot be used for `ORDER BY` or `AVG()` aggregation in SQL.
6. **No `statistics` endpoint on `AdmissionViewSet`** — Frontend cannot get correct total counts, active counts, or averages without fetching all pages.
7. **No `statistics` endpoint on `IPDBillingViewSet`** — Revenue totals, outstanding amounts, and payment breakdowns are not available to the frontend without loading all billing records.
8. **`BedViewSet` missing `select_related('ward')`** — Every time a bed is serialized with ward information, an extra query is fired per bed. On a 50-bed ward list page, this is 50 extra queries.

### Frontend Architecture Issues
9. **Duplicate billing service** — `src/services/ipd.service.ts` contains billing methods (`getBillings`, `createBilling`, `getBillItems`, `updateBilling`, etc.) AND `src/services/ipdBilling.service.ts` is a separate service hitting the same backend endpoints. `IPDBillingContent.tsx` uses `ipdBillingService`, while the `useIPD` hook uses `ipdService`. This creates inconsistent cache, duplicate HTTP calls, and confusing maintenance.
10. **No optimistic UI on any IPD mutation** — Discharge, bed assignment, billing item add, note creation — all wait for server round-trip before updating UI.
11. **`IPDConsultationTab.tsx` fetches template detail separately** — After loading a template response, a second call fires for the template's field definitions. Two HTTP calls where one should suffice (once backend prefetches are fixed per OPD plan Task 1.4).
12. **`useWards` and `useAdmissions` hooks lack `keepPreviousData: true`** — Every page change or filter change shows a blank list while the new page loads.
13. **`Admissions.tsx` stat cards block on list data** — Stats (header cards showing active count etc.) are rendered only after the admission list loads. Stats should load independently and immediately.
14. **No `search_fields` exposed in frontend search box for IPD** — Since backend silently ignores `?search=`, the search box appears to work (no error) but returns wrong data (all records).

---

## IMPLEMENTATION PLAN

> **RULE:** Work in phases. Each phase is independently deployable. Never break previous phases. All migrations are additive (`reverse_code=RunPython.noop` for safety).

---

## PHASE 0 — CRITICAL BUG FIXES (Deploy First, No Migrations)

These are backend + frontend code changes only. Safe to deploy immediately.

---

### TASK 0.1 — Add `search_fields` to `AdmissionViewSet`
**File:** `apps/ipd/views.py`, class `AdmissionViewSet`

**Problem:** `AdmissionViewSet` has `filterset_fields` but no `search_fields`. Frontend search box sends `?search=X` — backend ignores it silently.

**Fix:**
```python
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend

class AdmissionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'ward', 'doctor_id', 'patient']
    search_fields = [
        'admission_id',
        'patient__first_name',
        'patient__last_name',
        'patient__mobile_primary',
        'provisional_diagnosis',
    ]
    ordering_fields = ['admission_date', 'created_at', 'status']
    ordering = ['-admission_date']
```

**Also verify** `AdmissionViewSet.get_queryset()` uses `select_related('patient', 'ward', 'bed', 'doctor')` so the `patient__first_name` search doesn't trigger a separate query per row.

---

### TASK 0.2 — Add `search_fields` to `WardViewSet`
**File:** `apps/ipd/views.py`, class `WardViewSet`

**Problem:** Ward list has no search. Users can't find a ward by name.

**Fix:**
```python
class WardViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['ward_type', 'is_active']
    search_fields = ['name', 'ward_number', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
```

---

### TASK 0.3 — Fix frontend search in `Admissions.tsx`
**File:** `src/pages/ipd/Admissions.tsx`

**Problem:** The frontend search box likely sends `?search=X` to `useAdmissions()` but results appear unchanged because backend ignored it (before Task 0.1).

**Verify:** After Task 0.1 backend deploy, test that the search box filters results. If the frontend is sending the param correctly, it will start working automatically. If not, find the search input handler and ensure it's passed as `search` param:
```js
const { data } = useAdmissions({
  search: searchQuery,   // ensure this key is 'search' not 'query' or 'q'
  status: statusFilter,
  page: currentPage,
});
```

---

### TASK 0.4 — Remove client-side double-filtering from `Admissions.tsx`
**File:** `src/pages/ipd/Admissions.tsx`, lines ~67–90

**Problem:** Status filter and date range are passed to backend AND re-applied via `useMemo`. Client-side filtering of already-filtered server data is logically wrong and causes empty states when switching pages.

**Fix:** Delete the entire `useMemo` filter block. Trust the backend response:
```js
// REMOVE this block entirely:
const admissions = useMemo(() => {
  return rawAdmissions.filter((admission) => {
    if (statusFilter && admission.status !== statusFilter) return false;
    if (dateFrom && new Date(admission.admission_date) < new Date(dateFrom)) return false;
    if (dateTo && new Date(admission.admission_date) > new Date(dateTo)) return false;
    return true;
  });
}, [rawAdmissions, statusFilter, dateFrom, dateTo]);

// REPLACE with:
const admissions = rawAdmissions; // backend already applied filters
```

Add date range filter support to backend (see Phase 1 Task 1.3).

---

## PHASE 1 — BACKEND QUERY OPTIMIZATION

No model changes. No migrations. Only `views.py`, `serializers.py` changes.

---

### TASK 1.1 — Fix N+1 on Ward list using DB annotations
**File:** `apps/ipd/views.py`, class `WardViewSet`  
**File:** `apps/ipd/serializers.py`, class `WardSerializer`

**Problem:** `WardSerializer` includes:
```python
available_beds_count = serializers.ReadOnlyField(source='get_available_beds_count')
occupied_beds_count = serializers.ReadOnlyField(source='get_occupied_beds_count')
```
Both are Python method calls that each run a DB query per ward. 20 wards = 40 extra queries.

**Fix in `views.py`:**
```python
from django.db.models import Count, Q

class WardViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    def get_queryset(self):
        return Ward.objects.filter(
            tenant_id=self.request.tenant_id
        ).annotate(
            available_beds_count=Count(
                'beds', filter=Q(beds__is_occupied=False, beds__is_active=True)
            ),
            occupied_beds_count=Count(
                'beds', filter=Q(beds__is_occupied=True)
            ),
            total_beds_count=Count('beds', filter=Q(beds__is_active=True)),
        ).order_by('name')
```

**Fix in `serializers.py`:**
```python
class WardSerializer(TenantMixin, serializers.ModelSerializer):
    available_beds_count = serializers.IntegerField(read_only=True)  # from annotation
    occupied_beds_count = serializers.IntegerField(read_only=True)   # from annotation
    total_beds_count = serializers.IntegerField(read_only=True)      # from annotation
    
    # Remove source='get_available_beds_count' — annotation provides value directly
```

**Keep** the Python methods on the `Ward` model. Don't delete them — they may be used in admin or management commands. Just stop calling them from serializers.

**Result:** 20-ward list goes from 42 queries to 1 query. Significant speedup.

---

### TASK 1.2 — Fix N+1 on Bed list using `select_related`
**File:** `apps/ipd/views.py`, class `BedViewSet`

**Problem:** Each bed includes ward info but there's no `select_related` — every bed serialization triggers a separate query for its ward.

**Fix:**
```python
class BedViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    def get_queryset(self):
        return Bed.objects.filter(
            tenant_id=self.request.tenant_id
        ).select_related('ward')
```

---

### TASK 1.3 — Add date range filter to `AdmissionViewSet`
**File:** `apps/ipd/views.py` or `apps/ipd/filters.py` (create if not exists)

**Problem:** Frontend sends date range params but backend has no date-range filter support. Admissions can only be filtered by status, ward, doctor_id, and patient.

**Fix — Create a custom FilterSet:**
```python
# apps/ipd/filters.py
import django_filters
from .models import Admission

class AdmissionFilter(django_filters.FilterSet):
    admission_date__gte = django_filters.DateFilter(
        field_name='admission_date', lookup_expr='date__gte',
        label='Admitted on or after'
    )
    admission_date__lte = django_filters.DateFilter(
        field_name='admission_date', lookup_expr='date__lte',
        label='Admitted on or before'
    )
    discharge_date__gte = django_filters.DateFilter(
        field_name='discharge_date', lookup_expr='date__gte'
    )
    discharge_date__lte = django_filters.DateFilter(
        field_name='discharge_date', lookup_expr='date__lte'
    )

    class Meta:
        model = Admission
        fields = ['status', 'ward', 'doctor_id', 'patient']
```

**In `views.py`:**
```python
from .filters import AdmissionFilter

class AdmissionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    filterset_class = AdmissionFilter  # replaces filterset_fields
```

---

### TASK 1.4 — Add `statistics` action to `AdmissionViewSet`
**File:** `apps/ipd/views.py`, class `AdmissionViewSet`

**Problem:** Frontend `Admissions.tsx` computes header card stats (`activeAdmissions`, `dischargedToday`, `avgLengthOfStay`) from the current page only. These numbers are wrong for paginated data.

**Fix — Add a `statistics` action:**
```python
from django.db.models import Count, Avg, Sum, Q
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
import datetime

@action(detail=False, methods=['get'])
def statistics(self, request):
    """
    Returns aggregate statistics for admissions in this tenant.
    Respects the same filters as the list endpoint (pass ?status=, ?ward=, etc.)
    """
    qs = self.filter_queryset(self.get_queryset())
    today = datetime.date.today()

    agg = qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='admitted')),
        discharged_today=Count(
            'id',
            filter=Q(status='discharged', discharge_date__date=today)
        ),
        critical=Count('id', filter=Q(status='critical')),
        pending_discharge=Count('id', filter=Q(status='pending_discharge')),
    )

    # Average length of stay for discharged patients
    avg_result = qs.filter(
        status='discharged',
        discharge_date__isnull=False,
        admission_date__isnull=False,
    ).annotate(
        stay_days=ExpressionWrapper(
            F('discharge_date__date') - F('admission_date__date'),
            output_field=DurationField()
        )
    ).aggregate(avg_stay=Avg('stay_days'))
    
    avg_stay = None
    if avg_result['avg_stay']:
        avg_stay = avg_result['avg_stay'].days

    return Response({
        'success': True,
        'data': {
            **agg,
            'avg_length_of_stay_days': avg_stay,
        }
    })
```

Add to `urls.py` — DRF router auto-registers `@action` methods; no URL change needed.

---

### TASK 1.5 — Add `statistics` action to `IPDBillingViewSet`
**File:** `apps/ipd/views.py`, class `IPDBillingViewSet`

**Problem:** Frontend billing pages compute revenue totals from paginated data. Same problem as admissions stats.

**Fix:**
```python
@action(detail=False, methods=['get'])
def statistics(self, request):
    from django.db.models import Count, Sum, Q
    
    qs = self.filter_queryset(self.get_queryset())
    
    agg = qs.aggregate(
        total_bills=Count('id'),
        total_amount=Sum('total_amount'),
        paid_amount=Sum('paid_amount', filter=Q(payment_status='paid')),
        pending_amount=Sum('balance_amount', filter=Q(payment_status__in=['pending', 'partial'])),
        cancelled_amount=Sum('total_amount', filter=Q(payment_status='cancelled')),
    )
    
    return Response({'success': True, 'data': agg})
```

---

### TASK 1.6 — Optimize `AdmissionViewSet.get_queryset()` with `select_related` and `prefetch_related`
**File:** `apps/ipd/views.py`, class `AdmissionViewSet`

**Problem:** List view serializer accesses `patient.full_name`, `ward.name`, `bed.bed_number` etc. — each one fires a separate query per row without `select_related`.

**Fix:**
```python
def get_queryset(self):
    return Admission.objects.filter(
        tenant_id=self.request.tenant_id
    ).select_related(
        'patient',
        'ward',
        'bed',
    )
    # Note: doctor is stored as doctor_id (UUID), not a ForeignKey — no select_related needed
```

Add appropriate DB indexes if not present:
```python
class Meta:
    indexes = [
        models.Index(fields=['tenant_id', 'status']),
        models.Index(fields=['tenant_id', 'admission_date']),
        models.Index(fields=['tenant_id', '-created_at']),
        models.Index(fields=['patient', 'status']),  # for patient portal
    ]
```

---

### TASK 1.7 — Move `length_of_stay` computation to DB annotation
**File:** `apps/ipd/views.py`, class `AdmissionViewSet`  
**File:** `apps/ipd/serializers.py`, class `AdmissionListSerializer`

**Problem:** `Admission.calculate_length_of_stay()` is a Python method. It can't be used in SQL `ORDER BY length_of_stay` or averaged via `Avg('length_of_stay')`.

**Fix in `get_queryset` annotation:**
```python
from django.db.models import ExpressionWrapper, F, DurationField, IntegerField
from django.db.models.functions import Coalesce
from django.utils import timezone

def get_queryset(self):
    today = timezone.now().date()
    return Admission.objects.filter(
        tenant_id=self.request.tenant_id
    ).select_related('patient', 'ward', 'bed').annotate(
        los_days=ExpressionWrapper(
            Coalesce(F('discharge_date__date'), today) - F('admission_date__date'),
            output_field=IntegerField()
        )
    )
```

**Fix in `serializers.py`:**
```python
class AdmissionListSerializer(TenantMixin, serializers.ModelSerializer):
    los_days = serializers.IntegerField(read_only=True)  # from annotation
    # Remove: length_of_stay = serializers.SerializerMethodField()
    # Remove: get_length_of_stay method
```

**Add `ordering_fields` to viewset:**
```python
ordering_fields = ['admission_date', 'created_at', 'status', 'los_days']
```

Now frontend can `?ordering=-los_days` to sort by length of stay.

---

### TASK 1.8 — Add `has_active_ipd_admission` to `VisitDetailSerializer` (OPD side fix)
**File:** `apps/opd/serializers.py`, class `VisitDetailSerializer`

**Problem:** `ConsultationTab.tsx` (OPD consultation page) calls `GET /ipd/admissions/?patient=X` just to check if the OPD patient is currently admitted in IPD. This fires an IPD query every time any OPD consultation is opened.

**Fix:** Add as computed field in `VisitDetailSerializer`:
```python
has_active_ipd_admission = serializers.SerializerMethodField()

def get_has_active_ipd_admission(self, obj):
    from apps.ipd.models import Admission
    return Admission.objects.filter(
        patient=obj.patient,
        tenant_id=obj.tenant_id,
        status='admitted'
    ).exists()
```

This moves the IPD check into a single SQL `EXISTS` query embedded in the visit detail response, and eliminates one HTTP round-trip from the OPD consultation tab.

---

## PHASE 2 — DUPLICATE BILLING SERVICE CONSOLIDATION

No model changes. No migrations. Frontend service layer refactor only.

---

### TASK 2.1 — Audit which billing methods exist in both services
**Files:** `src/services/ipd.service.ts`, `src/services/ipdBilling.service.ts`

**Action:** Open both files and list all method names side-by-side. Methods that appear in both (hitting same endpoints) are duplicates. Expected duplicates based on audit:
- `getBillings` / `listBillings`
- `getBilling` / `getBillingById`
- `createBilling` / `createIPDBilling`
- `getBillItems` / `getBillingItems`
- `addBillItem` / `addBillingItem`
- `updateBilling` / `updateIPDBilling`

---

### TASK 2.2 — Make `ipdBilling.service.ts` the single source of truth for billing
**Files:** `src/services/ipd.service.ts`, `src/services/ipdBilling.service.ts`

**Decision:** Keep `ipdBilling.service.ts` as the canonical billing service. Remove billing methods from `ipd.service.ts`.

**Steps:**
1. In `ipd.service.ts`, delete all billing-related methods. Leave only non-billing IPD methods (admissions, wards, beds, clinical notes, etc.)
2. Ensure `ipdBilling.service.ts` has ALL methods that were in both files (merge any that exist only in `ipd.service.ts`)
3. Search codebase for any imports of billing methods from `ipd.service.ts` and update them to import from `ipdBilling.service.ts`

**Files to search for imports:**
```
grep -r "ipdService.getBilling\|ipdService.createBilling\|ipdService.getBillItems\|ipdService.addBillItem" src/
```

---

### TASK 2.3 — Create `useIPDBilling` SWR hook
**File:** `src/hooks/useIPD.ts` or new file `src/hooks/useIPDBilling.ts`

**Problem:** `useIPD.ts` has billing hooks mixed with admission/ward hooks, but they call different service files. After Task 2.2, the billing hooks should call `ipdBillingService`.

**Create dedicated billing hooks:**
```ts
// src/hooks/useIPDBilling.ts
import useSWR from 'swr';
import { ipdBillingService } from '../services/ipdBilling.service';

export function useIPDBillings(params?: BillingQueryParams) {
  const key = params ? `ipd-billings-${JSON.stringify(params)}` : 'ipd-billings';
  return useSWR(key, () => ipdBillingService.getBillings(params), {
    revalidateOnFocus: false,
    keepPreviousData: true,
  });
}

export function useIPDBillingStatistics(params?: BillingQueryParams) {
  const key = params ? `ipd-billing-stats-${JSON.stringify(params)}` : 'ipd-billing-stats';
  return useSWR(key, () => ipdBillingService.getStatistics(params), {
    revalidateOnFocus: false,
  });
}

export function useIPDBilling(id?: number) {
  return useSWR(id ? `ipd-billing-${id}` : null, () => ipdBillingService.getBilling(id!), {
    revalidateOnFocus: false,
  });
}
```

---

## PHASE 3 — FRONTEND STATS & PAGINATION FIX

---

### TASK 3.1 — Fix `Admissions.tsx` to use backend statistics endpoint
**File:** `src/pages/ipd/Admissions.tsx`

**After Task 1.4** (backend statistics endpoint is deployed):

**Before:**
```js
// Wrong — computes from current page only
const activeAdmissions = admissions.filter(a => a.status === 'admitted').length;
const dischargedToday = admissions.filter(a => {
  const today = new Date().toDateString();
  return a.status === 'discharged' && new Date(a.discharge_date).toDateString() === today;
}).length;
const avgLengthOfStay = admissions.reduce((acc, a) => acc + (a.length_of_stay || 0), 0) / admissions.length;
```

**After:**
```js
// Correct — comes from dedicated stats endpoint
const { data: stats, isLoading: statsLoading } = useAdmissionStatistics();

const activeAdmissions = stats?.data?.active ?? 0;
const dischargedToday = stats?.data?.discharged_today ?? 0;
const avgLengthOfStay = stats?.data?.avg_length_of_stay_days ?? 0;
```

**Implement `useAdmissionStatistics` hook:**
```ts
export function useAdmissionStatistics(params?: AdmissionQueryParams) {
  const key = params 
    ? `admission-stats-${JSON.stringify(params)}` 
    : 'admission-stats';
  return useSWR(key, () => ipdService.getAdmissionStatistics(params), {
    revalidateOnFocus: false,
    refreshInterval: 60000,  // refresh every 60s
  });
}
```

**Important:** Render stat cards independently from the list — don't block stats display on list loading. Both should load in parallel.

---

### TASK 3.2 — Fix `IPDBillingContent.tsx` revenue stats
**File:** `src/components/ipd/IPDBillingContent.tsx`

**Same problem:** Total revenue, pending amount, paid amount computed from current page of billing items.

**After Task 1.5** (backend billing stats endpoint):
```js
const { data: billingStats } = useIPDBillingStatistics({ admission: admissionId });

const totalRevenue = billingStats?.data?.total_amount ?? 0;
const paidAmount = billingStats?.data?.paid_amount ?? 0;
const pendingAmount = billingStats?.data?.pending_amount ?? 0;
```

---

### TASK 3.3 — Add `keepPreviousData: true` to all IPD list hooks
**File:** `src/hooks/useIPD.ts`

All paginated list hooks must have `keepPreviousData: true` to avoid blank flash on page change:

```ts
export function useAdmissions(params?: AdmissionQueryParams) {
  const key = params ? `admissions-${JSON.stringify(params)}` : 'admissions';
  return useSWR(key, () => ipdService.getAdmissions(params), {
    revalidateOnFocus: false,
    keepPreviousData: true,  // ADD
  });
}

export function useWards(params?: WardQueryParams) {
  const key = params ? `wards-${JSON.stringify(params)}` : 'wards';
  return useSWR(key, () => ipdService.getWards(params), {
    revalidateOnFocus: false,
    keepPreviousData: true,  // ADD
  });
}

export function useBeds(params?: BedQueryParams) {
  const key = params ? `beds-${JSON.stringify(params)}` : 'beds';
  return useSWR(key, () => ipdService.getBeds(params), {
    revalidateOnFocus: false,
    keepPreviousData: true,  // ADD
  });
}
```

---

### TASK 3.4 — Fix SWR key instability in IPD hooks
**File:** `src/hooks/useIPD.ts`

Same issue as OPD — any hooks using `...Object.values(params)` or an unstable object reference as the key will cause cache misses.

**Audit all hooks in `useIPD.ts`:**
```ts
// BAD pattern (creates new array with potentially different order):
const key = params ? ['admissions', ...Object.values(params)] : 'admissions';

// GOOD pattern (stable, deterministic):
const key = params ? `admissions-${JSON.stringify(params)}` : 'admissions';
```

Apply the stable `JSON.stringify` pattern to every hook in the file.

---

## PHASE 4 — OPTIMISTIC UI

---

### TASK 4.1 — Optimistic discharge action
**File:** `src/pages/ipd/AdmissionDetail.tsx` or wherever the discharge button lives

**Current:** Click "Discharge" → API call → reload admission → status changes (1-2s delay).

**Fix:**
```js
const handleDischarge = async (dischargeData) => {
  // Optimistic update
  mutateAdmission(
    (current) => current ? { ...current, status: 'discharged', discharge_date: new Date().toISOString() } : current,
    false  // don't revalidate yet
  );
  
  try {
    await ipdService.dischargePatient(admissionId, dischargeData);
    mutateAdmission(); // revalidate from server to confirm
  } catch (err) {
    mutateAdmission(); // revert to server truth
    toast.error('Discharge failed. Please try again.');
    throw err;
  }
};
```

---

### TASK 4.2 — Optimistic bed assignment
**File:** `src/components/ipd/BedAssignmentModal.tsx` or equivalent

**Current:** Assign bed → API call → bed list refreshes (shows old bed as available until refresh).

**Fix:**
```js
const handleAssignBed = async (bedId) => {
  // Optimistic: mark bed as occupied in ward view
  mutateWards(
    (current) => {
      if (!current) return current;
      return {
        ...current,
        results: current.results.map(ward =>
          ward.id === selectedWardId
            ? { ...ward, available_beds_count: Math.max(0, ward.available_beds_count - 1), occupied_beds_count: ward.occupied_beds_count + 1 }
            : ward
        )
      };
    },
    false
  );

  try {
    await ipdService.assignBed(admissionId, { bed: bedId });
    mutateWards(); // revalidate
    mutateAdmission();
  } catch (err) {
    mutateWards(); // revert
    toast.error('Bed assignment failed');
  }
};
```

---

### TASK 4.3 — Optimistic billing item add
**File:** `src/components/ipd/IPDBillingContent.tsx`

**Current:** Add billing item → POST → wait for response → billing table re-renders.

**Fix:**
```js
const handleAddBillingItem = async (itemData) => {
  const tempId = Date.now(); // temporary ID
  
  // Optimistic: add item immediately
  mutateBillingItems(
    (current) => current
      ? { ...current, results: [...(current.results || []), { ...itemData, id: tempId, _isOptimistic: true }] }
      : current,
    false
  );

  try {
    const result = await ipdBillingService.addBillItem(billingId, itemData);
    mutateBillingItems(); // revalidate to replace temp with real
    mutateBillingStats(); // update totals
  } catch (err) {
    mutateBillingItems(); // revert
    toast.error('Failed to add billing item');
  }
};
```

In the UI, render optimistic items with a subtle loading indicator (`opacity: 0.7`) until confirmed.

---

### TASK 4.4 — Optimistic billing item delete
**File:** `src/components/ipd/IPDBillingContent.tsx`

```js
const handleDeleteBillingItem = async (itemId) => {
  // Optimistic: remove immediately
  mutateBillingItems(
    (current) => current
      ? { ...current, results: current.results.filter(item => item.id !== itemId) }
      : current,
    false
  );

  try {
    await ipdBillingService.deleteBillItem(billingId, itemId);
    mutateBillingItems();
    mutateBillingStats();
  } catch (err) {
    mutateBillingItems(); // revert
    toast.error('Failed to remove billing item');
  }
};
```

---

### TASK 4.5 — Optimistic admission list status badge update
**File:** `src/pages/ipd/Admissions.tsx`

Any inline action that changes admission status (e.g., marking "critical", approving transfer) should update the badge immediately:

```js
const handleStatusChange = async (admissionId, newStatus) => {
  mutateAdmissions(
    (current) => current
      ? {
          ...current,
          results: current.results.map(a =>
            a.id === admissionId ? { ...a, status: newStatus } : a
          )
        }
      : current,
    false
  );

  try {
    await ipdService.updateAdmission(admissionId, { status: newStatus });
    mutateAdmissions();
  } catch (err) {
    mutateAdmissions();
    toast.error('Status update failed');
  }
};
```

---

## PHASE 5 — IPD CONSULTATION TAB OPTIMIZATION

---

### TASK 5.1 — Embed template field definitions in `ClinicalNoteTemplateResponseDetailSerializer` (Backend)
**File:** `apps/opd/serializers.py` (OPD serializer — shared between OPD and IPD)

**Problem:** `IPDConsultationTab.tsx` correctly uses:
```js
useTemplateResponses({ encounter_type: 'admission', object_id: currentObjectId })
```
But when the user selects a response, two more API calls fire:
1. `useTemplateResponse(id)` — to get field values
2. `useTemplate(templateId)` — to get field definitions/options

**After OPD Plan Task 1.4** (prefetch `field_responses__field__options` in queryset), update the detail serializer to embed template field info inline:

```python
class ClinicalNoteTemplateResponseDetailSerializer(serializers.ModelSerializer):
    field_responses = ClinicalNoteFieldResponseWithDefinitionSerializer(many=True, read_only=True)
    # field_responses now includes field label, type, options — no need to fetch template separately

class ClinicalNoteFieldResponseWithDefinitionSerializer(serializers.ModelSerializer):
    field_label = serializers.CharField(source='field.label', read_only=True)
    field_type = serializers.CharField(source='field.field_type', read_only=True)
    field_options = ClinicalNoteFieldOptionSerializer(source='field.options', many=True, read_only=True)
    
    class Meta:
        model = ClinicalNoteFieldResponse
        fields = ['id', 'field', 'field_label', 'field_type', 'field_options', 'value', 'selected_option']
```

**Result:** `GET /opd/template-responses/{id}/` returns field definitions + current values in ONE call. The `GET /opd/templates/{id}/` call is no longer needed on the consultation tab. Eliminates 1 HTTP call per note click.

---

### TASK 5.2 — Update `IPDConsultationTab.tsx` to remove redundant template fetch
**File:** `src/components/ipd/IPDConsultationTab.tsx`

**After Task 5.1 backend is deployed:**

**Before:**
```js
const { data: selectedResponse } = useTemplateResponse(selectedResponseId);
const { data: templateDetail } = useTemplate(selectedResponse?.template); // REMOVE THIS
```

**After:**
```js
const { data: selectedResponse } = useTemplateResponse(selectedResponseId);
// template fields/options are already in selectedResponse.field_responses[].field_label etc.
// No need for useTemplate() call — field definitions are embedded
```

Update the rendering code to use `res.field_label` and `res.field_options` from the embedded data instead of looking up from `templateDetail`.

---

## PHASE 6 — PRODUCTION DEPLOYMENT CHECKLIST

> Run in this exact order. Each step should be verified before proceeding.

```
Step 1: Deploy PHASE 0 backend changes (no migrations)
         → Task 0.1 — Add search_fields to AdmissionViewSet
         → Task 0.2 — Add search_fields to WardViewSet

Step 2: Deploy PHASE 0 frontend changes
         → Task 0.3 — Fix search query param key if wrong
         → Task 0.4 — Remove client-side double-filter in Admissions.tsx

Step 3: Deploy PHASE 1 backend changes
         → Task 1.1 — Ward N+1 fix (annotations in WardViewSet)
         → Task 1.2 — Bed list select_related
         → Task 1.3 — Date range filter for admissions (AdmissionFilter)
         → Task 1.4 — statistics action on AdmissionViewSet
         → Task 1.5 — statistics action on IPDBillingViewSet
         → Task 1.6 — AdmissionViewSet select_related + indexes
         → Task 1.7 — length_of_stay DB annotation
         → Task 1.8 — has_active_ipd_admission in OPD VisitDetailSerializer

Step 4: Deploy PHASE 2 service consolidation (frontend only)
         → Task 2.1 — Audit billing method duplication
         → Task 2.2 — Remove billing from ipd.service.ts
         → Task 2.3 — Create useIPDBilling hook

Step 5: Deploy PHASE 3 frontend pagination + stats fixes
         → Task 3.1 — Fix Admissions.tsx stat cards
         → Task 3.2 — Fix IPDBillingContent.tsx revenue stats
         → Task 3.3 — Add keepPreviousData: true to all IPD list hooks
         → Task 3.4 — Fix SWR key instability

Step 6: Deploy PHASE 4 optimistic UI
         → Task 4.1 — Optimistic discharge
         → Task 4.2 — Optimistic bed assignment
         → Task 4.3 — Optimistic billing item add
         → Task 4.4 — Optimistic billing item delete
         → Task 4.5 — Optimistic status badge update

Step 7: Deploy PHASE 5 consultation tab optimization
         (requires OPD Plan Task 1.4 to be deployed first)
         → Task 5.1 — Embed field definitions in response detail serializer
         → Task 5.2 — Remove redundant useTemplate call in IPDConsultationTab.tsx
```

---

## FILE INDEX

| File | Tasks |
|------|-------|
| `apps/ipd/views.py` | 0.1, 0.2, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7 |
| `apps/ipd/serializers.py` | 1.1, 1.2, 1.7 |
| `apps/ipd/filters.py` | 1.3 (new file) |
| `apps/opd/serializers.py` | 1.8, 5.1 |
| `src/pages/ipd/Admissions.tsx` | 0.3, 0.4, 3.1 |
| `src/components/ipd/IPDBillingContent.tsx` | 3.2, 4.3, 4.4 |
| `src/components/ipd/IPDConsultationTab.tsx` | 5.2 |
| `src/hooks/useIPD.ts` | 3.3, 3.4 |
| `src/hooks/useIPDBilling.ts` | 2.3 (new file) |
| `src/services/ipd.service.ts` | 2.2 |
| `src/services/ipdBilling.service.ts` | 2.2 |
| `src/pages/ipd/AdmissionDetail.tsx` | 4.1 |
| `src/components/ipd/BedAssignmentModal.tsx` | 4.2 |

---

## PRODUCTION SAFETY RULES

1. **No model fields are dropped** in this plan — only new fields/annotations added.
2. **No data migration is needed** for IPD — all changes are query-level, not schema-level.
3. **Billing service consolidation (Phase 2) is pure frontend refactor** — zero backend change, zero risk of data loss.
4. **Optimistic UI always has a revert path** — every optimistic update calls `mutate()` on error to restore server state.
5. **Statistics endpoints are read-only** — adding `@action(detail=False, methods=['get'])` is safe and backward-compatible.
6. **`keepPreviousData: true` is a read-only SWR option** — no behavior change on mutations, only affects how data is displayed during loading.
