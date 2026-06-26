# OPD Module — Complete Improvement Plan
**Project:** DigiHMS  
**Backend:** Django 5.2 + DRF (`apps/opd/`)  
**Frontend:** React + SWR (`src/pages/opd-production/`, `src/components/consultation/`)  
**Audit Date:** 2026-06-26  
**Constraint:** Production is live. No production data must be lost. All migrations must be additive or safe.

---

## AUDIT FINDINGS SUMMARY

### Critical Bugs (Breaking in production right now)
1. **Wrong query param for template responses** — `Consultation.tsx` calls `useTemplateResponses({ visit: visit?.id })` but backend filters on `object_id` + `encounter_type`. Result: ALL template responses for the entire tenant are returned, showing hundreds of `#1 #2 #3...` tabs for the wrong patients.
2. **Unstable SWR cache key** — `useTemplateResponses` builds its key with `Object.values(params)` which depends on object property insertion order. This causes cache misses and duplicate API calls on re-renders.

### Backend Issues
3. **N+1 on Ward list** — `WardSerializer` calls Python methods `get_available_beds_count()` and `get_occupied_beds_count()` per ward row. For 20 wards = 40 extra DB queries on every ward list request.
4. **No statistics endpoint for Visits list** — Frontend computes stats (waiting count, completed count, revenue) from a paginated response — so "Total Waiting: 3" only counts the current page, not all records.
5. **`ClinicalNoteTemplateResponseViewSet` missing `encounter_type` as filterset field** — The custom `get_queryset` handles `encounter_type`+`encounter_id` via `request.query_params.get()` but it's not declared in `filterset_fields`, so DRF's filter documentation and schema don't know about it.
6. **Dead commented-out code** — `ProcedureBillViewSet` (lines 1105–1193 of `views.py`) is fully commented out. Adds noise.
7. **`ClinicalNote.next_followup_date` is redundant** — Follow-up date is stored in two places: `ClinicalNote.next_followup_date` (old model) AND `Visit.follow_up_date` (new field on Visit). `ConsultationTab.tsx` reads from `ClinicalNote` for next follow-up, while `Consultation.tsx` reads from `Visit`. Both fields are in production and may have different data.
8. **`VisitListSerializer` does cross-join for `patient_name` and `doctor_name`** via `source='patient.full_name'` — already has `select_related` in viewset queryset so this is fine, but the detail serializer re-fetches `clinical_note` in some paths.
9. **`ClinicalNoteTemplateResponseViewSet` `prefetch_related('field_responses__field')` is missing `__options`** — When rendering a template response form, the frontend fetches template detail separately to get options, causing an extra round-trip.
10. **`VisitViewSet.statistics` action runs 5 separate aggregation queries** — `by_status`, `by_type`, `total_revenue`, `paid_revenue`, `pending_amount` are all separate `.aggregate()` calls. Can be combined into one query.

### Frontend Issues
11. **`ConsultationTab.tsx` makes 6+ API calls on mount:**
    - `useClinicalNoteByVisit(visit.id)` → `GET /opd/clinical-notes/?visit=X`
    - `useAdmissions({ patient: visit.patient })` → `GET /ipd/admissions/?patient=X`
    - `useTemplates({ is_active: true })` → `GET /opd/templates/`
    - `useTemplateResponses(...)` → `GET /opd/template-responses/`
    - `useTemplate(selectedTemplateId)` → `GET /opd/templates/{id}/` (fires again when response selected)
    - `useConsultationAttachment` → `GET /opd/visit-attachments/`
    - All of these re-fire independently when any state changes.

12. **`Consultation.tsx` (the page wrapper) also calls:**
    - `useOpdVisitById` → `GET /opd/visits/{id}/`
    - `useTodayVisits({ page_size: 100 })` → `GET /opd/visits/today/` (for prev/next navigation only)
    - `useTemplates` → duplicate of what `ConsultationTab` fetches
    - `useTemplateResponses` → duplicate of what `ConsultationTab` fetches (with wrong params)

13. **`useTodayVisits` has `refreshInterval: 30000`** and **`useOpdQueue` has `refreshInterval: 10000`** — Queue polling at 10 seconds is aggressive. On a slow connection this fires before the previous request completes.

14. **No optimistic UI anywhere** — Every create/update/delete waits for server response before updating UI. For field saves in the consultation form, this feels slow.

