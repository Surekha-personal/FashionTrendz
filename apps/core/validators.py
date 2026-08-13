"""Reusable field validators.

Attach these to model fields. Django enforces them in ``full_clean()`` and in
the admin, and DRF copies model field validators onto the serializer fields it
builds — so one declaration covers the API, the admin and the shell.

Every validator here is either a plain function or a ``@deconstructible`` class.
That matters: Django serialises validators into migration files, and a closure
or a lambda cannot be serialised.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.core.validators import RegexValidator
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

from apps.core.constants import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_FORMATS,
    MAX_DISCOUNT_PERCENT,
    MAX_FILE_SIZE_BYTES,
    MAX_IMAGE_SIZE_BYTES,
    MAX_PRICE,
    MIN_DISCOUNT_PERCENT,
    MIN_PRICE,
    SLUG_REGEX,
)

# ---------------------------------------------------------------------------
# Slugs
# ---------------------------------------------------------------------------

#: Stricter than Django's built-in ``validate_slug``, which accepts uppercase
#: and underscores. URLs are case-sensitive, so "Summer-Dress" and
#: "summer-dress" would be two different pages for the same product.
slug_validator = RegexValidator(
    regex=SLUG_REGEX,
    message=_(
        "Enter a valid slug: lowercase letters, digits and single hyphens, "
        "with no leading or trailing hyphen."
    ),
    code="invalid_slug",
)


# ---------------------------------------------------------------------------
# Files and images
# ---------------------------------------------------------------------------


@deconstructible
class FileSizeValidator:
    """Reject uploads larger than ``max_bytes``."""

    def __init__(self, max_bytes: int = MAX_FILE_SIZE_BYTES) -> None:
        self.max_bytes = max_bytes

    def __call__(self, value: File) -> None:
        """Raise if the uploaded file exceeds the configured ceiling."""
        if value.size > self.max_bytes:
            raise ValidationError(
                _("File must be %(max_mb).1f MB or smaller (this one is %(actual_mb).1f MB)."),
                code="file_too_large",
                params={
                    "max_mb": self.max_bytes / (1024 * 1024),
                    "actual_mb": value.size / (1024 * 1024),
                },
            )

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, FileSizeValidator) and self.max_bytes == other.max_bytes


@deconstructible
class FileExtensionValidator:
    """Reject uploads whose extension is not in ``allowed``."""

    def __init__(self, allowed: tuple[str, ...] = ALLOWED_DOCUMENT_EXTENSIONS) -> None:
        self.allowed = tuple(ext.lower().lstrip(".") for ext in allowed)

    def __call__(self, value: File) -> None:
        """Raise if the filename extension is not permitted."""
        extension = Path(value.name or "").suffix.lower().lstrip(".")
        if extension not in self.allowed:
            raise ValidationError(
                _("Unsupported file type '.%(ext)s'. Allowed types: %(allowed)s."),
                code="invalid_extension",
                params={"ext": extension or "?", "allowed": ", ".join(self.allowed)},
            )

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, FileExtensionValidator) and self.allowed == other.allowed


@deconstructible
class ImageValidator:
    """Validate an uploaded image by size, extension and decoded format.

    The format check is the one that matters. An extension is just the end of a
    filename — anyone can rename ``payload.svg`` to ``photo.png``. Asking Pillow
    what the bytes actually decode to is the only check that cannot be spoofed
    by renaming, and it is why SVG is absent from the allowed formats: SVG is
    XML, it can carry script, and browsers execute it when served inline.
    """

    def __init__(
        self,
        max_bytes: int = MAX_IMAGE_SIZE_BYTES,
        allowed_extensions: tuple[str, ...] = ALLOWED_IMAGE_EXTENSIONS,
        allowed_formats: tuple[str, ...] = ALLOWED_IMAGE_FORMATS,
        min_width: int = 0,
        min_height: int = 0,
    ) -> None:
        self.max_bytes = max_bytes
        self.allowed_extensions = tuple(e.lower().lstrip(".") for e in allowed_extensions)
        self.allowed_formats = tuple(f.upper() for f in allowed_formats)
        self.min_width = min_width
        self.min_height = min_height

    def __call__(self, value: File) -> None:
        """Raise if the upload is too large, wrongly named or not a real image."""
        FileSizeValidator(self.max_bytes)(value)
        FileExtensionValidator(self.allowed_extensions)(value)

        from PIL import Image, UnidentifiedImageError

        position = value.tell() if hasattr(value, "tell") else 0
        try:
            value.seek(0)
            with Image.open(value) as image:
                image_format = (image.format or "").upper()
                width, height = image.size
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValidationError(
                _("This file is not a readable image."),
                code="invalid_image",
            ) from exc
        finally:
            # Leave the file pointer where it was found; the storage backend
            # reads from here next and would otherwise write a truncated file.
            if hasattr(value, "seek"):
                value.seek(position)

        if image_format not in self.allowed_formats:
            raise ValidationError(
                _("Unsupported image format '%(format)s'. Allowed formats: %(allowed)s."),
                code="invalid_image_format",
                params={
                    "format": image_format or "unknown",
                    "allowed": ", ".join(self.allowed_formats),
                },
            )

        if width < self.min_width or height < self.min_height:
            raise ValidationError(
                _("Image must be at least %(w)d x %(h)d pixels (this one is %(aw)d x %(ah)d)."),
                code="image_too_small",
                params={
                    "w": self.min_width,
                    "h": self.min_height,
                    "aw": width,
                    "ah": height,
                },
            )

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, ImageValidator)
            and self.max_bytes == other.max_bytes
            and self.allowed_extensions == other.allowed_extensions
            and self.allowed_formats == other.allowed_formats
            and self.min_width == other.min_width
            and self.min_height == other.min_height
        )


#: Default image validator for catalogue and profile imagery.
validate_image = ImageValidator()

#: Default document validator for invoices and bulk-import spreadsheets.
validate_document = FileExtensionValidator(ALLOWED_DOCUMENT_EXTENSIONS)


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def _as_decimal(value: Any, code: str) -> Decimal:
    """Coerce to Decimal, raising a ValidationError rather than ArithmeticError."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(_("Enter a valid number."), code=code) from exc


