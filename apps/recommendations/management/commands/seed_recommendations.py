"""Seed browsing trails and the co-purchase graph.

Two halves:

* **Recently viewed** — synthetic browsing history. Written directly rather
  than through ``record_view`` so the trail can be backdated; the service
  stamps ``viewed_at`` with ``auto_now``, which would date every row today and
  make "customers also viewed" read from a single instant.

* **Product affinities** — not invented at all. The existing
  ``rebuild_affinities`` service derives them from real order history, so this
  command calls it. Fabricating co-purchase edges would put pairs on the
  "frequently bought together" rail that no customer has ever bought together,
  which is precisely the claim that rail is not allowed to make.

Trending, best-seller and new-arrival flags are recomputed from the seeded
engagement counters rather than assigned at random, so the homepage rails agree
with the products they promote.
"""

from __future__ import annotations

import random
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.products.models import Product
from apps.recommendations.models import ProductAffinity, RecentlyViewed
from apps.recommendations.scoring import invalidate_store_mean, score_products
from apps.recommendations.services import rebuild_affinities
from apps.users.models import User


class Command(BaseCommand):
    """Populate recently-viewed trails, affinities and merchandising flags."""

    help = "Seed browsing history, co-purchase affinities and homepage rails."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--trail-rate", type=float, default=0.7,
            help="Share of customers with a browsing trail. Default 0.7.",
        )
        parser.add_argument(
            "--max-trail", type=int, default=18,
            help="Longest browsing trail per customer. The model caps at 30.",
        )
        parser.add_argument(
            "--guest-trails", type=int, default=150,
            help="How many anonymous session trails to create.",
        )
        parser.add_argument(
            "--skip-affinities", action="store_true",
            help="Skip the co-purchase rebuild, which is the slowest step.",
        )
        parser.add_argument(
            "--seed", type=int, default=20260804, help="Random seed, for reproducibility."
        )
        parser.add_argument(
            "--flush", action="store_true", help="Delete existing trails first."
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed recommendation inputs, rolling back entirely on any error."""
        verbosity = options.get("verbosity", 1)
        rng = random.Random(options["seed"])

        products = list(Product.objects.filter(is_active=True).only("id")[:600])
        customers = list(User.objects.filter(is_staff=False, is_active=True).only("id"))

        if not products:
            raise CommandError("No products found. Run seed_products first.")

        if options["flush"]:
            RecentlyViewed.objects.all().delete()
            ProductAffinity.objects.all().delete()
            if verbosity:
                self.stdout.write(self.style.WARNING("Cleared recommendation tables."))

        trails = self._seed_user_trails(
            customers, products, rng, options["trail_rate"], options["max_trail"]
        )
        guest = self._seed_guest_trails(
            products, rng, options["guest_trails"], options["max_trail"]
        )
        views = self._seed_view_counts(products, rng)

        affinities = 0
        if not options["skip_affinities"]:
            result = rebuild_affinities()
            affinities = result["edges"]

        flags = self._refresh_merchandising_flags()
        invalidate_store_mean()

        if verbosity:
            self.stdout.write(self.style.SUCCESS("Recommendations seeded:"))
            self.stdout.write(f"  customer trails  {trails}")
            self.stdout.write(f"  guest trails     {guest}")
            self.stdout.write(f"  trail rows       {RecentlyViewed.objects.count()}")
            self.stdout.write(f"  view counters    {views} products")
            self.stdout.write(f"  affinity edges   {affinities}")
            for label, value in flags.items():
                self.stdout.write(f"  {label:<16} {value}")
            if options["skip_affinities"]:
                self.stdout.write(
                    self.style.WARNING(
                        "  affinities skipped: 'frequently bought together' will be empty"
                    )
                )

    # -- parts --------------------------------------------------------------

    def _seed_user_trails(
        self,
        customers: list[User],
        products: list[Product],
        rng: random.Random,
        rate: float,
        maximum: int,
    ) -> int:
        """Give customers a backdated browsing trail."""
        seeded = 0
        now = timezone.now()

        for customer in customers:
            # Per customer, so the same people have trails on every run. A
            # shared stream made the decision depend on call order, and a
            # re-run gave trails to customers that had none — growing the table
            # toward every customer on each pass.
            picker = random.Random(f"trail:{customer.pk}")
            if picker.random() > rate:
                continue
            if RecentlyViewed.objects.filter(user=customer).exists():
                continue

            chosen = picker.sample(
                products, k=min(picker.randint(3, maximum), len(products))
            )
            rows = [
                RecentlyViewed(
                    user=customer,
                    session_key="",
                    product=product,
                    view_count=picker.randint(1, 5),
                )
                for product in chosen
            ]
            RecentlyViewed.objects.bulk_create(rows, ignore_conflicts=True)

            # viewed_at is auto_now, so bulk_create stamps every row with the
            # same instant. Backdating with UPDATE gives the rail an order.
            for offset, row in enumerate(
                RecentlyViewed.objects.filter(user=customer).order_by("id")
            ):
                RecentlyViewed.objects.filter(pk=row.pk).update(
                    viewed_at=now - timezone.timedelta(
                        hours=offset * picker.randint(2, 20)
                    )
                )
            seeded += 1
        return seeded

    def _seed_guest_trails(
        self,
        products: list[Product],
        rng: random.Random,
        count: int,
        maximum: int,
    ) -> int:
        """Create anonymous session trails.

        Guest traffic is most of a storefront's browsing, and "customers also
        viewed" reads both. A trail owned by a session carries an empty user,
        which the exclusive-or CHECK on the table requires.
        """
        seeded = 0
        now = timezone.now()

        for index in range(count):
            # Deterministic. A random suffix would mint a brand-new trail on
            # every run instead of colliding with the previous one, so the
            # table would double in size each time the seed was re-run.
            session_key = f"seedguest{index:06d}"
            if RecentlyViewed.objects.filter(session_key=session_key).exists():
                continue

            picker = random.Random(f"guest:{index}")
            chosen = picker.sample(
                products, k=min(picker.randint(2, maximum), len(products))
            )
            RecentlyViewed.objects.bulk_create(
                [
                    RecentlyViewed(
                        user=None,
                        session_key=session_key,
                        product=product,
                        view_count=picker.randint(1, 3),
                    )
                    for product in chosen
                ],
                ignore_conflicts=True,
            )
            for offset, row in enumerate(
                RecentlyViewed.objects.filter(session_key=session_key).order_by("id")
            ):
                RecentlyViewed.objects.filter(pk=row.pk).update(
                    viewed_at=now - timezone.timedelta(
                        hours=offset * picker.randint(1, 12)
                    )
                )
            seeded += 1
        return seeded

    def _seed_view_counts(
        self, products: list[Product], rng: random.Random
    ) -> int:
        """Give products a plausible view counter.

        Long-tailed rather than uniform: a real catalogue has a handful of
        products with tens of thousands of views and a long tail with a few
        dozen. A uniform distribution makes the trending score meaningless
        because every product scores the same.
        """
        updated = 0
        for product in products:
            # Per product, so a product keeps its popularity across runs and the
            # trending rail does not reshuffle on every seed.
            picker = random.Random(f"views:{product.pk}")
            if picker.random() < 0.05:
                views = picker.randint(8_000, 60_000)   # the hits
            elif picker.random() < 0.25:
                views = picker.randint(800, 8_000)      # the middle
            else:
                views = picker.randint(10, 800)         # the tail
            Product.objects.filter(pk=product.pk).update(view_count=views)
            updated += 1
        return updated

    def _refresh_merchandising_flags(self) -> dict[str, int]:
        """Recompute the homepage rail flags from the seeded counters.

        Derived, not random: a product flagged trending that nobody has viewed
        makes the rail a lie, and the trending score already knows how to rank.
        """
        # Clear first, so a re-run does not accumulate flags.
        Product.objects.update(
            is_trending=False, is_best_seller=False, is_featured=False
        )

        trending_ids = list(
            score_products(Product.objects.filter(is_active=True))
            .order_by("-trending_score")
            .values_list("id", flat=True)[:40]
        )
        Product.objects.filter(pk__in=trending_ids).update(is_trending=True)

        best_seller_ids = list(
            Product.objects.filter(is_active=True, purchase_count__gt=0)
            .order_by("-purchase_count")
            .values_list("id", flat=True)[:40]
        )
        Product.objects.filter(pk__in=best_seller_ids).update(is_best_seller=True)

        featured_ids = list(
            Product.objects.filter(is_active=True, rating_count__gte=3)
            .order_by("-rating_average", "-purchase_count")
            .values_list("id", flat=True)[:30]
        )
        Product.objects.filter(pk__in=featured_ids).update(is_featured=True)

        cutoff = timezone.now() - timezone.timedelta(days=45)
        new_arrivals = Product.objects.filter(
            is_active=True, published_at__gte=cutoff
        ).update(is_new_arrival=True)

        return {
            "trending": len(trending_ids),
            "best sellers": len(best_seller_ids),
            "featured": len(featured_ids),
            "new arrivals": new_arrivals,
        }
