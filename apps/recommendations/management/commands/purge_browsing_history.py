"""Delete browsing-trail rows past their retention window."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.recommendations.models import RecentlyViewed
from apps.recommendations.services import purge_stale_trails
from apps.recommendations.validators import validate_retention_days


class Command(BaseCommand):
    """Enforce the retention policy on recently-viewed rows.

    The trail is a convenience, not a record. Holding a shopper's browsing
    history indefinitely is a data-protection liability that buys the store
    nothing — no rail reads beyond the most recent thirty products.
    """

    help = "Delete browsing history older than the retention window."

    def add_arguments(self, parser: CommandParser) -> None:
        """Expose the window and a dry run."""
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Retention window in days. Default 90.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting it.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Purge, or report what a purge would remove."""
        days: int = options["days"]

        try:
            validate_retention_days(days)
        except ValidationError as exc:
            raise CommandError(exc.messages[0]) from exc

        if options["dry_run"]:
            count = RecentlyViewed.objects.stale(days).count()
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {count} row(s) older than {days} days would be deleted."
                )
            )
            return

        removed = purge_stale_trails(days)
        self.stdout.write(
            self.style.SUCCESS(
                f"Removed {removed} trail row(s) older than {days} days."
            )
        )
