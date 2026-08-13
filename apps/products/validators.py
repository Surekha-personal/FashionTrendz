"""Product-specific field validators.

Generic money, slug and image rules come from :mod:`apps.core.validators`;
catalogue image profiles come from :mod:`apps.catalog.validators`. Only rules
with no existing home are defined here.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from apps.core.validators import ImageValidator

#: Product photography: portrait crops, so the height minimum is the binding one.
#: Below 600px tall a zoomed product image is visibly soft, and zoom is the
#: single most-used control on a fashion product page.
validate_product_image = ImageValidator(
    max_bytes=5 * 1024 * 1024,
    min_width=400,
    min_height=600,
)

#: Thumbnails are generated, not uploaded, so the floor is only a sanity check.
validate_thumbnail_image = ImageValidator(
    max_bytes=1 * 1024 * 1024,
    min_width=100,
    min_height=100,
)

#: SKUs are printed on labels and typed into a barcode scanner's fallback keypad.
#: Restricting to uppercase alphanumerics and hyphens keeps them unambiguous.
sku_validator = RegexValidator(
    regex=r"^[A-Z0-9][A-Z0-9-]{2,49}$",
    message=_(
        "Enter a SKU of 3-50 characters using uppercase letters, digits and hyphens."
    ),
    code="invalid_sku",
)

#: EAN-8, EAN-13, UPC-A and ITF-14 all fall inside 8-14 digits.
barcode_validator = RegexValidator(
    regex=r"^\d{8,14}$",
    message=_("Enter a barcode of 8 to 14 digits."),
    code="invalid_barcode",
)

#: "L x W x H" in centimetres, e.g. "30 x 20 x 5".
dimensions_validator = RegexValidator(
    regex=r"^\d+(\.\d+)?\s*x\s*\d+(\.\d+)?\s*x\s*\d+(\.\d+)?$",
    message=_("Enter dimensions as 'L x W x H' in centimetres, e.g. 30 x 20 x 5."),
    code="invalid_dimensions",
)


def validate_rating(value: float) -> None:
    """Reject an average rating outside the 0-5 star range."""
    if value < 0 or value > 5:
        raise ValidationError(
            _("Rating must be between 0 and 5."),
            code="rating_out_of_range",
        )


def validate_stock(value: int) -> None:
    """Reject an implausible stock figure.

    Negative stock is already blocked by ``PositiveIntegerField``; the ceiling
    catches a quantity typed into the wrong column, which would otherwise make
    an out-of-stock product look available.
    """
    if value > 1_000_000:
        raise ValidationError(
            _("Stock cannot exceed 1,000,000 units."),
            code="stock_too_large",
        )
