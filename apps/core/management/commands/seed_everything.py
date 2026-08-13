"""Run every seeder in dependency order.

The order is not cosmetic. Products need categories and brands; orders need
customers and products; reviews need *delivered* orders; recommendations need
orders to derive co-purchase edges from. Running these out of order does not
produce partial data, it produces a command that stops with "run X first".

Each step is a separate transaction. A failure part-way leaves the completed
steps in place, so a re-run picks up where it stopped rather than starting over
— which matters when the product step takes minutes.
"""

from __future__ import annotations

import time
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser

#: (command, description, options). Order is the dependency order.
PIPELINE: list[tuple[str, str, dict[str, Any]]] = [
    ("seed_categories", "Categories and subcategories", {}),
    ("seed_brands", "Brands", {}),
    ("seed_catalog", "Collections and the base taxonomy", {}),
    ("seed_products", "Products, variants, images, specs, attributes", {}),
    ("seed_coupons", "Discount coupons", {}),
    ("seed_banners", "Homepage banners", {}),
    ("seed_users", "Customers and addresses", {}),
    ("seed_orders", "Orders, items, payments, shipments, refunds", {}),
    ("seed_reviews", "Reviews, review images, helpful votes", {}),
    ("seed_engagement", "Wishlists, carts, notifications", {}),
    ("seed_recommendations", "Browsing trails, affinities, homepage rails", {}),
]

#: Per-scale volumes. Products drive everything downstream, so the ratios
#: between these are what keep a small run coherent rather than a catalogue
#: with five products and three thousand reviews.
SCALES: dict[str, dict[str, int]] = {
    "small":  {"products": 60,  "users": 40,  "orders": 120,  "reviews": 200},
    "medium": {"products": 200, "users": 100, "orders": 500,  "reviews": 1200},
    "full":   {"products": 500, "users": 200, "orders": 1200, "reviews": 3000},
    "large":  {"products": 1500, "users": 600, "orders": 5000, "reviews": 12000},
}


