"""Payment-specific validators."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

#: Gateway identifiers (``pay_XXXX``, ``order_XXXX``, ``rfnd_XXXX``) are opaque
#: strings whose format is the provider's business. This only rejects input
#: that is obviously not an identifier at all.
gateway_id_validator = RegexValidator(
    regex=r"^[A-Za-z0-9_\-]{6,100}$",
    message=_("Enter a valid gateway identifier."),
    code="invalid_gateway_id",
)


def validate_positive_amount(value: Decimal) -> None:
    """Reject a zero or negative payment amount.

    A zero-value payment row is either a bug or an attempt to mark an order
    paid for nothing, and both should stop here.
    """
    if value <= Decimal("0"):
        raise ValidationError(
            _("A payment amount must be greater than zero."),
            code="amount_not_positive",
        )


def validate_refund_amount(amount: Decimal, payment_amount: Decimal, already: Decimal) -> None:
    """Raise unless a refund of ``amount`` still fits inside the payment.

    Over-refunding is the one payment mistake with no automatic recovery: the
    money is gone, the gateway will not claw it back, and the only remedy is
    asking the customer to return it. The arithmetic is therefore checked here
    *and* backed by a database constraint.
    """
    if amount <= Decimal("0"):
        raise ValidationError(
            _("A refund must be greater than zero."), code="refund_not_positive"
        )

    remaining = payment_amount - already
    if amount > remaining:
        raise ValidationError(
            _("Only %(remaining)s remains refundable on this payment."),
            code="refund_exceeds_payment",
            params={"remaining": remaining},
        )
