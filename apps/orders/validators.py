"""Order-specific validators and the status state machine.

The transition table is the important part. Order status is the most
consequential field in the system — it drives refunds, courier handoff and
customer email — so which moves are legal is declared once, here, rather than
being implied by scattered ``if`` statements in views and admin actions.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from apps.core.choices import TERMINAL_ORDER_STATUSES, OrderStatus

#: Legal forward moves. Anything not listed is rejected.
#:
#: Read it as "from this status, you may move to one of these". Terminal states
#: map to the empty set: a delivered order does not go back to shipped, and a
#: refunded one does not reopen. Reversals happen through a new record — a
#: return or a replacement order — never by rewinding this field, because
#: rewinding destroys the audit trail the finance team reconciles against.
ORDER_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED}),
    OrderStatus.CONFIRMED: frozenset({OrderStatus.PROCESSING, OrderStatus.CANCELLED}),
    OrderStatus.PROCESSING: frozenset({OrderStatus.PACKED, OrderStatus.CANCELLED}),
    OrderStatus.PACKED: frozenset({OrderStatus.SHIPPED, OrderStatus.CANCELLED}),
    OrderStatus.SHIPPED: frozenset(
        {OrderStatus.OUT_FOR_DELIVERY, OrderStatus.RETURNED}
    ),
    OrderStatus.OUT_FOR_DELIVERY: frozenset(
        {OrderStatus.DELIVERED, OrderStatus.RETURNED}
    ),
    OrderStatus.DELIVERED: frozenset({OrderStatus.RETURNED}),
    OrderStatus.RETURNED: frozenset({OrderStatus.REFUNDED}),
    OrderStatus.CANCELLED: frozenset({OrderStatus.REFUNDED}),
    OrderStatus.REFUNDED: frozenset(),
}


def can_transition(current: str, target: str) -> bool:
    """Return whether moving from ``current`` to ``target`` is legal."""
    return target in ORDER_STATUS_TRANSITIONS.get(current, frozenset())


def assert_transition(current: str, target: str) -> None:
    """Raise unless the move is legal."""
    if current == target:
        raise ValidationError(
            _("The order is already %(status)s."),
            code="status_unchanged",
            params={"status": current},
        )

    if not can_transition(current, target):
        raise ValidationError(
            _("An order cannot move from %(current)s to %(target)s."),
            code="illegal_status_transition",
            params={"current": current, "target": target},
        )


def is_terminal(status: str) -> bool:
    """Return whether an order in ``status`` can still change."""
    return status in TERMINAL_ORDER_STATUSES


#: ``FT-ORD-20260804-7QK2M9`` — the shape produced by
#: :func:`apps.core.utils.generate_order_number`.
order_number_validator = RegexValidator(
    regex=r"^FT-ORD-\d{8}-[A-Z0-9]{6}$",
    message=_("Enter a valid order number, e.g. FT-ORD-20260804-7QK2M9."),
    code="invalid_order_number",
)

#: ``FT-INV-202608-3XP7K2``.
invoice_number_validator = RegexValidator(
    regex=r"^FT-INV-\d{6}-[A-Z0-9]{6}$",
    message=_("Enter a valid invoice number, e.g. FT-INV-202608-3XP7K2."),
    code="invalid_invoice_number",
)

#: Courier tracking numbers vary wildly between carriers, so this only rejects
#: obviously wrong input rather than pretending to know every format.
tracking_number_validator = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9\-]{5,39}$",
    message=_("Enter a tracking number of 6 to 40 alphanumeric characters."),
    code="invalid_tracking_number",
)


def validate_address_snapshot(value: dict) -> None:
    """Reject an address snapshot missing a field the courier needs.

    Snapshots are JSON rather than a foreign key, so nothing but this check
    stands between a malformed write and an undeliverable parcel.
    """
    if not isinstance(value, dict):
        raise ValidationError(
            _("An address snapshot must be an object."), code="invalid_address"
        )

    required = ("full_name", "mobile", "address_line_1", "city", "state", "postal_code")
    missing = [field for field in required if not str(value.get(field, "")).strip()]

    if missing:
        raise ValidationError(
            _("The address is missing: %(fields)s."),
            code="incomplete_address",
            params={"fields": ", ".join(missing)},
        )


def validate_cancel_reason(value: str) -> None:
    """Require a cancellation reason long enough to be useful.

    One-word reasons ("no", "x") make the cancellation report worthless, and
    that report is how a merchandiser finds out a size chart is wrong.
    """
    if len(value.strip()) < 5:
        raise ValidationError(
            _("Please give a reason of at least 5 characters."),
            code="cancel_reason_too_short",
        )