def validate_price(value: Any) -> None:
    """Reject negative prices and values beyond the storable maximum.

    Zero is allowed: free gifts and zero-priced samples are legitimate rows.
    A business rule requiring a positive price belongs on the specific field,
    not in the shared validator.
    """
    amount = _as_decimal(value, "invalid_price")

    if amount < MIN_PRICE:
        raise ValidationError(
            _("Price cannot be negative."),
            code="price_negative",
        )

    if amount > MAX_PRICE:
        raise ValidationError(
            _("Price cannot exceed %(max)s."),
            code="price_too_large",
            params={"max": MAX_PRICE},
        )

    if amount.as_tuple().exponent < -2:
        raise ValidationError(
            _("Price cannot have more than 2 decimal places."),
            code="price_precision",
        )


def validate_discount_percentage(value: Any) -> None:
    """Reject discount percentages outside 0-100."""
    percent = _as_decimal(value, "invalid_discount")

    if percent < MIN_DISCOUNT_PERCENT or percent > MAX_DISCOUNT_PERCENT:
        raise ValidationError(
            _("Discount must be between %(min)s and %(max)s percent."),
            code="discount_out_of_range",
            params={"min": MIN_DISCOUNT_PERCENT, "max": MAX_DISCOUNT_PERCENT},
        )


def validate_positive(value: Any) -> None:
    """Reject zero and negative values, for quantities and weights."""
    amount = _as_decimal(value, "invalid_number")
    if amount <= 0:
        raise ValidationError(
            _("Enter a value greater than zero."),
            code="not_positive",
        )


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

#: Loose international postal code: 3-12 alphanumerics, spaces or hyphens.
postal_code_validator = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9\s-]{1,10}[A-Za-z0-9]$",
    message=_("Enter a valid postal code."),
    code="invalid_postal_code",
)

#: Hex colour, used for product swatches.
hex_colour_validator = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$",
    message=_("Enter a colour as a hex code, for example #C0FFEE."),
    code="invalid_hex_colour",
)


def validate_no_html(value: str) -> None:
    """Reject angle brackets in fields rendered as plain text.

    Defence in depth only. Output escaping is the real protection; this stops
    obviously hostile input at the boundary so it never reaches a template that
    someone later marks safe.
    """
    if re.search(r"[<>]", value or ""):
        raise ValidationError(
            _("This field cannot contain the characters < or >."),
            code="html_not_allowed",
        )
