# Inventory Management — Frontend API Reference

Base URL: `https://api.celiyo.com/api/inventory/`  
Auth: `Authorization: Bearer <jwt>`  
All list endpoints support `?page=N&page_size=50` (max 200).

---

## 1. Categories

### List
```
GET /api/inventory/categories/
Query: search, parent (int), is_active (bool)
```
```json
{
  "count": 5,
  "results": [
    {
      "id": 1,
      "name": "Medicines",
      "code": "MED",
      "description": "",
      "parent": null,
      "parent_name": null,
      "is_active": true,
      "children_count": 3,
      "created_at": "2026-06-01T10:00:00Z",
      "updated_at": "2026-06-01T10:00:00Z"
    }
  ]
}
```

### Create
```
POST /api/inventory/categories/
```
```json
{
  "name": "Surgical Supplies",
  "code": "SURG",
  "description": "Disposable surgical items",
  "parent": 1,
  "is_active": true
}
```

### Update
```
PATCH /api/inventory/categories/{id}/
```
Send only fields to change.

### Delete
```
DELETE /api/inventory/categories/{id}/
→ 204 No Content
```

---

## 2. Suppliers

### List
```
GET /api/inventory/suppliers/
Query: search (name/code/contact/phone), is_active
```
```json
{
  "count": 10,
  "results": [
    {
      "id": 1,
      "name": "MedCo Pharma",
      "code": "MEDCO",
      "contact_name": "Rahul Shah",
      "phone": "9876543210",
      "email": "rahul@medco.in",
      "address": "Mumbai",
      "gstin": "27AAPFU0939F1ZV",
      "is_active": true,
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### Create
```
POST /api/inventory/suppliers/
```
```json
{
  "name": "MedCo Pharma",
  "code": "MEDCO",
  "contact_name": "Rahul Shah",
  "phone": "9876543210",
  "email": "rahul@medco.in",
  "address": "Mumbai",
  "gstin": "27AAPFU0939F1ZV"
}
```

---

## 3. Items

### List (compact)
```
GET /api/inventory/items/
Query: search (name/code/barcode), category (int), is_active, tags (comma-separated: opd,ipd,general,pharmacy,surgical,lab,other)
```
```json
{
  "count": 120,
  "results": [
    {
      "id": 5,
      "name": "Paracetamol 500mg",
      "code": "PCT500",
      "barcode": "8901234567890",
      "category": 1,
      "category_name": "Medicines",
      "tags": ["opd", "ipd", "pharmacy"],
      "unit_of_measure": "tablet",
      "purchase_price": "2.50",
      "selling_price": "3.50",
      "reorder_level": "100.00",
      "max_stock_level": "5000.00",
      "current_stock": "1200.00",
      "is_active": true,
      "is_low_stock": false,
      "is_out_of_stock": false,
      "is_overstock": false,
      "created_at": "..."
    }
  ]
}
```

### Get Detail
```
GET /api/inventory/items/{id}/
```
Returns full item + `tax_rate`, `hsn_code`, `description`, `created_by_user_id`, `updated_at`.

### Create
```
POST /api/inventory/items/
```
```json
{
  "name": "Paracetamol 500mg",
  "code": "PCT500",
  "barcode": "8901234567890",
  "category": 1,
  "tags": ["opd", "pharmacy"],
  "unit_of_measure": "tablet",
  "purchase_price": "2.50",
  "selling_price": "3.50",
  "tax_rate": "0.00",
  "hsn_code": "30049099",
  "reorder_level": "100.00",
  "max_stock_level": "5000.00",
  "description": "OTC analgesic"
}
```

Valid `unit_of_measure` values: `pcs strip box bottle vial ampoule ml litre gm kg tablet capsule sachet roll pair set other`  
Valid `tags`: `opd ipd general pharmacy surgical lab other`

### Update
```
PATCH /api/inventory/items/{id}/
```

### Low Stock Items
```
GET /api/inventory/items/low-stock/
→ Paginated list of items where current_stock ≤ reorder_level
```

### Expiring Soon
```
GET /api/inventory/items/expiring-soon/?days=90
→ Items with at least one batch expiring within N days (default 90)
```

### Stock History for Item
```
GET /api/inventory/items/{id}/stock-history/
Query: date_from (YYYY-MM-DD), date_to, transaction_type
→ Paginated list of StockTransaction objects for this item (newest first)
```

---

## 4. Batches

### List
```
GET /api/inventory/batches/
Query: item (int), supplier (int), is_active, expiring_within_days (int)
```
```json
{
  "count": 3,
  "results": [
    {
      "id": 12,
      "item": 5,
      "item_name": "Paracetamol 500mg",
      "batch_number": "B2024001",
      "expiry_date": "2026-12-31",
      "manufacturing_date": "2024-01-01",
      "purchase_date": "2024-02-15",
      "supplier": 1,
      "supplier_name": "MedCo Pharma",
      "purchase_price": "2.50",
      "quantity_received": "500.00",
      "remaining_quantity": "320.00",
      "is_active": true,
      "notes": "",
      "is_expired": false,
      "days_to_expiry": 185,
      "created_by_user_id": "uuid",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### Create
Creating a batch via this endpoint automatically creates a `purchase` stock transaction.
```
POST /api/inventory/batches/
```
```json
{
  "item": 5,
  "batch_number": "B2024001",
  "expiry_date": "2026-12-31",
  "manufacturing_date": "2024-01-01",
  "supplier": 1,
  "purchase_price": "2.50",
  "quantity_received": "500.00",
  "notes": "Monthly reorder"
}
```

> **Prefer `POST /stock-transactions/receive/`** for production use — it has better validation and richer error responses.

---

## 5. Stock Transactions

### List
```
GET /api/inventory/stock-transactions/
Query: item (int), transaction_type, reference_type, date_from, date_to
Ordered: newest first
```
```json
{
  "count": 88,
  "results": [
    {
      "id": "uuid",
      "item": 5,
      "item_name": "Paracetamol 500mg",
      "item_unit": "tablet",
      "batch": 12,
      "batch_number": "B2024001",
      "transaction_type": "issue_opd",
      "transaction_type_label": "Issued to OPD",
      "quantity": "10.00",
      "quantity_before": "1210.00",
      "quantity_after": "1200.00",
      "unit_cost": "2.50",
      "reference_type": "opd_visit",
      "reference_id": "4567",
      "notes": "",
      "is_addition": false,
      "performed_by_user_id": "uuid",
      "created_at": "2026-06-28T14:30:00Z"
    }
  ]
}
```

Valid `transaction_type` values:
| Value | Direction | Meaning |
|---|---|---|
| `opening_stock` | ➕ | Initial stock entry |
| `purchase` | ➕ | Received from supplier |
| `return_from_use` | ➕ | Returned by patient/dept |
| `adjustment_add` | ➕ | Manual correction (add) |
| `issue_opd` | ➖ | Issued to OPD patient |
| `issue_ipd` | ➖ | Issued to IPD patient |
| `issue_general` | ➖ | General department issue |
| `adjustment_remove` | ➖ | Manual correction (remove) |
| `disposal` | ➖ | Damaged / written off |
| `transfer_out` | ➖ | Sent to another location |
| `expired` | ➖ | Expired stock removed |

### Receive Stock (recommended for purchases)
```
POST /api/inventory/stock-transactions/receive/
```
Creates a new batch + `purchase` transaction atomically.
```json
{
  "item": 5,
  "batch_number": "B2024002",
  "quantity": "1000.00",
  "expiry_date": "2027-06-30",
  "manufacturing_date": "2024-06-01",
  "supplier": 1,
  "unit_cost": "2.50",
  "reference_id": "PO-2024-056",
  "notes": "June reorder"
}
```
Response `201`:
```json
{
  "success": true,
  "message": "Stock received.",
  "data": { /* StockTransaction object */ }
}
```

### Issue Stock
```
POST /api/inventory/stock-transactions/issue/
```
Issues stock for OPD/IPD/general. Validates sufficient stock before writing.
```json
{
  "item": 5,
  "batch": 12,
  "quantity": "10.00",
  "issue_type": "issue_opd",
  "reference_type": "opd_visit",
  "reference_id": "4567",
  "notes": "Prescribed by Dr. Sharma"
}
```
`issue_type` choices: `issue_opd | issue_ipd | issue_general`  
`reference_type` choices: `opd_visit | ipd_admission | manual | other`

Error `422` if insufficient stock:
```json
{
  "success": false,
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Insufficient stock. Available: 50 tablet.",
    "field": null,
    "detail": {}
  }
}
```

### Adjust Stock
```
POST /api/inventory/stock-transactions/adjust/
```
Manual add or removal (write-off, correction, expiry clearance).
```json
{
  "item": 5,
  "batch": 12,
  "adjustment_type": "disposal",
  "quantity": "20.00",
  "notes": "Damaged in storage"
}
```
`adjustment_type` choices: `adjustment_add | adjustment_remove | disposal | expired`

---

## 6. Alerts

### List
```
GET /api/inventory/alerts/
Query: is_active (bool), is_acknowledged (bool), alert_type, item (int)
Ordered: newest first
```
```json
{
  "count": 4,
  "results": [
    {
      "id": "uuid",
      "item": 5,
      "item_name": "Paracetamol 500mg",
      "item_code": "PCT500",
      "item_unit": "tablet",
      "batch": null,
      "batch_number": null,
      "expiry_date": null,
      "alert_type": "low_stock",
      "alert_type_label": "Low Stock",
      "message": "Paracetamol 500mg is below reorder level (80 / 100 tablet).",
      "current_value": "80.00",
      "threshold": "100.00",
      "is_active": true,
      "is_acknowledged": false,
      "acknowledged_by_user_id": null,
      "acknowledged_at": null,
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

Alert types: `low_stock | out_of_stock | expiry_approaching | expired | overstock`

### Acknowledge Alert
```
POST /api/inventory/alerts/{id}/acknowledge/
Body: {} (empty)
```
Response `200`:
```json
{
  "success": true,
  "message": "Alert acknowledged.",
  "data": { /* updated alert */ }
}
```

### Alert Summary (for badge/notification counts)
```
GET /api/inventory/alerts/summary/
```
```json
{
  "success": true,
  "data": {
    "total": 6,
    "unacknowledged": 4,
    "by_type": {
      "low_stock": 2,
      "out_of_stock": 1,
      "expiry_approaching": 3
    }
  }
}
```

### Refresh All Alerts
```
POST /api/inventory/alerts/refresh/
Body: {} (empty)
→ Re-evaluates all items. Use after bulk import.
```

---

## 7. Dashboard

```
GET /api/inventory/dashboard/stats/
```
```json
{
  "success": true,
  "data": {
    "total_items": 150,
    "active_items": 145,
    "low_stock_count": 8,
    "out_of_stock_count": 2,
    "overstock_count": 1,
    "expiring_soon_count": 5,
    "expired_count": 1,
    "total_categories": 12,
    "active_alerts": 11,
    "unacknowledged_alerts": 7,
    "total_stock_value": "284500.00",
    "recent_transactions": [
      /* last 10 StockTransaction objects */
    ]
  }
}
```

---

## Error Codes

| Code | Status | Meaning |
|---|---|---|
| `ITEM_NOT_FOUND` | 404 | Item doesn't exist for this tenant |
| `BATCH_NOT_FOUND` | 404 | Batch not found or doesn't belong to item |
| `SUPPLIER_NOT_FOUND` | 404 | Supplier doesn't exist for this tenant |
| `INSUFFICIENT_STOCK` | 422 | Not enough stock on item |
| `INSUFFICIENT_BATCH_STOCK` | 422 | Not enough remaining in the specific batch |

---

## Permissions Required (HMS module: `inventory`)

| Action | Permission |
|---|---|
| All GETs / list / retrieve / dashboard | `view_inventory` |
| Create / update / delete / receive / issue / adjust / acknowledge / refresh | `manage_inventory` |

---

## Recommended Frontend Workflow

### Stock Receive Flow
1. `GET /items/?search=...` — pick item
2. `GET /suppliers/` — pick supplier
3. `POST /stock-transactions/receive/` — creates batch + transaction in one call
4. Invalidate `/items/{id}/` and `/dashboard/stats/` queries

### Issue Flow (OPD/IPD)
1. `GET /items/?tags=opd&search=...` — pick item
2. `GET /batches/?item={id}&is_active=true` — show batches sorted by expiry (FEFO)
3. `POST /stock-transactions/issue/` — pass `batch` id for FEFO compliance
4. Invalidate item + dashboard queries

### Alert Badge
- Poll `GET /alerts/summary/` every 60s (or on page focus)
- Show `unacknowledged` count as badge
- `POST /alerts/{id}/acknowledge/` on user action

### Low Stock / Expiry Alerts Page
- `GET /items/low-stock/` — items needing reorder
- `GET /items/expiring-soon/?days=30` — critical expiry
- `GET /batches/?expiring_within_days=30` — batch-level detail
