"""Coupon-specific validators."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

#: Coupon codes are printed on banners, read aloud in ads and typed by hand.
#: Restricting to uppercase alphanumerics and hyphens keeps them unambiguous —
#: the code the customer types is always the code the campaign advertised.
coupon_code_validator = RegexValidator(
    regex=r"^[A-Z0-9][A-Z0-9-]{2,39}$",
    message=_(
        "Enter a code of 3-40 characters using uppercase letters, digits and hyphens."
    ),
    code="invalid_coupon_code",
)


def validate_percentage(value: Decimal) -> None:
    """Reject a percentage outside 0-100."""
    if value < Decimal("0") or value > Decimal("100"):
        raise ValidationError(
            _("A percentage discount must be between 0 and 100."),
            code="percentage_out_of_range",
        )


def validate_positive_amount(value: Decimal) -> None:
    """Reject a zero or negative discount amount."""
    if value <= Decimal("0"):
        raise ValidationError(
            _("Enter a discount greater than zero."), code="amount_not_positive"
        )