15. **`ClinicalNotes.tsx` page** (the "Follow-ups" page):
    - Uses old `ClinicalNote` API (`GET /opd/clinical-notes/`)
    - Labeled as "Follow-ups" in the UI title but the data is full clinical notes
    - `next_followup_date` from `ClinicalNote` and `follow_up_date` from `Visit` are different fields — the Follow-ups page shows clinical note follow-up dates, not visit follow-up dates

16. **`OPDVisits.tsx` and `OPDVisitDetails.tsx`** fetch both individual visit + today's visits list just to get prev/next navigation IDs — wastes a full list API call on every visit detail page.

17. **`VisitFindingViewSet` and `VisitAttachmentViewSet`** are registered endpoints but `ConsultationTab.tsx` uses `useConsultationAttachment` (a different hook) to handle attachments. `VisitFinding` appears to be an unused API on the frontend.

---

## IMPLEMENTATION PLAN

> **RULE:** Work in phases. Each phase is independently deployable. Never break the phase before moving to the next. All data migrations use `RunPython` with `reverse_code=RunPython.noop` (safe for rollback). No model fields are deleted in this plan — only new fields added.

---

## PHASE 0 — CRITICAL BUG FIXES (Deploy First, Highest Priority)

These are code-only changes. No migrations. No model changes. Safe to deploy immediately.

---

### TASK 0.1 — Fix `useTemplateResponses` wrong param in `Consultation.tsx`
**File:** `src/pages/opd-production/Consultation.tsx`  
**Lines:** 211–214

**Problem:** `useTemplateResponses({ visit: visit?.id, template: ... })` — the key `visit` is not recognized by the backend. Backend expects `object_id` + `encounter_type`.

**Fix:**
```js
// BEFORE
const { data: responsesData, isLoading: isLoadingResponses, mutate: mutateResponses } = useTemplateResponses({
  visit: visit?.id,
  template: selectedTemplate ? parseInt(selectedTemplate) : undefined,
});

// AFTER
const { data: responsesData, isLoading: isLoadingResponses, mutate: mutateResponses } = useTemplateResponses({
  object_id: visit?.id,
  encounter_type: 'visit',
  template: selectedTemplate ? parseInt(selectedTemplate) : undefined,
});
```

**Result:** The `#1 #2 #3...` tab explosion is fixed. Only current visit's notes show.

---

### TASK 0.2 — Fix unstable SWR cache key in `useTemplateResponses` hook
**File:** `src/hooks/useOPDTemplate.ts`  
**Lines:** ~433–441

**Problem:** `const key = params ? ['template-responses', ...Object.values(params)] : ['template-responses']`  
`Object.values()` order is not guaranteed across JS engines. Also, `undefined` values are included in spread, creating keys like `['template-responses', 2, undefined, undefined]` which don't match on re-render if object was reconstructed.

**Fix:**
```js
// BEFORE
const key = params ? ['template-responses', ...Object.values(params)] : ['template-responses'];

// AFTER
const key = params ? ['template-responses', JSON.stringify(params)] : ['template-responses'];
```

Apply the same fix to ALL other `useXxx` hooks in `useOPDTemplate.ts` that use `...Object.values(params)` or `[key, params]` without JSON serialization. The SWR `[key, params]` pattern works fine if `params` is the same object reference — but with React re-renders creating new objects each time, use `JSON.stringify`:

```js
// For all hooks, use this pattern:
const key = params ? `template-groups-${JSON.stringify(params)}` : 'template-groups';
```

---

### TASK 0.3 — Fix `createTemplateResponse` unwrap in `ConsultationBoard.tsx`
**File:** `src/services/opdTemplate.service.ts`, function `createTemplateResponse`

**Problem:** The service has a hacky unwrap:
```js
const result = response.data;
const unwrapped = (result as any)?.data && (result as any).data.id ? (result as any).data : result;
return unwrapped;
```

**Fix:** Decide on a consistent backend response format for `POST /opd/template-responses/`. Backend should return the created object directly (not wrapped in `{ data: {...} }`). Then remove the unwrap hack in the service and return `response.data` directly.

**Backend fix (views.py `ClinicalNoteTemplateResponseViewSet`):** Ensure `create` returns `Response(serializer.data, status=201)` — not a nested `{ "data": {...} }` wrapper. Check that `perform_create` doesn't add extra nesting.

---

## PHASE 1 — BACKEND QUERY OPTIMIZATION

No model changes. No migrations. Only `views.py` and `serializers.py` changes.

