"""Shared helper functions.

Pure functions with no Django model dependencies, except
:func:`generate_unique_slug`, which needs a queryset to detect collisions.
"""

from __future__ import annotations

import io
import secrets
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.constants import (
    CURRENCY_SYMBOLS,
    DEFAULT_CURRENCY,
    IMAGE_COMPRESSION_QUALITY,
    IMAGE_MAX_DIMENSION_PX,
    INVOICE_NUMBER_PREFIX,
    ORDER_NUMBER_PREFIX,
    OTP_LENGTH,
    REDACTED,
    SENSITIVE_KEYS,
    SKU_PREFIX,
    SLUG_MAX_LENGTH,
    UNAMBIGUOUS_ALPHABET,
    ZERO_DECIMAL_CURRENCIES,
)

# ---------------------------------------------------------------------------
# Slugs
# ---------------------------------------------------------------------------


def generate_unique_slug(
    model: type[models.Model],
    value: str,
    *,
    slug_field: str = "slug",
    instance_pk: Any = None,
    max_length: int = SLUG_MAX_LENGTH,
) -> str:
    """Return a slug for ``value`` that no other row of ``model`` holds.

    On collision a short random suffix is appended rather than an incrementing
    counter. A counter requires reading the highest existing value, which two
    concurrent writers can read identically before either commits; a random
    suffix has no such read-then-write window.

    ``instance_pk`` excludes the row being updated, so re-saving a record does
    not treat its own slug as a conflict.
    """
    base = slugify(value)[:max_length].strip("-")
    if not base:
        # slugify() empties strings that are entirely non-ASCII, e.g. "साड़ी".
        base = f"item-{secrets.token_hex(4)}"

    queryset = model._default_manager.all()
    if instance_pk is not None:
        queryset = queryset.exclude(pk=instance_pk)

    candidate = base
    while queryset.filter(**{slug_field: candidate}).exists():
        suffix = secrets.token_hex(3)
        candidate = f"{base[: max_length - len(suffix) - 1]}-{suffix}"

    return candidate


# ---------------------------------------------------------------------------
# Identifier generation
# ---------------------------------------------------------------------------


def _random_code(length: int, alphabet: str = UNAMBIGUOUS_ALPHABET) -> str:
    """Return a cryptographically random code drawn from ``alphabet``."""
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_sku(prefix: str = SKU_PREFIX, length: int = 8) -> str:
    """Return a stock keeping unit such as ``FT-K7M2P9QX``.

    Random rather than sequential: a sequential SKU tells a competitor exactly
    how many products the catalogue holds and how fast it grows.

    Uniqueness is not guaranteed here. Pair the field with
    ``unique=True`` and retry on ``IntegrityError`` — the database is the only
    place a uniqueness claim can actually be enforced under concurrency.
    """
    return f"{prefix}-{_random_code(length)}"


def generate_order_number(now: datetime | None = None) -> str:
    """Return an order number such as ``FT-ORD-20260804-7QK2M9``.

    The date segment makes a number human-sortable and lets support staff scope
    a database lookup to one day. The random tail keeps daily volume private.
    """
    moment = now or timezone.now()
    return f"{ORDER_NUMBER_PREFIX}-{moment:%Y%m%d}-{_random_code(6)}"


def generate_invoice_number(now: datetime | None = None) -> str:
    """Return an invoice number such as ``FT-INV-202608-3XP7K2``.

    Scoped to the month rather than the day, matching how invoices are filed
    for accounting periods.
    """
    moment = now or timezone.now()
    return f"{INVOICE_NUMBER_PREFIX}-{moment:%Y%m}-{_random_code(6)}"


def generate_otp(length: int = OTP_LENGTH) -> str:
    """Return a numeric one-time password, zero-padded to ``length``.

    Uses :mod:`secrets`, not :mod:`random`. ``random`` is a Mersenne Twister
    seeded from the clock: observing a handful of outputs is enough to predict
    every subsequent one, which for an OTP means predicting the next code sent
    to someone else's phone.
    """
    if length < 1:
        raise ValueError("OTP length must be at least 1.")
    upper_bound = 10**length
    return str(secrets.randbelow(upper_bound)).zfill(length)


