# Frontend Integration: Requisition Updates

## Summary (< 100 words)

**Key Changes:**
1. Response field `orders` renamed to `investigation_orders`
2. New `requisition_type` field (investigation/medicine/procedure/package)
3. Three new nested arrays: `medicine_orders`, `procedure_orders`, `package_orders`
4. New endpoints: `POST /requisitions/{id}/add_medicine/`, `/add_procedure/`, `/add_package/`
5. Payload: `{product_id|procedure_id|package_id, quantity, price(optional)}`
6. Filter: `GET /requisitions/?requisition_type=medicine`
7. All existing requisitions default to `type=investigation`
8. Type-specific endpoints validate requisition type matches

**Migration:** Update `response.orders` → `response.investigation_orders` in your code.

---

## 1. Creating Requisitions - Payload Examples

### Investigation Requisition (existing behavior)
```json
POST /api/requisitions/
{
  "patient": 123,
  "requesting_doctor_id": "uuid-here",
  "requisition_type": "investigation",
  "encounter_type": "opd.visit",
  "encounter_id": 456,
  "investigation_ids": [10, 11, 12],
  "priority": "routine"
}
```

### Medicine Requisition (NEW)
```json
POST /api/requisitions/
{
  "patient": 123,
  "requesting_doctor_id": "uuid-here",
  "requisition_type": "medicine",
  "encounter_type": "opd.visit",
  "encounter_id": 456,
  "priority": "routine"
}

// Then add medicines:
POST /api/requisitions/1/add_medicine/
{
  "product_id": 50,
  "quantity": 2,
  "price": 120.50  // optional
}
```

### Procedure Requisition (NEW)
```json
POST /api/requisitions/
{
  "patient": 123,
  "requesting_doctor_id": "uuid-here",
  "requisition_type": "procedure",
  "encounter_type": "ipd.admission",
  "encounter_id": 789,
  "priority": "urgent"
}

// Then add procedures:
POST /api/requisitions/2/add_procedure/
{
  "procedure_id": 20,
  "quantity": 1,
  "price": 5000.00  // optional
}
```

### Package Requisition (NEW)
```json
POST /api/requisitions/
{
  "patient": 123,
  "requesting_doctor_id": "uuid-here",
  "requisition_type": "package",
  "encounter_type": "opd.visit",
  "encounter_id": 456
}

// Then add packages:
POST /api/requisitions/3/add_package/
{
  "package_id": 5,
  "quantity": 1,
  "price": 15000.00  // optional
}
```

---

## 2. Response Structure

```json
{
  "id": 1,
  "requisition_number": "REQ-20231223-ABC123",
  "requisition_type": "investigation",
  "patient": 123,
  "requesting_doctor_id": "uuid-here",
  "status": "ordered",
  "priority": "routine",

  // RENAMED: was "orders", now "investigation_orders"
  "investigation_orders": [
    {
      "id": 1,
      "investigation": 10,
      "investigation_name": "CBC",
      "price": "500.00",
      "status": "pending"
    }
  ],

  // NEW
  "medicine_orders": [],
  "procedure_orders": [],
  "package_orders": []
}
```

---

## 3. Filtering Requisitions

```javascript
// Filter by type
GET /api/requisitions/?requisition_type=medicine
GET /api/requisitions/?requisition_type=investigation
GET /api/requisitions/?requisition_type=procedure
GET /api/requisitions/?requisition_type=package

// Filter by patient
GET /api/requisitions/?patient=123

// Combine filters
GET /api/requisitions/?patient=123&requisition_type=medicine&status=ordered
```

---

## 4. UI Implementation Pattern

```javascript
// Step 1: Create requisition based on type
const createRequisition = async (type) => {
  const payload = {
    patient: patientId,
    requesting_doctor_id: doctorId,
    requisition_type: type,  // 'investigation', 'medicine', 'procedure', 'package'
    encounter_type: 'opd.visit',
    encounter_id: visitId,
    priority: 'routine'
  };

  // For investigations, can add investigation_ids directly
  if (type === 'investigation') {
    payload.investigation_ids = [10, 11, 12];
  }

  return await POST('/api/requisitions/', payload);
};

// Step 2: Add items to requisition
const addItemsToRequisition = async (requisitionId, type, items) => {
  const endpoints = {
    medicine: '/add_medicine/',
    procedure: '/add_procedure/',
    package: '/add_package/'
  };

  for (const item of items) {
    await POST(`/api/requisitions/${requisitionId}${endpoints[type]}`, item);
  }
};

// Step 3: Display based on type
const displayRequisition = (requisition) => {
  const orderMap = {
    investigation: requisition.investigation_orders,
    medicine: requisition.medicine_orders,
    procedure: requisition.procedure_orders,
    package: requisition.package_orders
  };

  const orders = orderMap[requisition.requisition_type] || [];
  return orders;
};
```

---

## 5. Migration Checklist

- [ ] Update all `response.orders` to `response.investigation_orders`
- [ ] Add `requisition_type` selector to create requisition form
- [ ] Implement conditional rendering based on `requisition_type`
- [ ] Add medicine/procedure/package item selection UIs
- [ ] Test filter by `requisition_type`
- [ ] Verify existing investigation requisitions still work
