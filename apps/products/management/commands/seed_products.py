"""Seed the catalogue with realistic products.

Depends on ``seed_catalog`` having run first — products need categories,
subcategories and brands to point at.

Usage::

    python manage.py seed_products                 # 700 products
    python manage.py seed_products --count 1500
    python manage.py seed_products --flush         # delete products first

Idempotent through the SKU: a re-run updates rather than duplicates.
"""

from __future__ import annotations

import random
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Brand, Category, Collection, SubCategory
from apps.products.models import (
    Fit,
    Material,
    NeckType,
    Occasion,
    Pattern,
    Product,
    ProductAttribute,
    ProductImage,
    ProductSpecification,
    ProductTag,
    ProductVariant,
    Season,
    Size,
    SleeveType,
)
from apps.core.seed_assets import AssetLibrary, close_all, iter_expected_folders
from apps.products.services import invalidate_product_cache, sync_product_stock

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

ADJECTIVES = [
    "Classic", "Everyday", "Signature", "Heritage", "Relaxed", "Tailored",
    "Handwoven", "Embroidered", "Pleated", "Draped", "Structured", "Featherlight",
    "Essential", "Statement", "Vintage", "Modern", "Artisanal", "Luxe",
    "Minimal", "Sculpted", "Layered", "Breezy", "Textured", "Refined",
]

PRODUCT_NOUNS: dict[str, list[str]] = {
    "Women": ["Kurta", "Saree", "Lehenga", "Midi Dress", "Wrap Top", "Palazzo",
              "Co-ord Set", "Anarkali", "Tunic", "Maxi Dress", "Blouse", "Jumpsuit"],
    "Men": ["Shirt", "Polo Tee", "Chinos", "Kurta", "Sherwani", "Bomber Jacket",
            "Henley", "Blazer", "Joggers", "Oxford Shirt", "Waistcoat", "Tee"],
    "Kids": ["Playsuit", "Frock", "Dungaree", "Tee Set", "Ethnic Set", "Hoodie",
             "Shorts Set", "Party Dress", "Romper", "Track Set"],
    "Beauty": ["Lip Tint", "Face Serum", "Kajal", "Hair Mask", "Body Butter",
               "Eau de Parfum", "Cleanser", "Compact", "Nail Lacquer", "Face Mist"],
    "Accessories": ["Wristwatch", "Sunglasses", "Leather Belt", "Silk Stole",
                    "Bucket Hat", "Hair Clip Set", "Bifold Wallet", "Phone Sleeve"],
    "Footwear": ["Block Heels", "Ballerinas", "Sneakers", "Kolhapuris", "Chelsea Boots",
                 "Juttis", "Derby Shoes", "Running Shoes", "Slides", "Loafers"],
    "Bags": ["Tote", "Sling Bag", "Backpack", "Clutch", "Laptop Bag", "Potli",
             "Duffle", "Crossbody Bag"],
    "Jewellery": ["Jhumkas", "Choker", "Kada", "Statement Ring", "Anklet Pair",
                  "Nose Pin", "Bridal Set", "Temple Necklace"],
    "Luxury": ["Silk Gown", "Cashmere Coat", "Designer Clutch", "Fine Bracelet",
               "Couture Saree", "Limited Sneaker", "Chronograph Watch"],
    "Sale": ["Cotton Tee", "Denim Jeans", "Printed Kurta", "Casual Shirt",
             "Everyday Dress", "Canvas Sneakers"],
}

COLOURS: list[tuple[str, str]] = [
    ("Black", "#111827"), ("Ivory", "#F8F5F0"), ("Navy", "#1E3A8A"),
    ("Olive", "#4D5D3A"), ("Rust", "#B7410E"), ("Blush", "#F3C6C6"),
    ("Mustard", "#D6A419"), ("Emerald", "#046A4E"), ("Maroon", "#6B1420"),
    ("Sky", "#7FB2E5"), ("Charcoal", "#374151"), ("Beige", "#D9C7A7"),
    ("Wine", "#5C1A32"), ("Teal", "#0F766E"), ("Coral", "#F26B5B"),
]

