"""IPD billing-mode + advance-payment helpers.

Shared by ``AdmissionViewSet`` (billing_capabilities/record_advance/
apply_advance) and ``IPDBillingViewSet.create`` (the single_accumulated 409
guard) so "what counts as an active bill" and "which billing mode is this
tenant in" live in exactly one place instead of being re-derived per call
site.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction

# Not yet hospital-configurable — a fixed backend constant per the spec.
DEFAULT_ADVANCE_RECOMMEND_THRESHOLD = Decimal('5000.00')


def get_ipd_billing_mode(tenant_id) -> str:
    """Tenant-scoped ``Hospital.ipd_billing_mode``, defaulting to 'multiple'."""
    from apps.hospital.models import Hospital

    return (
        Hospital.objects.filter(tenant_id=tenant_id)
        .values_list('ipd_billing_mode', flat=True)
        .first()
        or 'multiple'
    )


def active_bill_queryset(admission):
    """Non-mediclaim IPDBilling rows for this admission, most recent first."""
    from apps.ipd.models import IPDBilling

    return (
        IPDBilling.objects.filter(admission=admission)
        .exclude(bill_type='mediclaim')
        .order_by('-bill_date', '-id')
    )


def get_active_bill_id(admission) -> Optional[int]:
    """Most recently created non-mediclaim bill for the admission, if any.

    "Active" means "exists" here, not "unpaid" — a single_accumulated bill
    routinely reaches payment_status=='paid' mid-stay (see
    IPDBillItemViewSet's paid-lock fix) and must still be treated as the
    admission's one accumulated bill afterwards, not superseded by a second
    bill. Reads the ``_active_bill_id`` annotation set by
    AdmissionViewSet.get_queryset() when present (avoids an extra query per
    row on the list endpoint); falls back to a direct query otherwise (e.g.
    an Admission instantiated outside that queryset, as in tests).
    """
    if hasattr(admission, '_active_bill_id'):
        return admission._active_bill_id
    return active_bill_queryset(admission).values_list('id', flat=True).first()


def has_active_non_mediclaim_bill(tenant_id, admission_id) -> bool:
    """Used by IPDBillingViewSet.create()'s single_accumulated 409 guard."""
    from apps.ipd.models import IPDBilling

    return IPDBilling.objects.filter(
        tenant_id=tenant_id, admission_id=admission_id
    ).exclude(bill_type='mediclaim').exists()


def build_billing_capabilities(admission, mode: Optional[str] = None) -> dict:
    """Build the ``billing_capabilities`` payload for one Admission.

    Reads the six rollup fields directly off ``admission`` (kept in sync by
    Admission.recompute_billing_rollup() via signals) rather than
    re-aggregating on every read — this is what keeps the Admission list
    endpoint N+1-free.
    """
    if mode is None:
        mode = get_ipd_billing_mode(admission.tenant_id)

    active_bill_id = get_active_bill_id(admission)
    can_create_new_bill = not (
        (mode == 'single_accumulated' and active_bill_id is not None)
        or admission.status == 'discharged'
    )

    balance_due = admission.balance_due or Decimal('0.00')
    advance_balance = admission.advance_balance or Decimal('0.00')
    advance_recommended = (
        balance_due > DEFAULT_ADVANCE_RECOMMEND_THRESHOLD
        and advance_balance == Decimal('0.00')
    )

    return {
        'mode': mode,
        'can_create_new_bill': can_create_new_bill,
        'active_bill_id': active_bill_id,
        'total_charges': str(admission.total_charges or Decimal('0.00')),
        'total_advance_paid': str(admission.total_advance_paid or Decimal('0.00')),
        'advance_applied': str(admission.advance_applied or Decimal('0.00')),
        'advance_balance': str(advance_balance),
        'total_received': str(admission.total_received or Decimal('0.00')),
        'balance_due': str(balance_due),
        'advance_recommended': advance_recommended,
    }


class AdvanceApplyError(Exception):
    """Raised by apply_advance_to_bill(); carries a stable error_code + HTTP status."""

    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def apply_advance_to_bill(admission, bill, requested_amount=None):
    """Move advance money from the admission's advance pool onto ``bill``.

    ``requested_amount`` of None means "apply the full remaining advance
    balance, capped at the bill's remaining balance" per the contract.
    Consumes the admission's 'advance' BillPayment rows oldest-first
    (FIFO), incrementing each row's applied_amount up to its own amount, so
    advance_applied (the sum of those applied_amount values) can never
    exceed total_advance_paid (the sum of their amount values) by
    construction. Returns the updated, refreshed bill.
    """
    from apps.payments.models import BillPayment
    from apps.ipd.models import IPDBilling

    if bill.admission_id != admission.id:
        raise AdvanceApplyError('BILL_NOT_FOUND', 'Bill does not belong to this admission.', status=404)
    if bill.bill_type == 'mediclaim':
        raise AdvanceApplyError(
            'INVALID_APPLY_AMOUNT', 'Advance cannot be applied to a Mediclaim bill.', status=400
        )

    with transaction.atomic():
        # Lock the bill row FIRST, before reading/validating against its
        # received_amount. Without this, two concurrent apply_advance calls
        # (or apply_advance racing IPDBillingViewSet.add_payment) on the
        # SAME bill can lost-update each other: both read the pre-update
        # received_amount, both compute their own delta from that stale
        # value, and whichever transaction commits last silently overwrites
        # the other's contribution instead of the two amounts summing.
        # select_for_update() here serializes against ANY concurrent writer
        # of this row (Postgres row locks apply to plain UPDATEs too, not
        # just other SELECT ... FOR UPDATE readers), matching the pattern
        # already used below for the advance BillPayment rows.
        bill = IPDBilling.objects.select_for_update().get(pk=bill.pk)

        admission.recompute_billing_rollup()
        advance_balance = admission.advance_balance
        bill_remaining = bill.payable_amount - bill.received_amount

        if requested_amount in (None, ''):
            amount = min(advance_balance, bill_remaining)
        else:
            try:
                amount = Decimal(str(requested_amount))
            except Exception:
                raise AdvanceApplyError('INVALID_APPLY_AMOUNT', "'amount' must be a number.", status=400)
            if amount <= Decimal('0.00'):
                raise AdvanceApplyError(
                    'INVALID_APPLY_AMOUNT', "'amount' must be greater than zero.", status=400
                )
            if amount > advance_balance:
                raise AdvanceApplyError(
                    'ADVANCE_EXCEEDS_BALANCE',
                    f'Requested amount exceeds the available advance balance ({advance_balance}).',
                    status=400,
                )
            if amount > bill_remaining:
                raise AdvanceApplyError(
                    'INVALID_APPLY_AMOUNT',
                    f"Requested amount exceeds the bill's remaining balance ({bill_remaining}).",
                    status=400,
                )

        if amount <= Decimal('0.00'):
            raise AdvanceApplyError(
                'INVALID_APPLY_AMOUNT', 'No advance balance available to apply.', status=400
            )

        remaining_to_apply = amount
        advance_rows = (
            BillPayment.objects.select_for_update()
            .filter(tenant_id=admission.tenant_id, bill_type='advance', admission=admission)
            .order_by('created_at', 'id')
        )
        for row in advance_rows:
            if remaining_to_apply <= Decimal('0.00'):
                break
            row_available = row.amount - row.applied_amount
            if row_available <= Decimal('0.00'):
                continue
            take = min(row_available, remaining_to_apply)
            row.applied_amount += take
            row.save(update_fields=['applied_amount'])
            remaining_to_apply -= take

        if remaining_to_apply > Decimal('0.00'):
            # Shouldn't happen given the advance_balance check above, but
            # guard against a concurrent apply_advance racing this one.
            raise AdvanceApplyError(
                'ADVANCE_EXCEEDS_BALANCE',
                'Insufficient advance balance to cover the requested amount.',
                status=400,
            )

        bill.record_payment(
            amount,
            mode=bill.payment_mode or 'cash',
            details={**(bill.payment_details or {}), 'advance_applied': str(amount)},
        )
        admission.recompute_billing_rollup()

    bill.refresh_from_db()
    return bill