---

### TASK 1.1 — Add `visit` as alias filter to `ClinicalNoteTemplateResponseViewSet`
**File:** `apps/opd/views.py`, class `ClinicalNoteTemplateResponseViewSet`

**Problem:** The custom `get_queryset` already handles `encounter_type` + `encounter_id`, but `object_id` is in `filterset_fields`. The frontend may sometimes pass `object_id` directly (after 0.1 fix). Document this clearly and add an explicit `object_id` filter alias for `visit` type:

```python
def get_queryset(self):
    queryset = super().get_queryset()
    encounter_type = self.request.query_params.get('encounter_type')
    encounter_id = self.request.query_params.get('encounter_id') or self.request.query_params.get('object_id')

    if encounter_type and encounter_id:
        # Map encounter type to content type
        model_map = {'opd': ('opd', 'visit'), 'visit': ('opd', 'visit'), 'ipd': ('ipd', 'admission'), 'admission': ('ipd', 'admission')}
        if encounter_type.lower() in model_map:
            app_label, model_name = model_map[encounter_type.lower()]
            content_type = ContentType.objects.get(app_label=app_label, model=model_name)
            queryset = queryset.filter(content_type=content_type, object_id=encounter_id)
        else:
            return queryset.none()
    return queryset
```

**Also add `db_index=True` to `ClinicalNoteTemplateResponse.object_id`** if not already present — this field is used in every visit-scoped query.

---

### TASK 1.2 — Fix N+1 in `WardViewSet` — move Python count methods to DB annotation
**File:** `apps/ipd/views.py`, `apps/ipd/serializers.py`

**Problem:** `WardSerializer` calls `get_available_beds_count()` and `get_occupied_beds_count()` which each do a DB query per ward row.

**Fix in `views.py`:**
```python
from django.db.models import Count, Q

class WardViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    def get_queryset(self):
        return Ward.objects.filter(
            tenant_id=self.request.tenant_id
        ).annotate(
            available_beds_count=Count('beds', filter=Q(beds__is_occupied=False, beds__is_active=True)),
            occupied_beds_count=Count('beds', filter=Q(beds__is_occupied=True)),
        )
```

**Fix in `serializers.py`:**
```python
class WardSerializer(TenantMixin, serializers.ModelSerializer):
    available_beds_count = serializers.IntegerField(read_only=True)  # from annotation
    occupied_beds_count = serializers.IntegerField(read_only=True)   # from annotation
    # Remove: source='get_available_beds_count' — no longer needed
```

**Keep** the Python methods on the model as fallback (for admin or direct ORM use). Just don't call them from serializers.

---

### TASK 1.3 — Add `statistics` action to `VisitViewSet` (or optimize existing one)
**File:** `apps/opd/views.py`, class `VisitViewSet`, method `statistics`

**Problem:** Currently runs 5 separate aggregation queries. Also, list page stats are computed on the frontend from only the current page.

**Fix:** Combine into one query using `aggregate()` with multiple fields:
```python
from django.db.models import Count, Sum, Q

@action(detail=False, methods=['get'])
def statistics(self, request):
    visits = self.get_queryset()
    
    # One query for all aggregates
    agg = visits.aggregate(
        total=Count('id'),
        waiting=Count('id', filter=Q(status='waiting')),
        in_consultation=Count('id', filter=Q(status='in_consultation')),
        completed=Count('id', filter=Q(status='completed')),
        cancelled=Count('id', filter=Q(status='cancelled')),
        total_revenue=Sum('total_amount'),
        paid_revenue=Sum('paid_amount', filter=Q(payment_status='paid')),
        pending_amount=Sum('balance_amount'),
    )
    
    # One query for by_type breakdown
    by_type = list(visits.values('visit_type').annotate(count=Count('id')))
    
    return Response({'success': True, 'data': {**agg, 'by_type': by_type}})
```

Also add a `today_stats` action that always returns today's aggregate (no date filter needed from frontend):
```python
@action(detail=False, methods=['get'])
def today_stats(self, request):
    today = date.today()
    visits = self.get_queryset().filter(visit_date=today)
    # same aggregation as above
```

---

### TASK 1.4 — Optimize `ClinicalNoteTemplateResponseViewSet` queryset prefetch
**File:** `apps/opd/views.py`

**Problem:** `prefetch_related('field_responses__field')` is missing `__options`. When the frontend opens a template response form, it immediately calls `GET /opd/templates/{id}/` separately to get field options — an extra round-trip.

