"""Seed discount coupons across every type and validity state."""

from __future__ import annotations

import random
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Brand, Category
from apps.coupons.models import Coupon

#: Written out rather than generated, so the seeded coupon list reads like a
#: real promotions calendar. Includes expired and future coupons deliberately:
#: the validation path is only exercised when something fails it.
COUPONS: list[dict[str, Any]] = [
    {"code": "WELCOME200", "discount_type": "flat", "value": "200.00",
     "min_cart_value": "999.00", "first_order_only": True,
     "description": "Flat Rs. 200 off your first order."},
    {"code": "TRENDZ10", "discount_type": "percentage", "value": "10.00",
     "max_discount": "500.00", "min_cart_value": "1499.00",
     "description": "10% off, up to Rs. 500."},
    {"code": "FESTIVE25", "discount_type": "percentage", "value": "25.00",
     "max_discount": "1500.00", "min_cart_value": "2999.00",
     "description": "Festive season: 25% off, up to Rs. 1500."},
    {"code": "FREESHIP", "discount_type": "free_shipping", "value": "0.00",
     "min_cart_value": "499.00", "description": "Free shipping on orders over Rs. 499."},
    {"code": "BIGSPEND1000", "discount_type": "flat", "value": "1000.00",
     "min_cart_value": "4999.00", "description": "Rs. 1000 off orders over Rs. 4999."},
    {"code": "ETHNIC15", "discount_type": "percentage", "value": "15.00",
     "max_discount": "1200.00", "min_cart_value": "1999.00",
     "categories": ["Ethnic Wear", "Women"],
     "description": "15% off ethnic wear."},
    {"code": "MENS20", "discount_type": "percentage", "value": "20.00",
     "max_discount": "900.00", "min_cart_value": "1499.00",
     "categories": ["Men"], "description": "20% off menswear."},
    {"code": "LUXE5", "discount_type": "percentage", "value": "5.00",
     "max_discount": "3000.00", "min_cart_value": "9999.00",
     "categories": ["Luxury"], "description": "5% off luxury, up to Rs. 3000."},
    {"code": "WEEKEND300", "discount_type": "flat", "value": "300.00",
     "min_cart_value": "1799.00", "uses_per_user": 2,
     "description": "Weekend special: Rs. 300 off."},
    {"code": "APPONLY150", "discount_type": "flat", "value": "150.00",
     "min_cart_value": "799.00", "is_public": False,
     "description": "App-exclusive Rs. 150 off."},
    {"code": "SUMMER30", "discount_type": "percentage", "value": "30.00",
     "max_discount": "2000.00", "min_cart_value": "3499.00",
     "description": "End-of-summer clearance.", "state": "expired"},
    {"code": "NEWYEAR26", "discount_type": "percentage", "value": "26.00",
     "max_discount": "2600.00", "min_cart_value": "2599.00",
     "description": "New Year 2026 preview.", "state": "future"},
    {"code": "SPENT2K", "discount_type": "flat", "value": "500.00",
     "min_cart_value": "2000.00", "max_uses": 500,
     "description": "Rs. 500 off, first 500 customers."},
    {"code": "STUDENT12", "discount_type": "percentage", "value": "12.00",
     "max_discount": "600.00", "min_cart_value": "999.00", "is_public": False,
     "description": "Verified student discount."},
    {"code": "COMEBACK400", "discount_type": "flat", "value": "400.00",
     "min_cart_value": "1999.00", "is_public": False,
     "description": "Win-back offer for lapsed customers."},
]


class Command(BaseCommand):
    """Create or update the coupon roster."""

    help = "Seed discount coupons."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--seed", type=int, default=20260804, help="Random seed, for reproducibility."
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed coupons, rolling back entirely on any error."""
        verbosity = options.get("verbosity", 1)
        rng = random.Random(options["seed"])
        now = timezone.now()

        by_category = {category.name: category for category in Category.objects.all()}
        brands = list(Brand.objects.filter(is_active=True)[:6])

        created = updated = 0

        for spec in COUPONS:
            state = spec.get("state", "live")
            if state == "expired":
                valid_from = now - timezone.timedelta(days=120)
                valid_until = now - timezone.timedelta(days=30)
            elif state == "future":
                valid_from = now + timezone.timedelta(days=20)
                valid_until = now + timezone.timedelta(days=80)
            else:
                valid_from = now - timezone.timedelta(days=rng.randint(5, 60))
                valid_until = now + timezone.timedelta(days=rng.randint(20, 180))

            coupon, was_created = Coupon.objects.update_or_create(
                code=spec["code"],
                defaults={
                    "description": spec["description"],
                    "discount_type": spec["discount_type"],
                    "value": Decimal(spec["value"]),
                    "max_discount": (
                        Decimal(spec["max_discount"]) if spec.get("max_discount") else None
                    ),
                    "min_cart_value": Decimal(spec.get("min_cart_value", "0.00")),
                    "max_uses": spec.get("max_uses", 0),
                    "uses_per_user": spec.get("uses_per_user", 1),
                    "is_active": state != "expired",
                    "is_public": spec.get("is_public", True),
                    "first_order_only": spec.get("first_order_only", False),
                    "valid_from": valid_from,
                    "valid_until": valid_until,
                },
            )
            created += was_created
            updated += not was_created

            # Scope is set rather than added, so a re-run with a changed spec
            # does not leave stale category links behind.
            scoped = [
                by_category[name]
                for name in spec.get("categories", [])
                if name in by_category
            ]
            coupon.categories.set(scoped)
            coupon.brands.set(brands if spec["code"] == "LUXE5" else [])

        if verbosity:
            live = Coupon.objects.filter(
                is_active=True, valid_from__lte=now, valid_until__gt=now
            ).count()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Coupons: {created} created, {updated} updated "
                    f"(total {Coupon.objects.count()}, {live} live)."
                )
            )
