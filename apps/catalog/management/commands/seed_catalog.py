"""Seed the catalogue with realistic data matching the storefront navigation.

Idempotent: every row is matched on its natural key, so running the command a
second time updates rather than duplicates. That is what makes it safe to run
on every deploy of a staging environment.

Seed data belongs in a management command, not a data migration. A data
migration runs exactly once per database and is then frozen into history —
so correcting a typo in a brand name would need a second migration, and the
command could never be re-run to refresh a scratch environment.

Usage::

    python manage.py seed_catalog
    python manage.py seed_catalog --flush     # delete existing catalogue first
    python manage.py seed_catalog --dry-run   # report without writing
"""

from __future__ import annotations

import random
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.catalog.models import Brand, Category, Collection, CollectionType, SubCategory
from apps.catalog.services import invalidate_catalog_cache

# ---------------------------------------------------------------------------
# Categories and their storefront navigation
# ---------------------------------------------------------------------------

CATEGORIES: list[dict[str, Any]] = [
    {
        "name": "Women",
        "description": "Ethnic, western and fusion wear curated for every occasion.",
        "is_featured": True,
        "is_trending": True,
        "subcategories": [
            "Kurtas & Suits", "Sarees", "Lehengas", "Dresses", "Tops & Tunics",
            "Jeans & Trousers", "Skirts & Shorts", "Co-ord Sets", "Ethnic Sets",
            "Loungewear", "Winterwear", "Innerwear & Sleepwear",
        ],
    },
    {
        "name": "Men",
        "description": "Everyday essentials, formal edits and festive ethnic wear.",
        "is_featured": True,
        "is_trending": True,
        "subcategories": [
            "T-Shirts", "Shirts", "Jeans", "Trousers & Chinos", "Kurta Sets",
            "Sherwanis", "Jackets & Coats", "Activewear", "Shorts",
            "Suits & Blazers", "Innerwear & Loungewear",
        ],
    },
    {
        "name": "Kids",
        "description": "Playful, comfortable clothing for newborns to teens.",
        "is_featured": True,
        "subcategories": [
            "Girls Clothing", "Boys Clothing", "Infants", "Ethnic Wear",
            "Party Wear", "Nightwear", "School Uniforms", "Kids Footwear",
        ],
    },
    {
        "name": "Beauty",
        "description": "Makeup, skincare and fragrance from cult-favourite labels.",
        "is_featured": True,
        "is_trending": True,
        "subcategories": [
            "Makeup", "Skincare", "Haircare", "Fragrance", "Bath & Body",
            "Men's Grooming", "Nail Care", "Beauty Tools",
        ],
    },
    {
        "name": "Accessories",
        "description": "The finishing touches: eyewear, belts, scarves and watches.",
        "is_featured": True,
        "subcategories": [
            "Watches", "Sunglasses", "Belts", "Scarves & Stoles", "Hats & Caps",
            "Hair Accessories", "Wallets", "Tech Accessories",
        ],
    },
    {
        "name": "Footwear",
        "description": "Heels, sneakers, sandals and juttis for every wardrobe.",
        "is_featured": True,
        "is_trending": True,
        "subcategories": [
            "Heels", "Flats & Ballerinas", "Sneakers", "Sandals & Flip Flops",
            "Boots", "Juttis & Mojaris", "Formal Shoes", "Sports Shoes",
        ],
    },
    {
        "name": "Bags",
        "description": "Totes, slings, backpacks and evening clutches.",
        "is_featured": True,
        "subcategories": [
            "Handbags", "Tote Bags", "Sling Bags", "Backpacks", "Clutches",
            "Laptop Bags", "Travel Luggage", "Potli Bags",
        ],
    },
    {
        "name": "Jewellery",
        "description": "Fine, fashion and temple jewellery for daily and bridal wear.",
        "is_featured": True,
        "is_luxury": True,
        "subcategories": [
            "Earrings", "Necklaces", "Bangles & Bracelets", "Rings",
            "Anklets", "Nose Pins", "Bridal Sets", "Temple Jewellery",
        ],
    },
    {
        "name": "Luxury",
        "description": "Designer labels, limited drops and couture edits.",
        "is_featured": True,
        "is_luxury": True,
        "is_trending": True,
        "subcategories": [
            "Designer Wear", "Luxury Handbags", "Fine Jewellery",
            "Premium Watches", "Couture", "Limited Editions",
        ],
    },
    {
        "name": "Sale",
        "description": "End-of-season markdowns across every department.",
        "subcategories": [
            "Under 999", "Under 1999", "50% Off & More", "Clearance",
            "Last Sizes Left", "Festive Offers",
        ],
    },
]

