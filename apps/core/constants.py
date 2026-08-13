"""Project-wide scalar constants.

Only plain values live here — numbers, strings, tuples and lookup maps.
Enumerations belong in :mod:`apps.core.choices`. The split is deliberate: this
module imports nothing from the project, so it can be imported from anywhere
(including ``choices``, ``validators`` and ``settings``) without risking a
circular import.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------

PROJECT_NAME: Final[str] = "Fashion Trendz"

# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

DEFAULT_CURRENCY: Final[str] = "INR"

#: Symbol used when formatting an amount for display.
CURRENCY_SYMBOLS: Final[dict[str, str]] = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AED": "د.إ",
}

#: Currencies whose smallest unit is the whole unit (no minor unit).
ZERO_DECIMAL_CURRENCIES: Final[frozenset[str]] = frozenset({"JPY", "KRW"})

# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

#: Matches DecimalField(max_digits=12, decimal_places=2) — up to 9,999,999,999.99.
PRICE_MAX_DIGITS: Final[int] = 12
PRICE_DECIMAL_PLACES: Final[int] = 2

MIN_PRICE: Final[Decimal] = Decimal("0.00")
MAX_PRICE: Final[Decimal] = Decimal("9999999.99")

MIN_DISCOUNT_PERCENT: Final[Decimal] = Decimal("0.00")
MAX_DISCOUNT_PERCENT: Final[Decimal] = Decimal("100.00")

# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

MAX_IMAGE_SIZE_BYTES: Final[int] = 5 * 1024 * 1024
MAX_FILE_SIZE_BYTES: Final[int] = 10 * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS: Final[tuple[str, ...]] = (
    "jpg",
    "jpeg",
    "png",
    "webp",
    "avif",
)
ALLOWED_DOCUMENT_EXTENSIONS: Final[tuple[str, ...]] = ("pdf", "csv", "xlsx")

#: Pillow format names accepted on upload. Checked against the decoded image
#: rather than the filename, so a renamed executable is still rejected.
ALLOWED_IMAGE_FORMATS: Final[tuple[str, ...]] = ("JPEG", "PNG", "WEBP", "AVIF")

#: Longest edge, in pixels, that a stored product or profile image may have.
IMAGE_MAX_DIMENSION_PX: Final[int] = 2000

#: JPEG/WebP quality used by :func:`apps.core.utils.compress_image`.
IMAGE_COMPRESSION_QUALITY: Final[int] = 82

# ---------------------------------------------------------------------------
# Slugs and identifiers
# ---------------------------------------------------------------------------

SLUG_MAX_LENGTH: Final[int] = 255

#: Lowercase letters, digits and single hyphens; no leading or trailing hyphen.
SLUG_REGEX: Final[str] = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

SKU_PREFIX: Final[str] = "FT"
ORDER_NUMBER_PREFIX: Final[str] = "FT-ORD"
INVOICE_NUMBER_PREFIX: Final[str] = "FT-INV"

#: Alphabet for generated identifiers. Excludes I, O, 0 and 1 so a code read
#: aloud from a printed invoice cannot be transcribed ambiguously.
UNAMBIGUOUS_ALPHABET: Final[str] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# ---------------------------------------------------------------------------
# One-time passwords
# ---------------------------------------------------------------------------

OTP_LENGTH: Final[int] = 6
OTP_EXPIRY_SECONDS: Final[int] = 10 * 60
OTP_MAX_ATTEMPTS: Final[int] = 5

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

STANDARD_PAGE_SIZE: Final[int] = 20
STANDARD_MAX_PAGE_SIZE: Final[int] = 100

LARGE_PAGE_SIZE: Final[int] = 100
LARGE_MAX_PAGE_SIZE: Final[int] = 500

ADMIN_PAGE_SIZE: Final[int] = 50
ADMIN_MAX_PAGE_SIZE: Final[int] = 200

PAGE_QUERY_PARAM: Final[str] = "page"
PAGE_SIZE_QUERY_PARAM: Final[str] = "page_size"

# ---------------------------------------------------------------------------
# Request tracing
# ---------------------------------------------------------------------------

REQUEST_ID_HEADER: Final[str] = "X-Request-ID"
RESPONSE_TIME_HEADER: Final[str] = "X-Response-Time-ms"

#: Request body keys that must never reach the log stream.
SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "new_password",
        "confirm_password",
        "current_password",
        "token",
        "refresh",
        "access",
        "authorization",
        "otp",
        "secret",
        "card_number",
        "cvv",
    }
)

#: Replacement written to the log in place of a sensitive value.
REDACTED: Final[str] = "[redacted]"
