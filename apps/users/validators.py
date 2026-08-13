"""Reusable field validators for the users module.

These are attached to model fields, so they are enforced by
``Model.full_clean()``, by ``ModelForm`` (the admin), and — because DRF copies
model field validators onto the serializer fields it builds — by the API too.
One definition, three enforcement points.
"""

from __future__ import annotations

import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.core.validators import RegexValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

#: Minimum age required to hold an account.
MIN_SIGNUP_AGE_YEARS: int = 13

#: Upper bound used to reject transposed or nonsensical birth dates.
MAX_AGE_YEARS: int = 120

#: E.164-shaped mobile number: optional "+", leading digit 1-9, 8-15 digits total.
mobile_number_validator = RegexValidator(
    regex=r"^\+?[1-9]\d{7,14}$",
    message=_(
        "Enter a valid mobile number in international format, "
        "for example +919876543210."
    ),
    code="invalid_mobile_number",
)


def validate_date_of_birth(value: datetime.date) -> None:
    """Reject future dates, under-age accounts and implausible birth years."""
    today = timezone.localdate()

    if value > today:
        raise ValidationError(
            _("Date of birth cannot be in the future."),
            code="dob_in_future",
        )

    # Subtracting the birthday-not-yet-reached flag avoids the off-by-one that
    # a naive year subtraction produces for people born later in the year.
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))

    if age < MIN_SIGNUP_AGE_YEARS:
        raise ValidationError(
            _("You must be at least %(min_age)d years old to register."),
            code="dob_under_age",
            params={"min_age": MIN_SIGNUP_AGE_YEARS},
        )

    if age > MAX_AGE_YEARS:
        raise ValidationError(
            _("Enter a valid date of birth."),
            code="dob_implausible",
        )


def validate_profile_image(value: File) -> None:
    """Cap profile image size at the project-wide upload ceiling."""
    max_bytes: int = settings.FILE_UPLOAD_MAX_MEMORY_SIZE

    if value.size > max_bytes:
        raise ValidationError(
            _("Image must be %(max_mb).1f MB or smaller."),
            code="image_too_large",
            params={"max_mb": max_bytes / (1024 * 1024)},
        )