def generate_reference(prefix: str, length: int = 10) -> str:
    """Return a generic prefixed reference for payments, returns or tickets."""
    return f"{prefix}-{_random_code(length)}"


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def quantise_money(amount: Any, currency: str = DEFAULT_CURRENCY) -> Decimal:
    """Round ``amount`` to the currency's minor unit using banker's-safe rounding.

    ``ROUND_HALF_UP`` matches what an invoice reader expects. Python's default
    ``ROUND_HALF_EVEN`` turns 0.125 into 0.12, which is defensible statistically
    and indefensible on a receipt.
    """
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Cannot interpret {amount!r} as a monetary amount.") from exc

    places = Decimal("1") if currency.upper() in ZERO_DECIMAL_CURRENCIES else Decimal("0.01")
    return value.quantize(places, rounding=ROUND_HALF_UP)


def format_currency(amount: Any, currency: str = DEFAULT_CURRENCY) -> str:
    """Return a display string such as ``₹1,299.00``.

    Thousands separators are applied with Python's own formatting rather than
    :mod:`locale`. ``locale.setlocale`` mutates process-global state and is not
    thread-safe, so under gunicorn one request can change another's number
    format mid-flight.
    """
    value = quantise_money(amount, currency)
    symbol = CURRENCY_SYMBOLS.get(currency.upper(), f"{currency.upper()} ")
    places = 0 if currency.upper() in ZERO_DECIMAL_CURRENCIES else 2
    return f"{symbol}{value:,.{places}f}"


def calculate_discounted_price(
    price: Any,
    discount_percent: Any,
    currency: str = DEFAULT_CURRENCY,
) -> Decimal:
    """Return ``price`` reduced by ``discount_percent``, rounded to the minor unit."""
    base = Decimal(str(price))
    percent = Decimal(str(discount_percent))
    return quantise_money(base * (Decimal("100") - percent) / Decimal("100"), currency)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


def compress_image(
    image_file: Any,
    *,
    max_dimension: int = IMAGE_MAX_DIMENSION_PX,
    quality: int = IMAGE_COMPRESSION_QUALITY,
    to_format: str = "WEBP",
) -> ContentFile:
    """Downscale and re-encode an uploaded image, returning a new file.

    A phone camera produces 4000px, 6 MB JPEGs; a product grid displays them at
    400px. Storing the original means every listing page ships tens of megabytes.
    Re-encoding on upload is a one-time cost that every subsequent page load
    benefits from.

    Aspect ratio is preserved and images already within ``max_dimension`` are
    only re-encoded, never upscaled.
    """
    from PIL import Image

    if hasattr(image_file, "seek"):
        image_file.seek(0)

    with Image.open(image_file) as source:
        image = source.convert("RGB") if source.mode in ("RGBA", "P", "LA") else source.copy()
        image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format=to_format, quality=quality, optimize=True)

    stem = Path(getattr(image_file, "name", "image")).stem
    return ContentFile(buffer.getvalue(), name=f"{stem}.{to_format.lower()}")


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


def redact(payload: Any) -> Any:
    """Return a copy of ``payload`` with sensitive values replaced.

    Applied before anything derived from a request body reaches the log stream.
    Passwords and tokens in logs are a breach waiting for a log aggregator with
    looser access control than the database.
    """
    if isinstance(payload, dict):
        return {
            key: REDACTED if str(key).lower() in SENSITIVE_KEYS else redact(value)
            for key, value in payload.items()
        }
    if isinstance(payload, (list, tuple)):
        return [redact(item) for item in payload]
    return payload


def client_ip(request: Any) -> str:
    """Return the originating client IP, honouring a trusted proxy header.

    ``X-Forwarded-For`` is client-supplied and trivially spoofed. It is only
    read when ``SECURE_PROXY_SSL_HEADER`` is configured, which is this project's
    signal that a trusted proxy is in front and is rewriting the header.
    """
    from django.conf import settings

    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR", "") or "unknown"
