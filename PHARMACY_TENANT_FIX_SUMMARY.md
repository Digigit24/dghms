# Pharmacy Tenant ID Fix Summary

## Issue
`IntegrityError: null value in column "tenant_id" violates not-null constraint`

This error occurred because the pharmacy cart/order views were creating database objects directly using `.objects.create()` and `.objects.get_or_create()` without passing `tenant_id`.

---

## Root Cause

When you use Django's ORM methods directly (bypassing serializers), you must **explicitly** set `tenant_id`. The `TenantMixin` in serializers only works when objects are created through serializers.

### ❌ WRONG Pattern (Missing tenant_id)
```python
# This bypasses serializer - tenant_id NOT set automatically
cart = Cart.objects.get_or_create(user_id=request.user.id)
```

### ✅ CORRECT Pattern (Explicit tenant_id)
```python
# Explicitly pass tenant_id from request
cart, _ = Cart.objects.get_or_create(
    user_id=request.user_id,
    tenant_id=request.tenant_id,
    defaults={'tenant_id': request.tenant_id}
)
```

---

## Files Fixed

### 1. `apps/pharmacy/views.py`

#### Fixed Methods in `CartViewSet`:
- ✅ `add_item()` - Line 548
- ✅ `update_item()` - Line 624
- ✅ `remove_item()` - Line 665
- ✅ `clear()` - Line 690

#### Fixed Methods in `PharmacyOrderViewSet`:
- ✅ `create()` - Line 740 (Cart lookup)
- ✅ `create()` - Line 789 (Order creation)
- ✅ `create()` - Line 800 (OrderItem creation)

#### Changes Made:

**Before:**
```python
cart, _ = Cart.objects.get_or_create(user_id=request.user.id)
product = PharmacyProduct.objects.get(id=product_id, is_active=True)
cart_item, _ = CartItem.objects.get_or_create(cart=cart, product=product, defaults={...})
order = PharmacyOrder.objects.create(user_id=request.user.id, ...)
PharmacyOrderItem.objects.create(order=order, ...)
```

**After:**
```python
cart, _ = Cart.objects.get_or_create(
    user_id=request.user_id,
    tenant_id=request.tenant_id,
    defaults={'tenant_id': request.tenant_id}
)

product = PharmacyProduct.objects.get(
    id=product_id,
    tenant_id=request.tenant_id,
    is_active=True
)

cart_item, _ = CartItem.objects.get_or_create(
    cart=cart,
    product=product,
    tenant_id=request.tenant_id,
    defaults={'tenant_id': request.tenant_id, ...}
)

order = PharmacyOrder.objects.create(
    tenant_id=request.tenant_id,
    user_id=request.user_id,
    ...
)

PharmacyOrderItem.objects.create(
    tenant_id=request.tenant_id,
    order=order,
    ...
)
```

#### Additional Fixes:
- ✅ Changed `request.user.id` → `request.user_id` (consistent with JWT auth)
- ✅ Added `tenant_id` filter to all `.get()` queries

---

### 2. `apps/pharmacy/serializers.py`

Added `TenantMixin` to all serializers for consistency:

- ✅ `ProductCategorySerializer` - Added `TenantMixin`
- ✅ `PharmacyProductSerializer` - Added `TenantMixin`
- ✅ `CartItemSerializer` - Added `TenantMixin`
- ✅ `CartSerializer` - Added `TenantMixin`
- ✅ `PharmacyOrderItemSerializer` - Added `TenantMixin`
- ✅ `PharmacyOrderSerializer` - Added `TenantMixin`

Added `tenant_id` to `read_only_fields` in all serializers to ensure it's never modified.

---

## Key Learnings

### When to Manually Set tenant_id

You must **manually** set `tenant_id` when using:
1. `.objects.create(**data)`
2. `.objects.get_or_create(**data)`
3. `.objects.update_or_create(**data)`
4. `.objects.filter().update(**data)`

### When tenant_id is Automatic

`tenant_id` is **automatically** set when:
1. Using serializers with `TenantMixin`
2. Using viewsets with `TenantViewSetMixin.perform_create()`

### Best Practices

1. **Always use `request.tenant_id`** - It comes from JWT token
2. **Always use `request.user_id`** - It comes from JWT token (not `request.user.id`)
3. **Add `tenant_id` to filters** - Prevent cross-tenant data leaks
4. **Use `TenantMixin`** - Add to all serializers
5. **Use `TenantViewSetMixin`** - Add to all viewsets

### Checklist for New Models

When creating new models that need tenant isolation:

- [ ] Add `tenant_id = models.UUIDField(db_index=True)`
- [ ] Add `tenant_id` to all indexes
- [ ] Add `TenantMixin` to serializer
- [ ] Add `TenantViewSetMixin` to viewset
- [ ] Add `tenant_id` to `read_only_fields` in serializer
- [ ] If using direct `.objects.create()`, pass `tenant_id=request.tenant_id`
- [ ] If using `.objects.get()`, filter by `tenant_id=request.tenant_id`

---

## Testing

### Manual Test Steps

1. **Test Cart Operations:**
```bash
POST /api/pharmacy/cart/add_item/
{
    "product_id": 1,
    "quantity": 2
}
```

2. **Verify tenant_id in database:**
```sql
SELECT id, tenant_id, user_id FROM pharmacy_carts;
SELECT id, tenant_id, cart_id, product_id FROM pharmacy_cart_items;
```

3. **Test Order Creation:**
```bash
POST /api/pharmacy/orders/
{
    "shipping_address": "123 Main St",
    "billing_address": "123 Main St"
}
```

4. **Verify tenant_id in orders:**
```sql
SELECT id, tenant_id, user_id FROM pharmacy_orders;
SELECT id, tenant_id, order_id FROM pharmacy_order_items;
```

---

## Reference

For more information on DigiHMS tenant architecture, see:
- `CLAUDE.md` - Section "Multi-Tenancy Architecture"
- `common/mixins.py` - TenantMixin and TenantViewSetMixin
- `apps/doctors/views.py` - Line 637 for example of manual tenant_id setting

---

**Status**: ✅ All tenant_id issues resolved
**Date**: 2024-12-24