**Fix:** Add options to prefetch so that the response detail already contains everything:
```python
queryset = ClinicalNoteTemplateResponse.objects.select_related(
    'template', 'content_type'
).prefetch_related(
    'field_responses__field__options'  # include options
)
```

And update `ClinicalNoteTemplateResponseDetailSerializer` to include nested field options in the response, so the frontend doesn't need to call `GET /opd/templates/{id}/` when viewing a response.

---

### TASK 1.5 — Add `follow_up_date` and `follow_up_notes` to `VisitListSerializer`
**File:** `apps/opd/serializers.py`, class `VisitListSerializer`

**Problem:** `Visit.follow_up_date` and `Visit.follow_up_required` exist on the model but are not in the list serializer. Frontend fetches the detail endpoint just to get follow-up info.

**Fix:** Add to `VisitListSerializer.Meta.fields`:
```python
fields = [
    'id', 'visit_number', 'patient', 'patient_name', 'patient_id',
    'doctor', 'doctor_name', 'visit_date', 'visit_type', 'status',
    'queue_position', 'payment_status', 'total_amount', 'balance_amount',
    'waiting_time', 'entry_time', 'is_follow_up',
    'follow_up_required', 'follow_up_date', 'follow_up_notes',  # ADD THESE
]
```

---

### TASK 1.6 — Remove dead `ProcedureBillViewSet` commented-out code
**File:** `apps/opd/views.py`, lines ~1105–1193

**Action:** Delete the entire commented-out `ProcedureBillViewSet` block. It's dead code and a maintenance hazard.

---

### TASK 1.7 — Add `search_fields` to `AdmissionViewSet` (IPD)
**File:** `apps/ipd/views.py`, class `AdmissionViewSet`

**Problem:** `AdmissionViewSet` has no `search_fields`. Frontend search box sends `?search=X` but backend ignores it.

**Fix:**
```python
class AdmissionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'ward', 'doctor_id', 'patient']
    search_fields = ['admission_id', 'patient__first_name', 'patient__last_name', 'patient__mobile_primary', 'provisional_diagnosis']
    ordering_fields = ['admission_date', 'created_at']
    ordering = ['-admission_date']
```

---

### TASK 1.8 — Add `statistics` action to `AdmissionViewSet` (IPD)
**File:** `apps/ipd/views.py`, class `AdmissionViewSet`

**Problem:** Frontend `Admissions.tsx` computes `activeAdmissions`, `dischargedToday`, and `avgLengthOfStay` from the current page only — wrong for paginated results.

**Fix:** Add statistics action:
```python
@action(detail=False, methods=['get'])
def statistics(self, request):
    from django.db.models import Count, Avg, Q
    from datetime import date
    
    qs = self.get_queryset()
    today = date.today()
    
    agg = qs.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='admitted')),
        discharged_today=Count('id', filter=Q(status='discharged', discharge_date__date=today)),
        avg_length_of_stay=Avg('length_of_stay'),  # if stored, else compute
    )
    return Response({'success': True, 'data': agg})
```

Add `length_of_stay` as an annotated field in `get_queryset` if it's currently computed in Python per row:
```python
from django.db.models import ExpressionWrapper, F, fields as db_fields
from django.utils import timezone

def get_queryset(self):
    return Admission.objects.filter(tenant_id=self.request.tenant_id).annotate(
        length_of_stay=ExpressionWrapper(
            (timezone.now().date() - F('admission_date__date')),  # or use Coalesce with discharge_date
            output_field=db_fields.IntegerField()
        )
    ).select_related('patient', 'ward', 'bed')
```

---

## PHASE 2 — FOLLOW-UP DATA CONSOLIDATION (Safe Migration)

> **Production Safety:** This phase is additive only. The old `ClinicalNote.next_followup_date` column is NOT dropped. A migration script copies data from it to `Visit.follow_up_date` where the Visit field is empty. After migration, the UI reads from `Visit.follow_up_date`. The old column stays.

---

