"""Validators for the analytics module.

Analytics endpoints take dates and window lengths from the query string and
feed them straight into aggregates over the orders table. Both need bounding:
an unbounded window is a full scan, and an unparseable date should produce a
normal dashboard rather than a 500.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _

#: Longest window an analytics endpoint will look back over. A year of daily
#: rows is already more than any chart renders legibly.
MAX_WINDOW_DAYS: int = 365


def validate_window_days(value: int) -> None:
    """Reject a window length outside the sane range."""
    if value < 1 or value > MAX_WINDOW_DAYS:
        raise ValidationError(
            _("Choose a window between 1 and %(maximum)d days."),
            code="window_out_of_range",
            params={"maximum": MAX_WINDOW_DAYS},
        )


def clamp_days(value: Any, default: int) -> int:
    """Return a usable window length from untrusted query-string input.

    Clamps rather than raises. An admin who lands on a bookmarked URL with a
    stale parameter should see a dashboard, not an error page.
    """
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(days, MAX_WINDOW_DAYS))


def parse_window(
    start: Any, end: Any, *, default_days: int = 30
) -> tuple[datetime, datetime]:
    """Resolve ``start``/``end`` query parameters into an aware datetime pair.

    Falls back to the last ``default_days`` when either bound is missing or
    unparseable. ``end`` is pushed to the end of its day so an inclusive date
    range behaves the way the person typing it expects — asking for
    ``end=2026-08-04`` and losing that day's orders is the classic off-by-one
    in every reporting tool.

    A reversed pair is swapped rather than rejected, because it is obvious what
    was meant.
    """
    now = timezone.now()
    parsed_start = parse_date(str(start)) if start else None
    parsed_end = parse_date(str(end)) if end else None

    if not parsed_start or not parsed_end:
        return now - timedelta(days=default_days), now

    if parsed_start > parsed_end:
        parsed_start, parsed_end = parsed_end, parsed_start

    window_start = timezone.make_aware(
        datetime.combine(parsed_start, datetime.min.time()),
        timezone.get_current_timezone(),
    )
    window_end = timezone.make_aware(
        datetime.combine(parsed_end, datetime.max.time()),
        timezone.get_current_timezone(),
    )

    # Cap the span, so a hand-typed 2019 start date does not scan the table.
    if (window_end - window_start).days > MAX_WINDOW_DAYS:
        window_start = window_end - timedelta(days=MAX_WINDOW_DAYS)

    return window_start, window_end
