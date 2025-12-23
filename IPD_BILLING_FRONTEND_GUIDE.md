# IPD Billing API - Frontend Implementation Guide

## Overview

The IPD billing system mirrors the OPD billing system exactly, making it easy to replicate the OPD billing UI for IPD. The backend supports **multiple bills per admission** (similar to OPD's multiple bills per visit), with automatic total calculation from line items, signal-driven recalculation, and payment tracking.

## Core Concepts

### 1. Bill Structure
- **IPD Bill** (`IPDBilling`): Main bill record with totals, discounts, and payment info
- **IPD Bill Items** (`IPDBillItem`): Individual line items (bed charges, pharmacy, lab tests, etc.)
- **Automatic Calculations**: Totals recalculate automatically when items are added/updated/deleted

### 2. Multiple Bills Per Admission
Unlike the old system (one bill per admission), the new system allows **multiple bills** for one admission, similar to how OPD works:
- Create interim bills during admission
- Create final bill at discharge
- Split bills by department or service type
- Each bill tracks its own payment status independently

### 3. Bill Item Sources
Items can come from multiple sources:
- `Bed`: Bed charges (auto-calculated from length of stay)
- `Pharmacy`: Medicine orders
- `Lab`: Laboratory tests
- `Radiology`: Radiology investigations
- `Consultation`: Doctor consultations
- `Procedure`: Medical procedures
- `Surgery`: Surgical procedures
- `Therapy`: Therapy sessions (Panchakarma, etc.)
- `Package`: Package deals
- `Other`: Miscellaneous charges

---

## API Endpoints

### Base URL
```
/api/ipd/ipd-bills/
```

### 1. List All IPD Bills
**GET** `/api/ipd/billings/`

**Query Parameters:**
- `admission={admission_id}` - Filter by admission
- `payment_status=unpaid|partial|paid` - Filter by payment status
- `search={term}` - Search by bill number or patient name

**Response Example:**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 5,
      "bill_number": "IPD-BILL/20251222/005",
      "admission": 10,
      "admission_number": "IPD/20251219/001",
      "patient_name": "John Doe",
      "doctor_id": "uuid-here",
      "bill_date": "2025-12-22T10:30:00Z",
      "total_amount": "15000.00",
      "discount_amount": "500.00",
      "payable_amount": "14500.00",
      "received_amount": "10000.00",
      "balance_amount": "4500.00",
      "payment_status": "partial",
      "payment_mode": "cash",
      "items": [
        {
          "id": 12,
          "item_name": "General Ward - Bed A-101 - 3 day(s)",
          "source": "Bed",
          "quantity": 3,
          "unit_price": "1500.00",
          "total_price": "4500.00"
        },
        {
          "id": 13,
          "item_name": "CBC Test",
          "source": "Lab",
          "quantity": 1,
          "unit_price": "500.00",
          "total_price": "500.00"
        }
      ]
    }
  ]
}
```

### 2. Get Single Bill
**GET** `/api/ipd/billings/{id}/`

Returns detailed bill information with all line items.

### 3. Create IPD Bill
**POST** `/api/ipd/billings/`

**Request Payload:**
```json
{
  "admission": 10,
  "doctor_id": "uuid-here",
  "diagnosis": "Post-operative care",
  "remarks": "Patient recovering well",
  "discount_percent": "0",
  "discount_amount": "0",
  "payment_mode": "cash",
  "received_amount": "0",
  "bill_date": "2025-12-22"
}
```

**Response:** Returns created bill with auto-generated `bill_number` and `id`.

### 4. Update IPD Bill (Partial)
**PATCH** `/api/ipd/billings/{id}/`

**Request Payload (Payment Example):**
```json
{
  "received_amount": "5000.00",
  "payment_mode": "card",
  "payment_details": {
    "card_type": "visa",
    "last_4_digits": "1234",
    "transaction_id": "TXN123456"
  }
}
```

**Response:** Returns updated bill with recalculated `balance_amount` and `payment_status`.

**Important:** All fields like `total_amount`, `payable_amount`, `balance_amount`, and `payment_status` are **auto-calculated** - don't send them in PATCH requests.

### 5. Sync Clinical Charges to Bill
**POST** `/api/ipd/admissions/{admission_id}/sync_clinical_charges/`

Automatically imports all unbilled requisitions (lab tests, medicines, procedures) into the most recent unpaid/partial bill for this admission.

**Request:** Empty body `{}`

**Response:**
```json
{
  "success": true,
  "message": "Synced 5 clinical charges to bill IPD-BILL/20251222/005",
  "created_items": 5,
  "updated_orders": 5,
  "bill_id": 5
}
```

### 6. Preview Unbilled Requisitions
**GET** `/api/ipd/admissions/{admission_id}/unbilled_requisitions/`

Shows what will be synced before actually calling `sync_clinical_charges`.

**Response:**
```json
{
  "success": true,
  "admission_id": 10,
  "admission_number": "IPD/20251219/001",
  "total_unbilled_items": 3,
  "estimated_amount": 1250.00,
  "requisitions": [
    {
      "requisition_id": 45,
      "requisition_number": "REQ-001",
      "requisition_type": "investigation",
      "status": "ordered",
      "unbilled_orders": [
        {
          "type": "diagnostic",
          "id": 89,
          "name": "X-Ray Chest",
          "category": "radiology",
          "price": "750.00"
        }
      ]
    }
  ]
}
```

---

## Frontend Implementation Steps

### 1. List/Filter Bills
- Display bills grouped by admission
- Show payment status badges (unpaid=red, partial=yellow, paid=green)
- Filter by status, date range, patient

### 2. Bill Details View
- Show bill header (number, date, patient, admission)
- List all line items in a table
- Display totals section: subtotal, discount, payable, received, balance
- Show payment status prominently

### 3. Create New Bill
- Select admission (or auto-fill if coming from admission page)
- Optional: Auto-sync unbilled charges first
- Select payment mode and amount received
- Apply discount (percentage or fixed amount)
- Submit to create bill

### 4. Record Payment
- PATCH the bill with `received_amount`
- Backend automatically recalculates balance and updates status
- Show success message with updated balance

### 5. Add Manual Line Items
Use `/api/ipd/bill-items/` endpoint to add miscellaneous charges:

**POST** `/api/ipd/bill-items/`
```json
{
  "bill": 5,
  "item_name": "Special Nursing Care",
  "source": "Other",
  "quantity": 2,
  "unit_price": "500.00",
  "notes": "24-hour special nursing"
}
```

Signals automatically update parent bill totals.

### 6. Sync Clinical Charges Button
Add a "Sync Lab/Pharmacy Charges" button that:
1. Calls `/unbilled_requisitions/` to preview
2. Shows modal with items to be synced
3. On confirm, calls `/sync_clinical_charges/`
4. Refreshes bill to show new items

---

## Key Differences from OPD

| Feature | OPD | IPD |
|---------|-----|-----|
| Parent Entity | `Visit` | `Admission` |
| Bill Model | `OPDBill` | `IPDBilling` |
| Item Model | `OPDBillItem` | `IPDBillItem` |
| Endpoint | `/api/opd/opd-bills/` | `/api/ipd/ipd-bills/` |
| Additional Items | Consultation fees | Bed charges |

**Everything else is identical!** You can literally copy your OPD billing UI components and change the API endpoints.

---

## Error Handling

### Common Errors

**400 Bad Request:**
```json
{
  "received_amount": ["Received amount cannot exceed payable amount (14500.00)"]
}
```
Solution: Validate amounts on frontend before submission.

**404 Not Found:**
```json
{
  "detail": "Not found."
}
```
Solution: Check bill ID exists and user has permission to access.

---

## Summary

The IPD billing system is a direct mirror of OPD billing. If you've already built the OPD billing UI:
1. Copy the components
2. Replace API endpoints (`/opd/opd-bills/` → `/ipd/ipd-bills/`)
3. Replace entity references (`visit` → `admission`)
4. Add bed charge handling (optional, auto-calculated)
5. Done!

All auto-calculations, validations, and payment tracking work identically to OPD.