### TASK 2.1 — Understand current data split
**Before writing any migration, run this SQL on production (read-only) to understand the data:**
```sql
-- How many clinical notes have a next_followup_date?
SELECT COUNT(*) FROM opd_clinical_notes WHERE next_followup_date IS NOT NULL;

-- How many visits have follow_up_date set?
SELECT COUNT(*) FROM opd_visits WHERE follow_up_date IS NOT NULL;

-- How many have both set (potential conflict)?
SELECT COUNT(*) 
FROM opd_clinical_notes cn
JOIN opd_visits v ON v.id = cn.visit_id
WHERE cn.next_followup_date IS NOT NULL AND v.follow_up_date IS NOT NULL;

-- How many have clinical note date but no visit date (need migration)?
SELECT COUNT(*) 
FROM opd_clinical_notes cn
JOIN opd_visits v ON v.id = cn.visit_id
WHERE cn.next_followup_date IS NOT NULL AND v.follow_up_date IS NULL;
```

---

### TASK 2.2 — Write Django management command to migrate follow-up data
**File:** `apps/opd/management/commands/migrate_followup_dates.py`

**Create a new management command** (not a migration — safer, reversible, can be run with `--dry-run`):

```python
# apps/opd/management/commands/migrate_followup_dates.py
from django.core.management.base import BaseCommand
from apps.opd.models import ClinicalNote, Visit

class Command(BaseCommand):
    help = 'Copy next_followup_date from ClinicalNote to Visit.follow_up_date where Visit field is null'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Print what would be changed without saving')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        notes = ClinicalNote.objects.filter(
            next_followup_date__isnull=False,
            visit__follow_up_date__isnull=True
        ).select_related('visit')
        
        self.stdout.write(f'Found {notes.count()} records to migrate')
        
        count = 0
        for note in notes:
            if not dry_run:
                note.visit.follow_up_date = note.next_followup_date
                note.visit.follow_up_required = True
                note.visit.save(update_fields=['follow_up_date', 'follow_up_required'])
            count += 1
        
        if dry_run:
            self.stdout.write(f'DRY RUN: Would have migrated {count} records')
        else:
            self.stdout.write(self.style.SUCCESS(f'Successfully migrated {count} records'))
```

**Run on production:**
```bash
# First dry run to verify
python manage.py migrate_followup_dates --dry-run

# Then actual migration
python manage.py migrate_followup_dates
```

---

### TASK 2.3 — After migration: Update `ConsultationTab.tsx` to use `Visit.follow_up_date`
**File:** `src/components/consultation/ConsultationTab.tsx`

**After the data migration runs on production,** update the frontend to read follow-up date from `Visit` instead of `ClinicalNote`:

**Before:**
```js
const { useClinicalNoteByVisit, updateNote, createNote } = useClinicalNote();
const { data: clinicalNote, mutate: mutateClinicalNote } = useClinicalNoteByVisit(visit.id);
// ...
if (clinicalNote?.next_followup_date) {
  setFollowupDate(new Date(clinicalNote.next_followup_date));
}
// ...
await updateNote(clinicalNote.id, { next_followup_date: followupDateStr });
```

**After:**
```js
// Remove useClinicalNote import entirely from ConsultationTab
// Use visit.follow_up_date directly (already in visit object from Phase 1 Task 1.5)
useEffect(() => {
  if (visit?.follow_up_date) {
    setFollowupDate(new Date(visit.follow_up_date));
  }
}, [visit?.follow_up_date]);

// Save follow-up date via PATCH on visit
const handleSaveFollowup = async () => {
  await patchOpdVisit(visit.id, {
    follow_up_date: followupDateStr,
    follow_up_required: !!followupDateStr,
    follow_up_notes: followupNotes,
  });
  mutateVisit();
};
```

**This removes one entire API call (`GET /opd/clinical-notes/?visit=X`) from every consultation page load.**

---

### TASK 2.4 — Rename "Follow-ups" page to be accurate / or rebuild it properly
**File:** `src/pages/opd-production/ClinicalNotes.tsx`

**Current state:** Page title says "Follow-ups" but it's actually showing all `ClinicalNote` records, which is the old clinical note system (free-text). After the migration (Task 2.2), follow-up date data lives in `Visit.follow_up_date`.

**Options (choose one):**
- **Option A (Recommended):** Keep page but change it to query `Visit` with `follow_up_required=True` and `follow_up_date__gte=today`. This gives a true "upcoming follow-ups" view using the new, correct data source.
- **Option B:** Keep querying old `ClinicalNote` model but fix the page title to say "Clinical Notes" and add a separate Follow-ups page.

**If Option A:**  
Change `useClinicalNotes` to `useOpdVisits({ follow_up_required: true })` and update the table columns to show visit-based follow-up data. The backend needs to support `?follow_up_required=true` as a filter on `VisitViewSet` — add it to `filterset_fields`.