APPAREL_SIZES = [Size.XS, Size.S, Size.M, Size.L, Size.XL, Size.XXL]
FOOTWEAR_SIZES = [Size.UK6, Size.UK7, Size.UK8, Size.UK9, Size.UK10]
FREE_SIZE = [Size.FREE]

FOOTWEAR_CATEGORIES = {"Footwear"}
ONE_SIZE_CATEGORIES = {"Beauty", "Accessories", "Bags", "Jewellery"}

COUNTRIES = ["India", "India", "India", "Italy", "Portugal", "Vietnam", "Turkey"]

CARE = [
    "Machine wash cold with like colours. Do not bleach. Tumble dry low.",
    "Dry clean only. Warm iron on reverse. Store folded.",
    "Hand wash separately in cold water. Dry in shade.",
    "Wipe with a soft dry cloth. Keep away from moisture and perfume.",
]

RETURN_POLICIES = [
    "15-day easy return", "7-day exchange only", "30-day free return",
    "Non-returnable (hygiene product)",
]

SHIPPING = [
    "Free shipping over 999", "Standard delivery 3-5 days",
    "Express delivery available", "Ships in 24 hours",
]

TAGS = [
    "linen-edit", "under-1999", "office-ready", "festive-picks", "everyday-basics",
    "sustainable", "handcrafted", "new-season", "limited-drop", "gifting",
]


