"""Seed homepage banners across every placement."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.banner.models import Banner, BannerPlacement
from apps.core.seed_assets import AssetLibrary, close_all

#: One realistic campaign per slot, plus a hero carousel of three. Written out
#: rather than generated so the seeded homepage reads like a real store instead
#: of "Banner 1, Banner 2, Banner 3".
BANNERS: list[dict[str, Any]] = [
    {
        "title": "The Festive Edit",
        "subtitle": "Handcrafted lehengas, sarees and sherwanis for wedding season",
        "placement": BannerPlacement.HERO,
        "button_text": "Shop Festive",
        "button_link": "/collections/festive",
        "alt_text": "Model wearing an embroidered festive lehenga",
        "folder": "banners/hero",
    },
    {
        "title": "New Season, New Silhouettes",
        "subtitle": "Spring/Summer 2026 has landed",
        "placement": BannerPlacement.HERO,
        "button_text": "Explore New In",
        "button_link": "/collections/new-arrivals",
        "alt_text": "Two models in spring-summer co-ord sets",
        "folder": "banners/hero",
    },
    {
        "title": "Up to 50% Off Denim",
        "subtitle": "Every fit, every wash — while stock lasts",
        "placement": BannerPlacement.HERO,
        "button_text": "Shop Denim",
        "button_link": "/products?material=denim",
        "alt_text": "Folded stack of denim jeans in assorted washes",
        "folder": "banners/sale",
    },
    {
        "title": "Free Shipping Over Rs. 999",
        "subtitle": "On every order, every day",
        "placement": BannerPlacement.STRIP,
        "button_text": "Start Shopping",
        "button_link": "/products",
        "alt_text": "Delivery box with a ribbon",
        "folder": "banners/strip",
    },
    {
        "title": "Ethnic Wear",
        "subtitle": "Rooted in craft, cut for today",
        "placement": BannerPlacement.GRID_LEFT,
        "button_text": "Discover",
        "button_link": "/categories/ethnic-wear",
        "alt_text": "Detail of hand-block-printed fabric",
        "folder": "banners/category",
    },
    {
        "title": "Everyday Essentials",
        "subtitle": "The basics you actually reach for",
        "placement": BannerPlacement.GRID_RIGHT,
        "button_text": "Shop Basics",
        "button_link": "/collections/best-sellers",
        "alt_text": "Neutral-toned folded t-shirts",
        "folder": "banners/category",
    },
    {
        "title": "Winter Warmers",
        "subtitle": "Knitwear, jackets and layers",
        "placement": BannerPlacement.CATEGORY_TOP,
        "button_text": "Shop Winterwear",
        "button_link": "/categories/winterwear",
        "alt_text": "Model in an oversized wool coat",
        "folder": "banners/category",
    },
    {
        "title": "Download the App",
        "subtitle": "Extra 10% off your first app order",
        "placement": BannerPlacement.FOOTER,
        "button_text": "Get the App",
        "button_link": "/app",
        "alt_text": "Phone displaying the Fashion Trendz app",
        "folder": "banners/strip",
    },
]


class Command(BaseCommand):
    """Create or update homepage banners."""

    help = "Seed homepage banners for every placement."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--flush", action="store_true", help="Delete existing banners first."
        )
        parser.add_argument(
            "--no-images", action="store_true", help="Create rows without imagery."
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

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed banners, rolling back entirely on any error."""
        verbosity = options.get("verbosity", 1)

        if options["flush"]:
            deleted, _ = Banner.objects.all().delete()
            if verbosity:
                self.stdout.write(self.style.WARNING(f"Deleted {deleted} banner(s)."))

        library = AssetLibrary(
            options["assets_dir"] or None, fetch_remote=options["fetch_remote"]
        )
        now = timezone.now()
        created = updated = 0
        opened: list = []
        order_by_placement: dict[str, int] = {}

        for spec in BANNERS:
            placement = spec["placement"]
            order_by_placement[placement] = order_by_placement.get(placement, 0) + 1

            defaults: dict[str, Any] = {
                "subtitle": spec["subtitle"],
                "placement": placement,
                "alt_text": spec["alt_text"],
                "button_text": spec["button_text"],
                "button_link": spec["button_link"],
                "display_order": order_by_placement[placement],
                "is_active": True,
                # Backdated so every seeded banner is live immediately; an
                # open-ended window means no end date to expire.
                "starts_at": now - timezone.timedelta(days=1),
                "ends_at": None,
            }

            banner, was_created = Banner.objects.get_or_create(
                title=spec["title"], placement=placement, defaults=defaults
            )
            if not was_created:
                for field, value in defaults.items():
                    setattr(banner, field, value)

            # Imagery only on first creation, so a re-run does not overwrite
            # artwork a merchandiser has since replaced.
            if not options["no_images"] and not banner.image:
                folder = spec.get("folder", "banners/hero")
                desktop = library.image_for(folder=folder, key=spec["title"])
                mobile = library.image_for(
                    folder=folder, key=f"{spec['title']}-mobile"
                )
                if desktop:
                    banner.image = desktop
                    opened.append(desktop)
                if mobile:
                    banner.mobile_image = mobile
                    opened.append(mobile)

            # Saved whether or not artwork was found. blank=False on an
            # ImageField is form validation, not a database constraint, and the
            # serializer renders an empty file as null — so the layout can still
            # be verified and the gap stays visible rather than being papered
            # over with a generated placeholder.
            banner.save()
            created += was_created
            updated += not was_created

        close_all(opened)

        if verbosity:
            self.stdout.write(f"Assets: {library.summary()}")
            for warning in library.warnings():
                self.stdout.write(
                    self.style.WARNING(f"  no images found in seed_assets/{warning}")
                )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Banners: {created} created, {updated} updated "
                    f"(total {Banner.objects.count()}, "
                    f"{Banner.objects.live().count()} live)."
                )
            )
