"""Shared parsing for the "record a payment" request body.

Used by both apps.opd.views.OPDBillViewSet.record_payment and
apps.ipd.views.AdmissionBillingViewSet.add_payment so a "Cash + Online" split
payment is parsed identically (and lands in the BillPayment ledger
identically) regardless of which bill type it was recorded against.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

SPLIT_PAYMENT_MODE = "cash_online"


class PaymentEntryError(ValueError):
    """Raised when the request body cannot be parsed into payment entries."""


def _to_decimal(raw, field_name: str) -> Decimal:
    if raw in (None, ""):
        return Decimal("0.00")
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise PaymentEntryError(f"'{field_name}' must be a number.")
    if value < 0:
        raise PaymentEntryError(f"'{field_name}' cannot be negative.")
    return value


def parse_payment_entries(data: dict, payment_mode: str) -> list[tuple[str, Decimal]]:
    """Parse the request body into a list of ``(mode, amount)`` ledger entries.

    - Plain modes (``cash``, ``card``, ``upi``, ...) read a single ``amount``.
    - ``cash_online`` reads ``cash_amount``/``online_amount`` and produces up
      to two entries — whichever of the two the caller actually collected.
      Both fields are independently editable on the frontend (the UI
      auto-balances one against the other but does not force the sum to
      equal any particular total), so the only server-side rule is that at
      least one of them is a positive amount.
    """
    if payment_mode == SPLIT_PAYMENT_MODE:
        cash_amount = _to_decimal(data.get("cash_amount"), "cash_amount")
        online_amount = _to_decimal(data.get("online_amount"), "online_amount")
        entries = []
        if cash_amount > 0:
            entries.append(("cash", cash_amount))
        if online_amount > 0:
            entries.append(("online", online_amount))
        if not entries:
            raise PaymentEntryError(
                "At least one of 'cash_amount' or 'online_amount' must be greater than 0."
            )
        return entries

    amount = data.get("amount")
    if not amount:
        raise PaymentEntryError("Amount is required.")
    value = _to_decimal(amount, "amount")
    if value <= 0:
        raise PaymentEntryError("Amount must be greater than 0.")
    return [(payment_mode, value)]


def total_amount(entries: list[tuple[str, Decimal]]) -> Decimal:
    total = Decimal("0.00")
    for _, amount in entries:
        total += amount
    return total