class Command(BaseCommand):
    """Populate products with variants, images, specifications and attributes."""

    help = "Seed the product catalogue with realistic data."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--count", type=int, default=700, help="Number of products to create."
        )
        parser.add_argument(
            "--flush", action="store_true", help="Delete existing products first."
        )
        parser.add_argument(
            "--seed", type=int, default=20260804, help="Random seed, for reproducibility."
        )
        parser.add_argument(
            "--no-images", action="store_true", help="Skip galleries entirely."
        )
        parser.add_argument(
            "--images-per-product",
            type=int,
            default=0,
            help="Fixed gallery size. Default 0 picks 4-6 at random per product.",
        )
        parser.add_argument(
            "--assets-dir",
            default="",
            help="Image library root. Defaults to SEED_ASSETS_DIR or ./seed_assets.",
        )
        parser.add_argument(
            "--fetch-remote",
            action="store_true",
            help="Download http(s) manifest entries. Off by default.",
        )
        parser.add_argument(
            "--generate-placeholders",
            action="store_true",
            help=(
                "Generate stand-in images where the asset library has none. "
                "Off by default: real gaps should stay visible."
            ),
        )
        parser.add_argument(
            "--list-asset-folders",
            action="store_true",
            help="Print the folder layout the content team should populate, then exit.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed products, rolling back entirely on any error."""
        verbosity = options.get("verbosity", 1)
        rng = random.Random(options["seed"])

        if options["list_asset_folders"]:
            self._print_asset_folders()
            return

        library = AssetLibrary(
            options["assets_dir"] or None, fetch_remote=options["fetch_remote"], rng=rng
        )

        subcategories = list(
            SubCategory.objects.select_related("category").filter(is_active=True)
        )
        brands = list(Brand.objects.filter(is_active=True))

        if not subcategories or not brands:
            raise CommandError(
                "Run 'python manage.py seed_catalog' first — products need "
                "categories, subcategories and brands to reference."
            )

        if options["flush"]:
            deleted = Product.objects.count()
            Product.objects.all().delete()
            if verbosity:
                self.stdout.write(self.style.WARNING(f"Deleted {deleted} products."))

        tags = self._seed_tags()
        collections = list(Collection.objects.filter(is_active=True))

        created = self._seed_products(
            count=options["count"],
            subcategories=subcategories,
            brands=brands,
            collections=collections,
            tags=tags,
            rng=rng,
            verbosity=verbosity,
            with_images=not options["no_images"],
            images_per_product=options["images_per_product"],
            library=library,
            placeholders=options["generate_placeholders"],
        )

        invalidate_product_cache()

        if verbosity:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Products seeded:"))
            self.stdout.write(f"  products       {created}")
            self.stdout.write(f"  variants       {ProductVariant.objects.count()}")
            self.stdout.write(f"  images         {ProductImage.objects.count()}")
            self.stdout.write(f"  assets         {library.summary()}")
            for warning in library.warnings():
                self.stdout.write(
                    self.style.WARNING(f"    no images found for {warning}")
                )
            self.stdout.write(f"  specifications {ProductSpecification.objects.count()}")
            self.stdout.write(f"  attributes     {ProductAttribute.objects.count()}")
            self.stdout.write(f"  tags           {len(tags)}")
            self.stdout.write(f"  categories     {Category.objects.count()}")
            self.stdout.write(f"  subcategories  {SubCategory.objects.count()}")
            self.stdout.write(f"  brands         {Brand.objects.count()}")

    # -- steps --------------------------------------------------------------

    def _seed_tags(self) -> list[ProductTag]:
        """Create the merchandising tags."""
        return [
            ProductTag.objects.get_or_create(
                name=name.replace("-", " ").title(),
                defaults={"is_active": True},
            )[0]
            for name in TAGS
        ]

    def _seed_products(
        self,
        *,
        count: int,
        subcategories: list[SubCategory],
        brands: list[Brand],
        collections: list[Collection],
        tags: list[ProductTag],
        rng: random.Random,
        verbosity: int,
        with_images: bool = True,
        images_per_product: int = 0,
        library: "AssetLibrary | None" = None,
        placeholders: bool = False,
    ) -> int:
        """Create ``count`` products with their satellites."""
        now = timezone.now()
        created = 0

        for index in range(1, count + 1):
            subcategory = rng.choice(subcategories)
            category = subcategory.category
            brand = rng.choice(brands)

            noun_pool = PRODUCT_NOUNS.get(category.name, PRODUCT_NOUNS["Women"])
            name = f"{rng.choice(ADJECTIVES)} {rng.choice(noun_pool)}"

            mrp, selling_price = self._prices(rng, luxury=brand.is_luxury)
            sku = f"FT-P{index:05d}"

            # Publication spread over the past two years so "newest" ordering,
            # date filters and the trending-this-week rail all have real data.
            published_at = now - timezone.timedelta(
                days=rng.randint(0, 730), hours=rng.randint(0, 23)
            )

            rating_count = rng.choice([0, 0, 3, 12, 47, 128, 356, 890])
            rating_average = (
                Decimal("0.00")
                if rating_count == 0
                else Decimal(str(round(rng.uniform(3.2, 4.9), 2)))
            )

            product, _created = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "short_description": (
                        f"{name} by {brand.name}, cut for {category.name.lower()}."
                    ),
                    "long_description": (
                        f"An {rng.choice(ADJECTIVES).lower()} {name.lower()} from "
                        f"{brand.name}. Designed in {brand.country or 'India'} and "
                        f"finished for {rng.choice(Occasion.values).replace('_', ' ')} "
                        f"wear, this piece sits in the {subcategory.name} edit."
                    ),
                    "category": category,
                    "subcategory": subcategory,
                    "brand": brand,
                    "collection": (
                        rng.choice(collections) if collections and rng.random() < 0.35 else None
                    ),
                    "mrp": mrp,
                    "selling_price": selling_price,
                    "tax_percentage": Decimal(rng.choice(["5.00", "12.00", "18.00"])),
                    "gender": self._gender_for(category.name, rng),
                    "material": rng.choice(Material.values),
                    "fit": rng.choice(Fit.values),
                    "sleeve_type": rng.choice(SleeveType.values),
                    "neck_type": rng.choice(NeckType.values),
                    "pattern": rng.choice(Pattern.values),
                    "occasion": rng.choice(Occasion.values),
                    "season": rng.choice(Season.values),
                    "country_of_origin": rng.choice(COUNTRIES),
                    "weight_grams": rng.randint(120, 1800),
                    "dimensions": f"{rng.randint(20, 40)} x {rng.randint(15, 30)} x {rng.randint(2, 12)}",
                    "warranty": rng.choice(["", "", "6 months on hardware", "1 year manufacturer warranty"]),
                    "care_instructions": rng.choice(CARE),
                    "return_policy": rng.choice(RETURN_POLICIES),
                    "shipping_info": rng.choice(SHIPPING),
                    "estimated_delivery_days": rng.randint(2, 9),
                    "rating_average": rating_average,
                    "rating_count": rating_count,
                    "review_count": rating_count,
                    "wishlist_count": rng.randint(0, 900),
                    "view_count": rng.randint(20, 25_000),
                    "purchase_count": rng.randint(0, 1_400),
                    "is_active": rng.random() > 0.04,
                    "is_featured": rng.random() < 0.08,
                    "is_new_arrival": published_at > now - timezone.timedelta(days=45),
                    "is_best_seller": rng.random() < 0.10,
                    "is_trending": rng.random() < 0.09,
                    "is_luxury": brand.is_luxury or category.is_luxury,
                    "is_recommended": rng.random() < 0.12,
                    "is_returnable": "Non-returnable" not in rng.choice(RETURN_POLICIES),
                    "published_at": published_at,
                    "meta_title": f"{name} by {brand.name} | Fashion Trendz",
                    "meta_description": (
                        f"Shop the {name} from {brand.name}. "
                        f"{subcategory.name} in {category.name}."
                    )[:170],
                },
            )

            product.tags.set(rng.sample(tags, k=rng.randint(0, 3)))
            self._seed_variants(product, category.name, rng)
            self._seed_specifications(product, brand, rng)
            self._seed_attributes(product, rng)
            if with_images and library is not None:
                self._seed_images(
                    product, subcategory, rng, library, images_per_product, placeholders
                )
            sync_product_stock(product)

            created += 1
            if verbosity and created % 100 == 0:
                self.stdout.write(f"  ... {created} products")

        return created

    def _prices(self, rng: random.Random, *, luxury: bool) -> tuple[Decimal, Decimal]:
        """Return a plausible (MRP, selling price) pair.

        Discounts cluster at the round numbers a merchandiser actually uses —
        nobody prices anything at 37% off — with a third of the catalogue at
        full price, which is what makes a "sale" filter meaningful.
        """
        base = rng.randint(12_000, 90_000) if luxury else rng.randint(399, 8_999)
        mrp = Decimal(base).quantize(Decimal("0.01"))

        discount = rng.choice([0, 0, 0, 10, 15, 20, 25, 30, 40, 50, 60, 70])
        selling = (mrp * (Decimal(100 - discount) / Decimal(100))).quantize(
            Decimal("0.01")
        )
        return mrp, selling

    def _gender_for(self, category_name: str, rng: random.Random) -> str:
        """Return a gender consistent with the category."""
        from apps.core.choices import Gender

        mapping = {
            "Women": Gender.FEMALE,
            "Men": Gender.MALE,
            "Kids": Gender.UNISEX,
        }
        return mapping.get(category_name, rng.choice([Gender.UNISEX, Gender.FEMALE, Gender.MALE]))

    def _sizes_for(self, category_name: str) -> list[str]:
        """Return the size run appropriate to a category."""
        if category_name in FOOTWEAR_CATEGORIES:
            return FOOTWEAR_SIZES
        if category_name in ONE_SIZE_CATEGORIES:
            return FREE_SIZE
        return APPAREL_SIZES

    def _seed_variants(
        self, product: Product, category_name: str, rng: random.Random
    ) -> None:
        """Create the colour/size grid for one product.

        Skipped when a grid already exists. Deleting and rebuilding would draw
        a fresh colour count from the rng on every run, so the variant total
        would drift up and down across re-runs — and it would orphan any cart
        line or order item pointing at a variant that no longer exists.
        """
        if product.variants.exists():
            return

        sizes = self._sizes_for(category_name)

        # The brief asks for 8-20 variants per product. Sizes come from the
        # category (a dress runs XS-XXL, a watch is one size), so the colour
        # count is chosen to land the grid in that window rather than fixed.
        low = max(2, -(-8 // max(len(sizes), 1)))          # ceil(8 / sizes)
        high = max(low, min(len(COLOURS), 20 // max(len(sizes), 1)))
        colours = rng.sample(COLOURS, k=rng.randint(low, max(low, high)))

        for colour_index, (colour, hex_code) in enumerate(colours):
            for size_index, size in enumerate(sizes):
                # A quarter of the grid is deliberately out of stock, so the
                # "only 2 left" and "sold out" states have real data to render.
                stock = rng.choice([0, 0, 1, 3, 5, 12, 40, 120, 300])
                ProductVariant.objects.create(
                    product=product,
                    sku=f"{product.sku}-{colour_index}{size_index}",
                    barcode=str(rng.randint(10**11, 10**12 - 1)),
                    color=colour,
                    color_code=hex_code,
                    size=size,
                    stock=stock,
                    reserved_stock=min(rng.randint(0, 2), stock),
                    weight_grams=product.weight_grams,
                    is_active=rng.random() > 0.05,
                )

    def _seed_images(
        self,
        product: Product,
        subcategory: SubCategory,
        rng: random.Random,
        library: AssetLibrary,
        fixed: int = 0,
        placeholders: bool = False,
    ) -> None:
        """Attach a gallery of four to six real photographs.

        Files come from the asset library — a manifest entry keyed on the SKU,
        or the subcategory folder, or ``_default``. Nothing is invented: when
        the library has nothing, the product is left without imagery and the
        command reports which folder it looked in.

        Exactly one image is primary, which the partial unique index on
        ``ProductImage`` enforces anyway.
        """
        # Idempotency. Re-running against an existing catalogue must not stack
        # a second gallery onto every product.
        if product.images.exists():
            return

        total = fixed if fixed > 0 else rng.randint(4, 6)
        files = library.images_for_product(
            sku=product.sku,
            slug=product.slug,
            subcategory_slug=subcategory.slug,
            count=total,
        )

        if not files and placeholders:
            files = self._placeholders(product, total)

        if not files:
            return

        angles = ["front", "back", "detail", "styled", "flat-lay", "close-up"]
        try:
            for index, handle in enumerate(files):
                ProductImage.objects.create(
                    product=product,
                    image=handle,
                    alt_text=f"{product.name} - {angles[index % len(angles)]} view",
                    display_order=index,
                    is_primary=index == 0,
                )
        finally:
            # A 500-product seed opens thousands of files; leaving them to the
            # garbage collector exhausts the process descriptor limit.
            close_all(files)

    @staticmethod
    def _placeholders(product: Product, total: int) -> list:
        """Return generated stand-in images. Only used with an explicit flag."""
        from apps.core.seeding import make_image

        return [
            make_image(f"{product.sku}-{index}", offset=index, caption=product.name[:28])
            for index in range(total)
        ]

    def _print_asset_folders(self) -> None:
        """List the folder layout the content team should populate."""
        slugs = SubCategory.objects.filter(is_active=True).values_list(
            "slug", flat=True
        )
        self.stdout.write("Expected layout under seed_assets/:")
        self.stdout.write("")
        for folder in iter_expected_folders(slugs):
            self.stdout.write(f"  {folder}")
        self.stdout.write("")
        self.stdout.write(
            "Drop images into any of these. products/_default/ is the fallback "
            "for subcategories with no dedicated folder."
        )

    def _seed_specifications(
        self, product: Product, brand: Brand, rng: random.Random
    ) -> None:
        """Create the specification table rows."""
        product.specifications.all().delete()

        rows = [
            ("Brand", brand.name),
            ("Material", product.get_material_display() or "Mixed"),
            ("Fit", product.get_fit_display() or "Regular"),
            ("Pattern", product.get_pattern_display() or "Solid"),
            ("Occasion", product.get_occasion_display() or "Casual"),
            ("Country of Origin", product.country_of_origin or "India"),
            ("Net Weight", f"{product.weight_grams} g"),
        ]
        for order, (label, value) in enumerate(rows, start=1):
            ProductSpecification.objects.create(
                product=product, label=label, value=value, display_order=order
            )

    def _seed_attributes(self, product: Product, rng: random.Random) -> None:
        """Create the key/value attribute rows."""
        product.attributes.all().delete()

        pool = {
            "Closure": rng.choice(["Zip", "Button", "Pull-on", "Hook & Eye"]),
            "Lining": rng.choice(["Lined", "Unlined", "Partially lined"]),
            "Transparency": rng.choice(["Opaque", "Semi-sheer", "Sheer"]),
            "Stretch": rng.choice(["Non-stretch", "2-way stretch", "4-way stretch"]),
            "Sleeve Length": rng.choice(["Short", "Long", "Three-quarter", "None"]),
        }
        for key in rng.sample(sorted(pool), k=rng.randint(2, 4)):
            ProductAttribute.objects.create(product=product, key=key, value=pool[key])