---

## PHASE 3 — FRONTEND API CALL REDUCTION

---

### TASK 3.1 — Eliminate duplicate `useTemplates` calls between `Consultation.tsx` and `ConsultationTab.tsx`

**Problem:** `Consultation.tsx` (the page) calls `useTemplates({ is_active: true })` AND `ConsultationTab.tsx` (child component) also calls `useTemplates({ is_active: true })`. Because SWR deduplicates by key, this is actually fine if the keys match exactly — BUT only if both use `JSON.stringify` keys (see Task 0.2). After Task 0.2, both will hit the SWR cache.

**Action:** After Task 0.2 is done, verify in browser Network tab that only ONE actual HTTP request fires for templates. No code change needed if SWR cache works.

---

### TASK 3.2 — Remove `useAdmissions` call from `ConsultationTab.tsx`
**File:** `src/components/consultation/ConsultationTab.tsx`, line 220

**Problem:** `ConsultationTab.tsx` calls `useAdmissions({ patient: visit.patient })` just to check if this OPD patient has an active IPD admission. This fires a `GET /ipd/admissions/?patient=X` on every consultation page for every OPD visit.

**Verify:** What is this used for? If it's just to show a badge "Patient is currently admitted in IPD", consider:
- Move this check to backend: add `has_active_admission` as a computed field in `VisitDetailSerializer`
- Or lazy-load it only when the user clicks a specific UI element

**Fix:** Add `has_active_ipd_admission` as a read-only `SerializerMethodField` in `VisitDetailSerializer`:
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

This replaces one HTTP call with one SQL `EXISTS` query embedded in the visit detail response.

---

### TASK 3.3 — Reduce `IPDConsultationTab.tsx` from 4 API calls to 2
**File:** `src/components/ipd/IPDConsultationTab.tsx`

**Current API calls on mount:**
1. `useTemplates({ is_active: true })` → `GET /opd/templates/`
2. `useTemplateResponses({ encounter_type: 'admission', object_id: id })` → `GET /opd/template-responses/`
3. On selecting a response: `useTemplateResponse(id)` → `GET /opd/template-responses/{id}/` (for field values)
4. On selecting a response: `useTemplate(templateId)` → `GET /opd/templates/{id}/` (for field definitions)

**After Task 1.4** (prefetch `field_responses__field__options` in backend):
- Call 3 (`useTemplateResponse`) already returns all field values
- The template detail (call 4) is now only needed for field metadata (labels, types, order)

**Fix:** The `ClinicalNoteTemplateResponseDetailSerializer` should embed the template's fields inline:
```python
class ClinicalNoteTemplateResponseDetailSerializer(serializers.ModelSerializer):
    template_detail = ClinicalNoteTemplateDetailSerializer(source='template', read_only=True)
    field_responses = ClinicalNoteTemplateFieldResponseSerializer(many=True, read_only=True)
    # ...
```

Now when you select a response and call `GET /opd/template-responses/{id}/`, you get everything — field definitions, options, and current values — in one response. **Eliminates call 4.**

---

### TASK 3.4 — Add optimistic UI to template response mutations
**Files:** `src/hooks/useOPDTemplate.ts`, `src/components/consultation/ConsultationBoard.tsx`

**Implement SWR optimistic update pattern for:**
1. `createTemplateResponse` — immediately add a placeholder card while server responds
2. `deleteTemplateResponse` — immediately remove card from UI
3. `updateTemplateResponse` — immediately reflect field value changes

**Pattern for SWR optimistic update:**
```js
const createTemplateResponse = useCallback(async (data) => {
  const key = ['template-responses', JSON.stringify({ object_id: data.object_id, encounter_type: data.encounter_type })];
  
  // Optimistic: add placeholder
  mutate(key, (current) => ({
    ...current,
    results: [...(current?.results || []), { ...data, id: -1, status: 'draft', response_sequence: (current?.results?.length || 0) + 1 }]
  }), false);

  try {
    const result = await opdTemplateService.createTemplateResponse(data);
    mutate(key); // revalidate from server
    return result;
  } catch (err) {
    mutate(key); // revert on error
    throw err;
  }
}, []);
```

---

### TASK 3.5 — Fix `useTodayVisits` usage in `Consultation.tsx` for navigation
**File:** `src/pages/opd-production/Consultation.tsx`, lines 105–114