# ---------------------------------------------------------------------------
# Brands — 50 fictional labels
# ---------------------------------------------------------------------------

BRANDS: list[dict[str, Any]] = [
    # (name, country, founded, luxury, categories)
    {"name": "Aarohi Couture", "country": "India", "founded_year": 2011, "is_luxury": True,
     "categories": ["Women", "Luxury"]},
    {"name": "Indigo Loom", "country": "India", "founded_year": 2014,
     "categories": ["Women", "Men"]},
    {"name": "Vermillion Thread", "country": "India", "founded_year": 2009,
     "categories": ["Women"]},
    {"name": "Nordwyn", "country": "Denmark", "founded_year": 1998,
     "categories": ["Men", "Women"]},
    {"name": "Casa Marbella", "country": "Italy", "founded_year": 1962, "is_luxury": True,
     "categories": ["Luxury", "Bags"]},
    {"name": "Saffron & Sage", "country": "India", "founded_year": 2016,
     "categories": ["Women", "Beauty"]},
    {"name": "Roux Atelier", "country": "France", "founded_year": 1955, "is_luxury": True,
     "categories": ["Luxury", "Women"]},
    {"name": "Kolm Studio", "country": "Sweden", "founded_year": 2012,
     "categories": ["Men", "Accessories"]},
    {"name": "Bellhaven", "country": "United Kingdom", "founded_year": 1976,
     "categories": ["Men", "Footwear"]},
    {"name": "Mehr Handloom", "country": "India", "founded_year": 2007,
     "categories": ["Women", "Kids"]},
    {"name": "Terra Nueve", "country": "Spain", "founded_year": 2003,
     "categories": ["Women", "Footwear"]},
    {"name": "Ashwood & Co", "country": "United Kingdom", "founded_year": 1948,
     "categories": ["Men", "Accessories"]},
    {"name": "Lumière Blanc", "country": "France", "founded_year": 1989, "is_luxury": True,
     "categories": ["Luxury", "Jewellery"]},
    {"name": "Peakline Athletics", "country": "United States", "founded_year": 2010,
     "categories": ["Men", "Footwear"]},
    {"name": "Chandni Bazaar", "country": "India", "founded_year": 2013,
     "categories": ["Women", "Jewellery"]},
    {"name": "Oru & Oak", "country": "India", "founded_year": 2018,
     "categories": ["Kids"]},
    {"name": "Verdant Row", "country": "India", "founded_year": 2015,
     "categories": ["Women", "Men"]},
    {"name": "Solstice Kids", "country": "India", "founded_year": 2017,
     "categories": ["Kids"]},
    {"name": "Marchetti Pelle", "country": "Italy", "founded_year": 1971, "is_luxury": True,
     "categories": ["Bags", "Luxury"]},
    {"name": "Halcyon Beauty", "country": "South Korea", "founded_year": 2015,
     "categories": ["Beauty"]},
    {"name": "Rasa Botanics", "country": "India", "founded_year": 2019,
     "categories": ["Beauty"]},
    {"name": "Ivory Lane", "country": "United States", "founded_year": 2008,
     "categories": ["Beauty", "Women"]},
    {"name": "Kanha Silks", "country": "India", "founded_year": 1984,
     "categories": ["Women"]},
    {"name": "Northbridge Denim", "country": "United States", "founded_year": 1991,
     "categories": ["Men", "Women"]},
    {"name": "Tessuto Nero", "country": "Italy", "founded_year": 1994, "is_luxury": True,
     "categories": ["Luxury", "Men"]},
    {"name": "Anara Jewels", "country": "India", "founded_year": 2006, "is_luxury": True,
     "categories": ["Jewellery", "Luxury"]},
    {"name": "Pashmwear", "country": "India", "founded_year": 2001,
     "categories": ["Women", "Accessories"]},
    {"name": "Straend", "country": "Norway", "founded_year": 2013,
     "categories": ["Men", "Bags"]},
    {"name": "Coralline", "country": "Australia", "founded_year": 2016,
     "categories": ["Women", "Footwear"]},
    {"name": "Bhavya Ethnics", "country": "India", "founded_year": 2010,
     "categories": ["Women", "Kids"]},
    {"name": "Larkspur & Vine", "country": "United Kingdom", "founded_year": 2014,
     "categories": ["Women", "Accessories"]},
    {"name": "Odeon Timepieces", "country": "Switzerland", "founded_year": 1936,
     "is_luxury": True, "categories": ["Accessories", "Luxury"]},
    {"name": "Rugged Meridian", "country": "United States", "founded_year": 1999,
     "categories": ["Men", "Bags"]},
    {"name": "Juhu Sands", "country": "India", "founded_year": 2020,
     "categories": ["Women", "Footwear"]},
    {"name": "Elowen", "country": "Ireland", "founded_year": 2011,
     "categories": ["Women", "Jewellery"]},
    {"name": "Sable & Stone", "country": "Canada", "founded_year": 2009,
     "categories": ["Accessories", "Bags"]},
    {"name": "Zaria Label", "country": "India", "founded_year": 2021,
     "categories": ["Women"]},
    {"name": "Fenwick Trading", "country": "United Kingdom", "founded_year": 1965,
     "categories": ["Men", "Accessories"]},
    {"name": "Palazzo Verde", "country": "Italy", "founded_year": 1982, "is_luxury": True,
     "categories": ["Luxury", "Footwear"]},
    {"name": "Auric Atelier", "country": "India", "founded_year": 2012, "is_luxury": True,
     "categories": ["Jewellery", "Luxury"]},
    {"name": "Trailhead Supply", "country": "United States", "founded_year": 2005,
     "categories": ["Bags", "Men"]},
    {"name": "Mirabel Kids", "country": "France", "founded_year": 2013,
     "categories": ["Kids"]},
    {"name": "Sundara Naturals", "country": "India", "founded_year": 2018,
     "categories": ["Beauty"]},
    {"name": "Hexley Street", "country": "United Kingdom", "founded_year": 2007,
     "categories": ["Men"]},
    {"name": "Osmanthus", "country": "Japan", "founded_year": 1996,
     "categories": ["Beauty", "Accessories"]},
    {"name": "Ravenna Rossi", "country": "Italy", "founded_year": 1958, "is_luxury": True,
     "categories": ["Luxury", "Women"]},
    {"name": "Kadam Footwear", "country": "India", "founded_year": 1993,
     "categories": ["Footwear"]},
    {"name": "Wynstone", "country": "Canada", "founded_year": 2015,
     "categories": ["Men", "Footwear"]},
    {"name": "Alto Firenze", "country": "Italy", "founded_year": 1974, "is_luxury": True,
     "categories": ["Bags", "Luxury"]},
    {"name": "Neeli Ethnic", "country": "India", "founded_year": 2017,
     "categories": ["Women", "Kids"]},
]

# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

COLLECTIONS: list[dict[str, Any]] = [
    {"title": "New Arrivals", "type": CollectionType.NEW_ARRIVALS, "is_featured": True,
     "description": "The freshest drops, updated every week.",
     "categories": ["Women", "Men", "Kids"]},
    {"title": "Trending Now", "type": CollectionType.TRENDING, "is_featured": True,
     "description": "What everyone is adding to cart this week.",
     "categories": ["Women", "Men", "Footwear"]},
    {"title": "The Luxury Edit", "type": CollectionType.LUXURY, "is_featured": True,
     "description": "Designer labels and limited couture drops.",
     "categories": ["Luxury", "Jewellery", "Bags"]},
    {"title": "Editor's Picks", "type": CollectionType.EDITORS_PICKS, "is_featured": True,
     "description": "Handpicked by our styling team.",
     "categories": ["Women", "Men", "Accessories"]},
    {"title": "Best Sellers", "type": CollectionType.BEST_SELLERS, "is_featured": True,
     "description": "The pieces our customers keep coming back for.",
     "categories": ["Women", "Men", "Beauty"]},
    {"title": "Festive Collection", "type": CollectionType.FESTIVAL, "is_featured": True,
     "description": "Diwali, Navratri and Eid ready.",
     "categories": ["Women", "Men", "Kids", "Jewellery"]},
    {"title": "Wedding Collection", "type": CollectionType.WEDDING, "is_featured": True,
     "description": "Bridal lehengas, sherwanis and everything in between.",
     "categories": ["Women", "Men", "Jewellery", "Footwear"]},
    {"title": "Summer Collection", "type": CollectionType.SUMMER,
     "description": "Linen, cotton and breathable everyday wear.",
     "categories": ["Women", "Men", "Kids"]},
    {"title": "Winter Collection", "type": CollectionType.WINTER,
     "description": "Layered knits, coats and cold-weather staples.",
     "categories": ["Women", "Men", "Kids"]},
    {"title": "Workwear Edit", "type": CollectionType.EDITORS_PICKS,
     "description": "Polished pieces that survive a full day.",
     "categories": ["Women", "Men"]},
    {"title": "Weekend Casuals", "type": CollectionType.TRENDING,
     "description": "Easy silhouettes for slow Saturdays.",
     "categories": ["Women", "Men"]},
    {"title": "Statement Jewellery", "type": CollectionType.EDITORS_PICKS,
     "description": "Pieces that carry the whole outfit.",
     "categories": ["Jewellery"]},
]


