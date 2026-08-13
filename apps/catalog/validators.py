"""Catalog-specific field validators.

Generic validators (image, slug, price, discount) live in
:mod:`apps.core.validators` and are imported directly by the models. Only rules
that are specific to catalogue data are defined here.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.validators import ImageValidator

#: Earliest plausible founding year for a fashion house. Guards against a
#: transposed digit ("1092") landing in the database and breaking any
#: chronological sort or "heritage brand" filter built on the column.
EARLIEST_FOUNDED_YEAR: int = 1600


def validate_founded_year(value: int) -> None:
    """Reject founding years that are impossible or in the future."""
    current_year = timezone.localdate().year

    if value < EARLIEST_FOUNDED_YEAR:
        raise ValidationError(
            _("Enter a founding year of %(earliest)d or later."),
            code="founded_year_too_early",
            params={"earliest": EARLIEST_FOUNDED_YEAR},
        )

    if value > current_year:
        raise ValidationError(
            _("A founding year cannot be in the future."),
            code="founded_year_in_future",
        )


#: Category and brand icons: small, square-ish artwork shown in the mega menu.
#: The minimum stops a 16px favicon being uploaded as a menu tile and rendering
#: as a blurred smear on a retina display.
validate_icon_image = ImageValidator(
    max_bytes=1 * 1024 * 1024,
    min_width=64,
    min_height=64,
)

#: Tile artwork for category cards and brand logos.
validate_tile_image = ImageValidator(
    max_bytes=2 * 1024 * 1024,
    min_width=200,
    min_height=200,
)

#: Full-width hero artwork. Anything narrower than 1200px is upscaled by the
#: browser on a desktop hero slot, which looks worse than no banner at all.
validate_banner_image = ImageValidator(
    max_bytes=4 * 1024 * 1024,
    min_width=1200,
    min_height=300,
)


def validate_display_order(value: int) -> None:
    """Keep manual ordering within a range an editor can reason about."""
    if value > 9999:
        raise ValidationError(
            _("Display order must be 9999 or lower."),
            code="display_order_too_large",
        )


def validate_not_future_date(value: datetime.date) -> None:
    """Reject a date in the future, for publication timestamps."""
    if value > timezone.localdate():
        raise ValidationError(
            _("This date cannot be in the future."),
            code="date_in_future",
        )