**Problem:** `useTodayVisits({ page_size: 100 })` is called on every consultation page just to get IDs for prev/next navigation. This fetches up to 100 full visit records.

**Options:**
- **Option A:** Pass `visitIds` array in route state when navigating from the visits list (already partially done — `location.state?.visitIds`). Make the visits list always pass this state. Then `useTodayVisits` call is only a fallback when `visitIds` is missing.
- **Option B:** Add a `GET /opd/visits/today/ids/` endpoint that returns only `[{id, patient_name}]` — minimal payload for navigation.

**Fix for Option A (recommended — no backend change):**
```js
// In Consultation.tsx
const visitIdsFromState = (location.state as any)?.visitIds as number[];

// Only call useTodayVisits if state doesn't have visitIds
const shouldFetchToday = !visitIdsFromState;
const { data: todayVisitsData } = useTodayVisits(
  shouldFetchToday ? { page_size: 100 } : undefined  // skip if we have state
);
```

**In `OPDVisits.tsx` (the list page):** When navigating to a visit, always pass visitIds:
```js
navigate(`/opd/consultation/${visit.id}`, {
  state: { visitIds: visits.map(v => v.id), from: '/opd/visits' }
});
```

---

### TASK 3.6 — Fix client-side stats in `Admissions.tsx` (IPD)
**File:** `src/pages/ipd/Admissions.tsx`

**Problem:** `activeAdmissions`, `dischargedToday`, `avgLengthOfStay` are computed via `useMemo` + `.filter()` on `admissions` which is ONLY the current page. Wrong for paginated data.

**Fix:** After Task 1.8 (backend stats endpoint):
```js
// Add a useIPDStatistics hook
const { data: stats } = useIPDStatistics(); // calls GET /ipd/admissions/statistics/

// Replace client-side computed values with backend stats
const activeAdmissions = stats?.active ?? 0;
const dischargedToday = stats?.discharged_today ?? 0;
const avgLengthOfStay = stats?.avg_length_of_stay ?? 0;
```

Also remove the client-side status/date filtering `useMemo` block entirely — the backend `filterset_fields` already handles `status` and date range. Frontend should just pass these as query params and trust the backend response.

---

### TASK 3.7 — Fix client-side double-filtering in `Admissions.tsx`
**File:** `src/pages/ipd/Admissions.tsx`, lines 67–90

**Problem:** Status filter and date range are both sent to the backend AND also applied client-side via `useMemo`. This is wasteful and confusing.

**Fix:** Remove the `useMemo` filtering block entirely:
```js
// REMOVE this entire block:
const admissions = useMemo(() => {
  return rawAdmissions.filter((admission) => { ... });
}, [rawAdmissions, statusFilter, dateRange]);

// REPLACE with:
const admissions = rawAdmissions;  // backend already filtered
```

The backend `filterset_fields` for `AdmissionViewSet` already supports `status`. Add date range support:
```python
class AdmissionFilter(django_filters.FilterSet):
    admission_date__gte = django_filters.DateFilter(field_name='admission_date', lookup_expr='date__gte')
    admission_date__lte = django_filters.DateFilter(field_name='admission_date', lookup_expr='date__lte')
    
    class Meta:
        model = Admission
        fields = ['status', 'ward', 'doctor_id', 'patient']

class AdmissionViewSet(...):
    filterset_class = AdmissionFilter  # use custom FilterSet
```

---

### TASK 3.8 — Reduce polling frequency and add smarter refresh
**Files:** `src/hooks/useOpdVisit.ts`

**Problem:**
- `useOpdQueue` polls every 10 seconds — too aggressive
- `useTodayVisits` polls every 30 seconds

**Fix:**
```js
// useOpdQueue — increase to 30s
refreshInterval: 30000,

// useTodayVisits — keep 30s but add visibilityState check
refreshInterval: 30000,
refreshWhenHidden: false,  // stop polling when tab is not visible
```

Also add `dedupingInterval: 5000` to both to prevent duplicate requests within 5 seconds.

---

## PHASE 4 — OPTIMISTIC UI & UX POLISH

---

### TASK 4.1 — Optimistic status change for "Start Consultation"
**File:** `src/pages/opd-production/Consultation.tsx`

**Current:** Click "Start" → POST → wait 500ms–1s → button state changes.

