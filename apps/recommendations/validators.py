"""Validators for the recommendations module.

Small surface. The module writes exactly one thing a client can influence — a
row in the browsing trail — so these guard the two numbers that arrive from
query strings.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

#: Largest rail a client may request. Without a ceiling, ``?limit=100000`` on a
#: cached, scored endpoint is a cheap way to make the store do expensive work.
MAX_RAIL_LIMIT: int = 50

#: Longest retention window the cleanup command accepts, in days. Two years of
#: browsing history is already well past what any rail reads.
MAX_RETENTION_DAYS: int = 730


def validate_rail_limit(value: int) -> None:
    """Reject a rail size outside the sane range."""
    if value < 1 or value > MAX_RAIL_LIMIT:
        raise ValidationError(
            _("Ask for between 1 and %(maximum)d products."),
            code="rail_limit_out_of_range",
            params={"maximum": MAX_RAIL_LIMIT},
        )


def validate_retention_days(value: int) -> None:
    """Reject a retention window that is negative or absurdly long."""
    if value < 1 or value > MAX_RETENTION_DAYS:
        raise ValidationError(
            _("Retention must be between 1 and %(maximum)d days."),
            code="retention_out_of_range",
            params={"maximum": MAX_RETENTION_DAYS},
        )


def clamp_limit(value: object, default: int) -> int:
    """Return a usable rail size from untrusted query-string input.

    Clamps rather than raises. A shopper who lands on a page with a mangled
    ``?limit=`` should see a normal rail, not a validation error — the
    parameter is a hint, not a request the page depends on.
    """
    try:
        limit = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, MAX_RAIL_LIMIT))


#: Longest window the "recently popular" rail will look back over. A year is
#: already past the point where "recently" means anything.
MAX_POPULARITY_DAYS: int = 365


def clamp_days(value: object, default: int) -> int:
    """Return a usable look-back window from untrusted query-string input.

    Separate from :func:`clamp_limit` because the two clamp to different
    ceilings — sharing one would silently cap a 90-day window at 50 days.
    """
    try:
        days = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(1, min(days, MAX_POPULARITY_DAYS))
