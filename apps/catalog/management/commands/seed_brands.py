"""Seed exactly N brands.

A focused companion to ``seed_catalog``, which seeds fifty. The brand list is
imported from that command rather than duplicated, so there is one definition
of the brand roster and no chance of the two drifting.

Idempotent: re-running updates rather than duplicating, which matters because
products reference brands with ON DELETE PROTECT.
"""

from __future__ import annotations

import random
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.catalog.management.commands.seed_catalog import BRANDS
from apps.catalog.models import Brand, Category


class Command(BaseCommand):
    """Create or update brand records."""

    help = "Seed brands (15 by default)."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--count",
            type=int,
            default=15,
            help="How many brands to seed. Default 15; maximum %d." % len(BRANDS),
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=20260804,
            help="Random seed for popularity scores, for reproducibility.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed brands, rolling back entirely on any error."""
        verbosity = options.get("verbosity", 1)
        # Deterministic popularity: a re-run must not reshuffle the "popular
        # brands" rail, which would make the homepage look unstable.
        rng = random.Random(options["seed"])

        wanted = max(1, min(options["count"], len(BRANDS)))
        specs = BRANDS[:wanted]

        by_name = {category.name: category for category in Category.objects.all()}
        created = updated = 0

        for order, spec in enumerate(specs, start=1):
            brand, was_created = Brand.objects.update_or_create(
                name=spec["name"],
                defaults={
                    "country": spec.get("country", "India"),
                    "founded_year": spec.get("founded_year"),
                    "is_luxury": spec.get("is_luxury", False),
                    "is_featured": order <= 8,
                    "display_order": order,
                    "popularity_score": rng.randint(40, 1000),
                    "description": (
                        f"{spec['name']} — {spec.get('country', 'India')}, "
                        f"est. {spec.get('founded_year', 'n/a')}."
                    ),
                    "website": f"https://www.{_slugify(spec['name'])}.example",
                    "is_active": True,
                },
            )
            created += was_created
            updated += not was_created

            # Category links are set rather than added, so a re-run with a
            # changed roster does not leave stale associations behind.
            linked = [
                by_name[name] for name in spec.get("categories", []) if name in by_name
            ]
            if linked:
                brand.categories.set(linked)

        if verbosity:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Brands: {created} created, {updated} updated "
                    f"(total {Brand.objects.count()})."
                )
            )
            if not by_name:
                self.stdout.write(
                    self.style.WARNING(
                        "No categories exist, so no brand-category links were made. "
                        "Run seed_categories first."
                    )
                )


def _slugify(name: str) -> str:
    """Return a lower-case, alphanumeric form of ``name`` for a domain."""
    return "".join(character for character in name.lower() if character.isalnum())
