"""Review-specific validators."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.core.validators import ImageValidator

#: Review photographs. Smaller ceiling than catalogue imagery because these
#: come from phones in bulk and nobody zooms into a customer snapshot.
validate_review_image = ImageValidator(
    max_bytes=3 * 1024 * 1024,
    min_width=200,
    min_height=200,
)

#: Longest a review body may be. Long enough for a considered write-up, short
#: enough that the field cannot be used as free blog hosting.
MAX_REVIEW_LENGTH: int = 5000

#: Shortest useful review. Below this it is a rating with noise attached, and
#: it dilutes the review list without telling the next shopper anything.
MIN_REVIEW_LENGTH: int = 10


def validate_review_body(value: str) -> None:
    """Reject a review that is too short, or that is only punctuation."""
    text = (value or "").strip()

    if len(text) < MIN_REVIEW_LENGTH:
        raise ValidationError(
            _("Please write at least %(minimum)d characters."),
            code="review_too_short",
            params={"minimum": MIN_REVIEW_LENGTH},
        )

    if not re.search(r"[A-Za-zऀ-ॿ]", text):
        # Devanagari included: a review in Hindi is a real review.
        raise ValidationError(
            _("Please write a few words about the product."),
            code="review_no_words",
        )


def validate_no_contact_details(value: str) -> None:
    """Reject reviews carrying an email address or phone number.

    Two reasons, both real. Customers paste their own number expecting support
    to call, which publishes it to the whole internet. And sellers use the
    field to route buyers to an off-platform channel.
    """
    text = value or ""

    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text):
        raise ValidationError(
            _("Please do not include email addresses in a review."),
            code="review_contains_email",
        )

    if re.search(r"(?:\+?\d[\d\s-]{8,}\d)", text):
        raise ValidationError(
            _("Please do not include phone numbers in a review."),
            code="review_contains_phone",
        )


def validate_rating(value: int) -> None:
    """Reject a rating outside one to five stars."""
    if value < 1 or value > 5:
        raise ValidationError(
            _("A rating must be between 1 and 5 stars."), code="rating_out_of_range"
        )
