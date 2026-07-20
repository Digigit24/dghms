# Dashboard API reference

## Recent encounters

`GET /api/dashboard/recent-encounters/`

Each row under `data.results` includes two integer pending-work counters:

```json
{
  "encounter_type": "opd",
  "encounter_id": 2401,
  "patient_id": 123,
  "patient_name": "Patient Name",
  "number": "OPD/2026/001",
  "doctor_name": "Doctor Name",
  "date": "2026-07-20",
  "status": "completed",
  "pending_pharmacy_count": 2,
  "pending_lab_count": 1
}
```

- `pending_pharmacy_count`: undispensed prescription-item count for this
  encounter. Returns `0` when there is no prescription or no undispensed item.
- `pending_lab_count`: investigation diagnostic-order count whose status is
  neither `completed` nor `cancelled`. Returns `0` when there is no matching
  requisition or pending order.

The counts are computed in two batched aggregate queries for the paginated
encounter rows, not with per-row queries.