**Fix:**
```js
const handleStartConsultation = async () => {
  // Optimistic: immediately reflect in local state
  mutateVisit((current) => current ? { ...current, status: 'in_consultation' } : current, false);
  
  try {
    await patchOpdVisit(visit.id, { status: 'in_consultation', started_at: new Date().toISOString() });
    mutateVisit(); // confirm from server
  } catch {
    mutateVisit(); // revert
    toast.error('Failed to start consultation');
  }
};
```

---

### TASK 4.2 — Add `keepPreviousData: true` to all list hooks
**Files:** `src/hooks/useOPDTemplate.ts`, `src/hooks/useIPD.ts`

All paginated list hooks should use `keepPreviousData: true` so pagination doesn't flash empty state:
```js
return useSWR(key, fetcher, {
  revalidateOnFocus: false,
  keepPreviousData: true,  // ADD THIS to all list hooks
});
```

This applies to: `useTemplateGroups`, `useTemplates`, `useTemplateFields`, `useTemplateResponses`, `useAdmissions`, `useBeds`, `useWards`.

---

### TASK 4.3 — Consolidate IPD `ipd.service.ts` billing + `ipdBilling.service.ts`
**Files:** `src/services/ipd.service.ts`, `src/services/ipdBilling.service.ts`, `src/hooks/useIPD.ts`

**Problem:** Both services have billing-related methods hitting the same endpoints. `IPDBillingContent.tsx` uses `ipdBillingService` directly. The `useIPD` hook uses `ipdService.getBillings()`.

**Fix:**
1. Remove all billing methods from `ipd.service.ts` (lines ~200 onwards for billing)
2. Remove `getBillings`, `getBilling`, `createBilling`, etc. from `ipd.service.ts`
3. Update `useIPD.ts` to call `ipdBillingService` for billing operations
4. Or: Add a `useIPDBilling` hook that wraps `ipdBillingService`

---

## PHASE 5 — PRODUCTION DEPLOYMENT CHECKLIST

> Run in this exact order to avoid production breakage.

```
Step 1: Deploy PHASE 0 backend changes (no migrations needed)
         → Task 1.1 (backend filter alias)
         → Task 1.7 (search_fields for admissions)
         
Step 2: Deploy PHASE 0 frontend changes
         → Task 0.1 (fix visit param bug) ← MOST CRITICAL
         → Task 0.2 (stable SWR keys)
         → Task 0.3 (fix response unwrap)
         
Step 3: Deploy PHASE 1 backend changes
         → Task 1.2 (ward N+1 fix)
         → Task 1.3 (visit statistics)
         → Task 1.4 (prefetch options)
         → Task 1.5 (follow_up_date in list)
         → Task 1.6 (remove dead code)
         → Task 1.8 (admission statistics)
         
Step 4: Run PHASE 2 data migration (on production DB)
         → python manage.py migrate_followup_dates --dry-run  (verify first)
         → python manage.py migrate_followup_dates            (execute)
         
Step 5: Deploy PHASE 2 frontend changes
         → Task 2.3 (read follow-up from Visit, not ClinicalNote)
         → Task 2.4 (fix Follow-ups page)
         
Step 6: Deploy PHASE 3 frontend changes
         → Tasks 3.1 through 3.8
         
Step 7: Deploy PHASE 4 UX changes
         → Tasks 4.1 through 4.3
```

---

## FILE INDEX

| File | Tasks |
|------|-------|
| `src/pages/opd-production/Consultation.tsx` | 0.1, 3.5 |
| `src/hooks/useOPDTemplate.ts` | 0.2, 3.4, 4.2 |
| `src/components/consultation/ConsultationTab.tsx` | 2.3, 3.2 |
| `src/components/ipd/IPDConsultationTab.tsx` | 3.3 |
| `src/pages/ipd/Admissions.tsx` | 3.6, 3.7 |
| `src/hooks/useOpdVisit.ts` | 3.8, 4.2 |
| `src/hooks/useIPD.ts` | 4.3, 4.2 |
| `src/services/opdTemplate.service.ts` | 0.3 |
| `src/services/ipd.service.ts` | 4.3 |
| `src/pages/opd-production/ClinicalNotes.tsx` | 2.4 |
| `apps/opd/views.py` | 1.1, 1.3, 1.4, 1.6 |
| `apps/opd/serializers.py` | 1.5, 3.3 |
| `apps/ipd/views.py` | 1.2, 1.7, 1.8, 3.7 |
| `apps/ipd/serializers.py` | 1.2 |
| `apps/opd/management/commands/migrate_followup_dates.py` | 2.2 (new file) |