class Command(BaseCommand):
    """Populate categories, subcategories, brands and collections."""

    help = "Seed the catalogue with realistic categories, brands and collections."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing catalogue records before seeding.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing to the database.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed the catalogue, rolling back entirely on any error."""
        # Deterministic popularity scores: a re-run must not reshuffle the
        # "popular brands" rail, which would make the homepage look unstable.
        rng = random.Random(20260804)

        if options["flush"]:
            self._flush(dry_run=options["dry_run"])

        categories = self._seed_categories(dry_run=options["dry_run"])
        subcategory_count = self._seed_subcategories(categories, dry_run=options["dry_run"])
        brand_count = self._seed_brands(categories, rng, dry_run=options["dry_run"])
        collection_count = self._seed_collections(categories, dry_run=options["dry_run"])

        invalidate_catalog_cache()

        # Honour --verbosity 0 so the test suite is not drowned in summaries.
        if options.get("verbosity", 1):
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Catalogue seeded:"))
            self.stdout.write(f"  categories    {len(categories)}")
            self.stdout.write(f"  subcategories {subcategory_count}")
            self.stdout.write(f"  brands        {brand_count}")
            self.stdout.write(f"  collections   {collection_count}")

        if options["dry_run"]:
            if options.get("verbosity", 1):
                self.stdout.write("")
                self.stdout.write(self.style.WARNING("Dry run — rolling back."))
            transaction.set_rollback(True)

    # -- steps --------------------------------------------------------------

    def _flush(self, *, dry_run: bool) -> None:
        """Delete every existing catalogue record."""
        counts = {
            "collections": Collection.objects.count(),
            "brands": Brand.objects.count(),
            "subcategories": SubCategory.objects.count(),
            "categories": Category.objects.count(),
        }
        self.stdout.write(self.style.WARNING(f"Flushing existing catalogue: {counts}"))

        if not dry_run:
            Collection.objects.all().delete()
            Brand.objects.all().delete()
            SubCategory.objects.all().delete()
            Category.objects.all().delete()

    def _seed_categories(self, *, dry_run: bool) -> dict[str, Category]:
        """Create or update the top-level categories."""
        created: dict[str, Category] = {}

        for order, spec in enumerate(CATEGORIES, start=1):
            defaults = {
                "description": spec["description"],
                "display_order": order,
                "is_active": True,
                "is_featured": spec.get("is_featured", False),
                "is_trending": spec.get("is_trending", False),
                "is_luxury": spec.get("is_luxury", False),
                "meta_title": f"{spec['name']} | Fashion Trendz",
                "meta_description": spec["description"][:170],
            }
            if dry_run:
                category = Category(name=spec["name"], **defaults)
                category.slug = spec["name"].lower()
            else:
                category, _ = Category.objects.update_or_create(
                    name=spec["name"], defaults=defaults
                )
            created[spec["name"]] = category

        return created

    def _seed_subcategories(
        self,
        categories: dict[str, Category],
        *,
        dry_run: bool,
    ) -> int:
        """Create or update the second-level navigation."""
        total = 0

        for spec in CATEGORIES:
            parent = categories[spec["name"]]
            for order, name in enumerate(spec["subcategories"], start=1):
                total += 1
                if dry_run:
                    continue
                SubCategory.objects.update_or_create(
                    category=parent,
                    name=name,
                    defaults={
                        "display_order": order,
                        "is_active": True,
                        "description": f"{name} in {parent.name}.",
                        "meta_title": f"{name} - {parent.name} | Fashion Trendz",
                    },
                )

        return total

    def _seed_brands(
        self,
        categories: dict[str, Category],
        rng: random.Random,
        *,
        dry_run: bool,
    ) -> int:
        """Create or update the brand list and its category links."""
        total = 0

        for order, spec in enumerate(BRANDS, start=1):
            total += 1
            if dry_run:
                continue

            is_luxury = spec.get("is_luxury", False)
            brand, _ = Brand.objects.update_or_create(
                name=spec["name"],
                defaults={
                    "country": spec["country"],
                    "founded_year": spec["founded_year"],
                    "description": (
                        f"{spec['name']} has been designing from "
                        f"{spec['country']} since {spec['founded_year']}."
                    ),
                    "website": f"https://www.{_domain(spec['name'])}.example",
                    "is_active": True,
                    "is_luxury": is_luxury,
                    # Every fourth brand is featured, so the homepage rail has
                    # roughly a dozen entries rather than all fifty.
                    "is_featured": order % 4 == 0,
                    "display_order": order,
                    "popularity_score": rng.randint(200, 1000) + (300 if is_luxury else 0),
                    "meta_title": f"{spec['name']} | Fashion Trendz",
                },
            )
            brand.categories.set(
                [categories[name] for name in spec["categories"] if name in categories]
            )

        return total

    def _seed_collections(
        self,
        categories: dict[str, Category],
        *,
        dry_run: bool,
    ) -> int:
        """Create or update the homepage collections."""
        total = 0

        for order, spec in enumerate(COLLECTIONS, start=1):
            total += 1
            if dry_run:
                continue

            collection, _ = Collection.objects.update_or_create(
                title=spec["title"],
                defaults={
                    "type": spec["type"],
                    "description": spec["description"],
                    "is_active": True,
                    "is_featured": spec.get("is_featured", False),
                    "display_order": order,
                    "meta_title": f"{spec['title']} | Fashion Trendz",
                    "meta_description": spec["description"][:170],
                },
            )
            collection.categories.set(
                [categories[name] for name in spec["categories"] if name in categories]
            )

        return total


def _domain(name: str) -> str:
    """Return a plausible domain fragment for a brand name."""
    return "".join(character for character in name.lower() if character.isalnum())
