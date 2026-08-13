"""Seed exactly N categories, with their subcategories.

A focused companion to ``seed_catalog``, which seeds the whole taxonomy at
once. This command exists because the brief asks for twenty categories, while
``seed_catalog`` deliberately seeds ten and has tests asserting that count.

Rather than duplicate the taxonomy, the first ten entries are imported from
``seed_catalog`` and ten more are declared here. Editing a subcategory list in
one place therefore updates both commands.

Idempotent: re-running updates rather than duplicating, so it is safe against a
database that already has products hanging off these categories.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.catalog.management.commands.seed_catalog import CATEGORIES as BASE_CATEGORIES
from apps.catalog.models import Category, SubCategory

#: The ten categories beyond the base taxonomy, taking the total to twenty.
#: Kept separate rather than appended to seed_catalog.CATEGORIES so that
#: command's documented output — and the tests pinning it — do not change.
EXTRA_CATEGORIES: list[dict[str, Any]] = [
    {
        "name": "Maternity",
        "description": "Bump-friendly cuts for pregnancy and after.",
        "subcategories": [
            "Maternity Dresses", "Maternity Tops", "Maternity Bottoms",
            "Nursing Wear", "Maternity Loungewear", "Maternity Ethnic",
            "Maternity Denim", "Feeding Kurtis",
        ],
    },
    {
        "name": "Watches",
        "description": "Analogue, digital and smart watches across every budget.",
        "subcategories": [
            "Analogue Watches", "Digital Watches", "Smart Watches",
            "Luxury Watches", "Watch Straps", "Chronographs", "Kids Watches",
        ],
    },
    {
        "name": "Occasion Wear",
        "description": "Cocktail, party and black-tie edits.",
        "is_trending": True,
        "subcategories": [
            "Cocktail Dresses", "Gowns", "Party Tops", "Tuxedos",
            "Occasion Blazers", "Sequin Wear", "Capes & Shrugs",
        ],
    },
    {
        "name": "Eyewear",
        "description": "Sunglasses, frames and lenses.",
        "subcategories": [
            "Sunglasses", "Eyeglasses", "Contact Lenses", "Reading Glasses",
            "Blue-Light Glasses", "Sports Eyewear",
        ],
    },
    {
        "name": "Sportswear",
        "description": "Performance and athleisure for training and rest days.",
        "is_trending": True,
        "subcategories": [
            "Track Pants", "Sports Bras", "Gym T-Shirts", "Yoga Wear",
            "Running Gear", "Swimwear", "Sports Accessories",
        ],
    },
    {
        "name": "Winterwear",
        "description": "Jackets, knitwear and thermals for the cold months.",
        "subcategories": [
            "Jackets", "Sweaters & Cardigans", "Sweatshirts & Hoodies",
            "Thermals", "Shawls & Stoles", "Gloves & Caps",
        ],
    },
    {
        "name": "Ethnic Wear",
        "description": "Festive and wedding edits rooted in Indian craft.",
        "is_featured": True,
        "is_trending": True,
        "subcategories": [
            "Anarkali Suits", "Salwar Kameez", "Dhoti & Kurta", "Nehru Jackets",
            "Dupattas", "Blouses", "Bridal Wear",
        ],
    },
    {
        "name": "Home & Living",
        "description": "Textiles and decor that finish a room.",
        "subcategories": [
            "Bed Linen", "Cushions & Throws", "Curtains", "Rugs & Carpets",
            "Table Linen", "Bath Linen", "Wall Decor", "Floor Cushions",
        ],
    },
    {
        "name": "Fragrances",
        "description": "Perfumes, deodorants and attars.",
        "subcategories": [
            "Perfumes", "Deodorants", "Attars & Oils", "Gift Sets",
            "Body Mists", "Roll-Ons",
        ],
    },
    {
        "name": "Plus Size",
        "description": "Considered fits from L to 6XL, cut properly rather than scaled up.",
        "is_featured": True,
        "subcategories": [
            "Plus Size Tops", "Plus Size Dresses", "Plus Size Bottoms",
            "Plus Size Ethnic", "Plus Size Menswear", "Plus Size Activewear",
            "Plus Size Innerwear",
        ],
    },
]

ALL_CATEGORIES: list[dict[str, Any]] = BASE_CATEGORIES + EXTRA_CATEGORIES

# A name appearing in both lists would update the base row instead of creating a
# new one, and --count 20 would quietly yield eighteen categories. Caught at
# import so it fails on the developer's machine rather than in the seeded data.
_DUPLICATES = {c["name"] for c in BASE_CATEGORIES} & {c["name"] for c in EXTRA_CATEGORIES}
assert not _DUPLICATES, f"EXTRA_CATEGORIES duplicates seed_catalog: {sorted(_DUPLICATES)}"


class Command(BaseCommand):
    """Create or update the category tree."""

    help = "Seed categories and their subcategories (20 by default)."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="How many categories to seed. Default 20; maximum %d."
            % len(ALL_CATEGORIES),
        )
        parser.add_argument(
            "--skip-subcategories",
            action="store_true",
            help="Create categories only, leaving the second level alone.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed the taxonomy, rolling back entirely on any error."""
        verbosity = options.get("verbosity", 1)
        wanted = max(1, min(options["count"], len(ALL_CATEGORIES)))
        specs = ALL_CATEGORIES[:wanted]

        created_categories = updated_categories = 0
        created_subcategories = 0

        for order, spec in enumerate(specs, start=1):
            category, created = Category.objects.update_or_create(
                name=spec["name"],
                defaults={
                    "description": spec.get("description", ""),
                    "is_featured": spec.get("is_featured", False),
                    "is_trending": spec.get("is_trending", False),
                    "is_luxury": spec.get("is_luxury", False),
                    "display_order": order,
                    "is_active": True,
                },
            )
            created_categories += created
            updated_categories += not created

            if options["skip_subcategories"]:
                continue

            for sub_order, name in enumerate(spec.get("subcategories", []), start=1):
                # Subcategory names are unique per parent, not globally —
                # "Shirts" legitimately exists under both Men and Women — so the
                # lookup must include the category.
                _, sub_created = SubCategory.objects.update_or_create(
                    category=category,
                    name=name,
                    defaults={"display_order": sub_order, "is_active": True},
                )
                created_subcategories += sub_created

        if verbosity:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Categories: {created_categories} created, "
                    f"{updated_categories} updated "
                    f"(total {Category.objects.count()})."
                )
            )
            if not options["skip_subcategories"]:
                self.stdout.write(
                    f"Subcategories: {created_subcategories} created "
                    f"(total {SubCategory.objects.count()})."
                )
