"""Rebuild the co-purchase graph from order history."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.recommendations.services import rebuild_affinities


class Command(BaseCommand):
    """Recompute every "frequently bought together" edge.

    Meant for a nightly cron. Order history changes slowly enough that hourly
    would be waste, and a graph a day old recommends the same bundles a fresh
    one would.
    """

    help = "Rebuild the product co-purchase graph from order history."

    def add_arguments(self, parser: CommandParser) -> None:
        """Expose the noise floor as a flag."""
        parser.add_argument(
            "--minimum",
            type=int,
            default=2,
            help=(
                "Orders a pair must share before it becomes an edge. "
                "Below 2, one customer's coincidence becomes a recommendation."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the rebuild and report what it produced."""
        result = rebuild_affinities(minimum=options["minimum"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Built {result['edges']} affinity edge(s) "
                f"from {result['baskets']} order(s)."
            )
        )

        if result["edges"] == 0:
            self.stdout.write(
                self.style.WARNING(
                    "No edges met the threshold. The 'frequently bought together' "
                    "rail will stay empty until more orders share products."
                )
            )