class Command(BaseCommand):
    """Seed the entire database in one pass."""

    help = "Run every seed command in dependency order."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--scale",
            choices=sorted(SCALES),
            default="full",
            help="Volume preset. Default 'full' (500 products).",
        )
        parser.add_argument(
            "--products", type=int, default=0, help="Override the product count."
        )
        parser.add_argument(
            "--users", type=int, default=0, help="Override the customer count."
        )
        parser.add_argument(
            "--orders", type=int, default=0, help="Override the order count."
        )
        parser.add_argument(
            "--reviews", type=int, default=0, help="Override the review count."
        )
        parser.add_argument(
            "--assets-dir", default="", help="Image library root."
        )
        parser.add_argument(
            "--fetch-remote", action="store_true",
            help="Download http(s) manifest entries. Off by default.",
        )
        parser.add_argument(
            "--no-images", action="store_true", help="Skip all imagery."
        )
        parser.add_argument(
            "--generate-placeholders", action="store_true",
            help="Generate stand-in product images where the library has none.",
        )
        parser.add_argument(
            "--flush", action="store_true",
            help="Delete existing seeded data first. Destructive.",
        )
        parser.add_argument(
            "--only", default="",
            help="Comma-separated step names to run. Skips the rest.",
        )
        parser.add_argument(
            "--skip", default="",
            help="Comma-separated step names to skip.",
        )
        parser.add_argument(
            "--continue-on-error", action="store_true",
            help="Keep going when a step fails, instead of stopping.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the pipeline."""
        verbosity = options.get("verbosity", 1)
        scale = SCALES[options["scale"]]

        volumes = {
            "seed_products": options["products"] or scale["products"],
            "seed_users": options["users"] or scale["users"],
            "seed_orders": options["orders"] or scale["orders"],
            "seed_reviews": options["reviews"] or scale["reviews"],
        }

        only = {name.strip() for name in options["only"].split(",") if name.strip()}
        skip = {name.strip() for name in options["skip"].split(",") if name.strip()}

        # Image options only apply to the commands that accept them; passing
        # --assets-dir to seed_users would be a TypeError.
        image_aware = {"seed_products", "seed_banners", "seed_reviews"}
        image_options: dict[str, Any] = {}
        if options["assets_dir"]:
            image_options["assets_dir"] = options["assets_dir"]
        if options["fetch_remote"]:
            image_options["fetch_remote"] = True
        if options["no_images"]:
            image_options["no_images"] = True

        flushable = {
            "seed_products", "seed_banners", "seed_orders",
            "seed_reviews", "seed_engagement", "seed_recommendations",
        }

        started = time.monotonic()
        results: list[tuple[str, str, float]] = []

        for name, description, base in PIPELINE:
            if only and name not in only:
                continue
            if name in skip:
                results.append((name, "skipped", 0.0))
                continue

            call_options: dict[str, Any] = {"verbosity": verbosity, **base}
            if name in volumes:
                call_options["count"] = volumes[name]
            if name in image_aware:
                call_options.update(image_options)
            if name == "seed_products" and options["generate_placeholders"]:
                call_options["generate_placeholders"] = True
            if options["flush"] and name in flushable:
                call_options["flush"] = True

            if verbosity:
                self.stdout.write("")
                self.stdout.write(
                    self.style.MIGRATE_HEADING(f"→ {name}  —  {description}")
                )

            step_started = time.monotonic()
            try:
                call_command(name, **call_options)
            except Exception as exc:  # noqa: BLE001 - reported, then re-raised
                elapsed = time.monotonic() - step_started
                results.append((name, f"FAILED: {exc}", elapsed))
                if not options["continue_on_error"]:
                    self._summarise(results, time.monotonic() - started)
                    raise CommandError(
                        f"{name} failed: {exc}\n"
                        "Fix the cause and re-run — completed steps are "
                        "idempotent and will be skipped."
                    ) from exc
                self.stdout.write(self.style.ERROR(f"  {name} failed: {exc}"))
            else:
                results.append((name, "ok", time.monotonic() - step_started))

        self._summarise(results, time.monotonic() - started)

        if verbosity:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Database seeded."))
            self._print_totals()

    def _summarise(self, results: list[tuple[str, str, float]], elapsed: float) -> None:
        """Print a per-step timing table."""
        self.stdout.write("")
        self.stdout.write("Pipeline summary:")
        for name, status, seconds in results:
            marker = {"ok": "  ok  ", "skipped": " skip "}.get(status, " FAIL ")
            self.stdout.write(f"  [{marker}] {name:<24} {seconds:6.1f}s  "
                              f"{'' if status in {'ok', 'skipped'} else status}")
        self.stdout.write(f"  total {elapsed:.1f}s")

    def _print_totals(self) -> None:
        """Print the row count of every seeded table."""
        from apps.banner.models import Banner
        from apps.cart.models import Cart, CartItem
        from apps.catalog.models import Brand, Category, Collection, SubCategory
        from apps.coupons.models import Coupon, CouponUsage
        from apps.notifications.models import Notification
        from apps.orders.models import Order, OrderItem, Shipment
        from apps.payments.models import Payment, Refund
        from apps.products.models import (
            Product, ProductAttribute, ProductImage, ProductSpecification, ProductVariant,
        )
        from apps.recommendations.models import ProductAffinity, RecentlyViewed
        from apps.reviews.models import Review, ReviewImage
        from apps.users.models import Address, User
        from apps.wishlist.models import WishlistItem

        rows = [
            ("Categories", Category), ("Subcategories", SubCategory),
            ("Brands", Brand), ("Collections", Collection),
            ("Products", Product), ("Product variants", ProductVariant),
            ("Product images", ProductImage),
            ("Product attributes", ProductAttribute),
            ("Product specs", ProductSpecification),
            ("Customers", User), ("Addresses", Address),
            ("Coupons", Coupon), ("Coupon usages", CouponUsage),
            ("Orders", Order), ("Order items", OrderItem),
            ("Shipments", Shipment), ("Payments", Payment), ("Refunds", Refund),
            ("Reviews", Review), ("Review images", ReviewImage),
            ("Wishlist items", WishlistItem),
            ("Carts", Cart), ("Cart items", CartItem),
            ("Recently viewed", RecentlyViewed),
            ("Product affinities", ProductAffinity),
            ("Notifications", Notification), ("Banners", Banner),
        ]

        self.stdout.write("")
        self.stdout.write("Row counts:")
        for label, model in rows:
            self.stdout.write(f"  {label:<20} {model.objects.count():>8,}")
