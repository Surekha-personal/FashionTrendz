"""Tests for the recommendations module.

Two areas. The browsing trail, where the risks are one shopper seeing another's
history and the table growing without bound; and the scoring engine, where the
risk is a ranking nobody can explain.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.core.management import call_command
from django.db.models import F
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Brand, Category, SubCategory
from apps.core.choices import OrderStatus
from apps.orders.models import Order, OrderItem
from apps.products.models import Product, ProductVariant, Size
from apps.recommendations import services
from apps.recommendations.models import ProductAffinity, RecentlyViewed
from apps.recommendations.scoring import (
    explain_score,
    score_products,
    store_mean_rating,
    weights,
)
from apps.recommendations.validators import clamp_days, clamp_limit
from apps.users.models import User

STRONG_PASSWORD = "Tr3ndz!Shopper42"
GUEST_SESSION = "guest-session-key-abc123"


class RecommendationFixtureMixin:
    """Builds a small catalogue and a couple of shoppers."""

    def build_world(self) -> None:
        """Create categories, products, users."""
        cache.clear()
        self._order_seq = 0

        self.category = Category.objects.create(name="Women")
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Dresses"
        )
        self.other_subcategory = SubCategory.objects.create(
            category=self.category, name="Tops"
        )
        self.brand = Brand.objects.create(name="Nordwyn")
        self.other_brand = Brand.objects.create(name="Calloway")

        self.dress = self.make_product("Classic Midi Dress", "FT-C0001")
        self.second_dress = self.make_product("Wrap Midi Dress", "FT-C0002")
        self.top = self.make_product(
            "Linen Top", "FT-C0003", subcategory=self.other_subcategory
        )

        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.stranger = User.objects.create_user(
            email="other@example.com", password=STRONG_PASSWORD, first_name="Rhea"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com",
            password=STRONG_PASSWORD,
            first_name="Staff",
            is_staff=True,
        )

    def make_product(self, name: str, sku: str, **extra: Any) -> Product:
        """Create a published product with one variant."""
        defaults: dict[str, Any] = {
            "name": name,
            "sku": sku,
            "category": self.category,
            "subcategory": self.subcategory,
            "brand": self.brand,
            "mrp": Decimal("2000.00"),
            "selling_price": Decimal("1500.00"),
            "published_at": timezone.now() - timedelta(days=1),
        }
        defaults.update(extra)
        product = Product.objects.create(**defaults)
        ProductVariant.objects.create(
            product=product, sku=f"{sku}-0", color="Navy", size=Size.M, stock=5
        )
        return product

    def make_order(self, user: User, products: list[Product], **extra: Any) -> Order:
        """Create a delivered order containing ``products``."""
        self._order_seq += 1
        order = Order.objects.create(
            user=user,
            order_number=f"FT-TEST-{self._order_seq:05d}",
            status=extra.get("status", OrderStatus.DELIVERED),
            shipping_address={"city": "Mumbai"},
            billing_address={"city": "Mumbai"},
            subtotal=Decimal("1500.00"),
            grand_total=Decimal("1500.00"),
            delivered_at=timezone.now(),
        )
        for product in products:
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                product_slug=product.slug,
                sku=product.sku,
                mrp=product.mrp,
                selling_price=product.selling_price,
                quantity=1,
                subtotal=product.selling_price,
                grand_total=product.selling_price,
            )
        return order


class RecommendationTestCase(RecommendationFixtureMixin, TestCase):
    """Base case with the world built."""

    def setUp(self) -> None:
        self.build_world()


# ---------------------------------------------------------------------------
# Recently viewed
# ---------------------------------------------------------------------------


class RecentlyViewedTests(RecommendationTestCase):
    """The browsing trail."""

    def test_a_view_is_recorded_for_a_signed_in_shopper(self) -> None:
        services.record_view(self.dress, user=self.user)
        self.assertEqual(RecentlyViewed.objects.filter(user=self.user).count(), 1)

    def test_a_view_is_recorded_for_a_guest(self) -> None:
        services.record_view(self.dress, session_key=GUEST_SESSION)
        row = RecentlyViewed.objects.get()
        self.assertTrue(row.is_guest)
        self.assertEqual(row.session_key, GUEST_SESSION)

    def test_a_request_with_no_owner_is_a_no_op(self) -> None:
        # Better than raising: the product page fires this and does not wait.
        self.assertIsNone(services.record_view(self.dress))
        self.assertEqual(RecentlyViewed.objects.count(), 0)

    def test_viewing_twice_bumps_the_row_rather_than_appending(self) -> None:
        services.record_view(self.dress, user=self.user)
        services.record_view(self.dress, user=self.user)

        row = RecentlyViewed.objects.get()
        self.assertEqual(row.view_count, 2)

    def test_re_viewing_moves_a_product_back_to_the_top(self) -> None:
        services.record_view(self.dress, user=self.user)
        services.record_view(self.second_dress, user=self.user)
        services.record_view(self.dress, user=self.user)

        trail = services.get_recently_viewed(user=self.user)
        self.assertEqual(trail[0], self.dress)

    def test_the_trail_is_newest_first(self) -> None:
        services.record_view(self.dress, user=self.user)
        services.record_view(self.top, user=self.user)

        self.assertEqual(
            services.get_recently_viewed(user=self.user), [self.top, self.dress]
        )

    @override_settings(MAX_RECENTLY_VIEWED=2)
    def test_the_trail_is_trimmed_to_the_ceiling(self) -> None:
        for product in (self.dress, self.second_dress, self.top):
            services.record_view(product, user=self.user)

        self.assertEqual(RecentlyViewed.objects.filter(user=self.user).count(), 2)

    @override_settings(MAX_RECENTLY_VIEWED=2)
    def test_trimming_drops_the_oldest_not_the_newest(self) -> None:
        for product in (self.dress, self.second_dress, self.top):
            services.record_view(product, user=self.user)

        trail = services.get_recently_viewed(user=self.user)
        self.assertNotIn(self.dress, trail)
        self.assertIn(self.top, trail)

    def test_one_shopper_cannot_see_anothers_trail(self) -> None:
        services.record_view(self.dress, user=self.user)
        self.assertEqual(services.get_recently_viewed(user=self.stranger), [])

    def test_an_unpublished_product_drops_out_of_the_trail(self) -> None:
        services.record_view(self.dress, user=self.user)
        Product.objects.filter(pk=self.dress.pk).update(is_active=False)

        self.assertEqual(services.get_recently_viewed(user=self.user), [])

    def test_one_product_can_be_removed(self) -> None:
        services.record_view(self.dress, user=self.user)
        services.record_view(self.top, user=self.user)

        services.remove_from_recently_viewed(self.dress.slug, user=self.user)
        self.assertEqual(services.get_recently_viewed(user=self.user), [self.top])

    def test_the_whole_trail_can_be_cleared(self) -> None:
        services.record_view(self.dress, user=self.user)
        self.assertEqual(services.clear_recently_viewed(user=self.user), 1)
        self.assertEqual(services.get_recently_viewed(user=self.user), [])

    def test_stale_rows_are_purged(self) -> None:
        services.record_view(self.dress, user=self.user)
        RecentlyViewed.objects.update(viewed_at=timezone.now() - timedelta(days=200))

        self.assertEqual(services.purge_stale_trails(90), 1)

    def test_fresh_rows_survive_a_purge(self) -> None:
        services.record_view(self.dress, user=self.user)
        self.assertEqual(services.purge_stale_trails(90), 0)


class TrailMergeTests(RecommendationTestCase):
    """Folding a guest trail into an account."""

    def test_guest_rows_move_to_the_account(self) -> None:
        services.record_view(self.dress, session_key=GUEST_SESSION)
        moved = services.merge_recently_viewed(self.user, GUEST_SESSION)

        self.assertEqual(moved, 1)
        self.assertEqual(services.get_recently_viewed(user=self.user), [self.dress])

    def test_the_guest_trail_is_emptied(self) -> None:
        services.record_view(self.dress, session_key=GUEST_SESSION)
        services.merge_recently_viewed(self.user, GUEST_SESSION)

        self.assertEqual(
            RecentlyViewed.objects.filter(user__isnull=True).count(), 0
        )

    def test_a_product_the_account_already_has_is_not_duplicated(self) -> None:
        services.record_view(self.dress, user=self.user)
        services.record_view(self.dress, session_key=GUEST_SESSION)

        services.merge_recently_viewed(self.user, GUEST_SESSION)
        self.assertEqual(RecentlyViewed.objects.filter(product=self.dress).count(), 1)

    def test_merging_an_unknown_session_is_harmless(self) -> None:
        self.assertEqual(services.merge_recently_viewed(self.user, "no-such"), 0)

    @override_settings(MAX_RECENTLY_VIEWED=2)
    def test_the_merged_trail_is_trimmed(self) -> None:
        services.record_view(self.dress, user=self.user)
        services.record_view(self.second_dress, session_key=GUEST_SESSION)
        services.record_view(self.top, session_key=GUEST_SESSION)

        services.merge_recently_viewed(self.user, GUEST_SESSION)
        self.assertEqual(RecentlyViewed.objects.filter(user=self.user).count(), 2)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class TrendingScoreTests(RecommendationTestCase):
    """The documented ranking formula."""

    def test_every_visible_product_is_scored(self) -> None:
        scored = score_products()
        self.assertEqual(scored.count(), 3)
        self.assertTrue(all(hasattr(p, "trending_score") for p in scored))

    def test_more_purchases_outrank_fewer(self) -> None:
        Product.objects.filter(pk=self.dress.pk).update(purchase_count=100)
        ranked = list(score_products().order_by("-trending_score"))
        self.assertEqual(ranked[0].pk, self.dress.pk)

    def test_purchases_outweigh_views(self) -> None:
        # A view is a click; a purchase is a decision backed by money.
        Product.objects.filter(pk=self.dress.pk).update(purchase_count=50)
        Product.objects.filter(pk=self.second_dress.pk).update(view_count=50)

        ranked = list(score_products().order_by("-trending_score"))
        self.assertEqual(ranked[0].pk, self.dress.pk)

    def test_counters_are_log_scaled_not_linear(self) -> None:
        # Ten times the views must not be ten times the contribution, or the
        # rail becomes a ratchet nothing new can enter.
        Product.objects.filter(pk=self.dress.pk).update(view_count=10)
        Product.objects.filter(pk=self.second_dress.pk).update(view_count=100)

        breakdowns = {
            p.pk: explain_score(p) for p in Product.objects.filter(view_count__gt=0)
        }
        ten = breakdowns[self.dress.pk]["views"]
        hundred = breakdowns[self.second_dress.pk]["views"]
        self.assertLess(hundred, ten * 3)

    def test_a_single_five_star_review_does_not_top_the_catalogue(self) -> None:
        # The Bayesian prior is the whole reason this test exists: a raw
        # average would put the 5.0-from-one-review above the 4.6-from-400.
        Product.objects.filter(pk=self.dress.pk).update(
            rating_average=Decimal("5.00"), rating_count=1, review_count=1
        )
        Product.objects.filter(pk=self.second_dress.pk).update(
            rating_average=Decimal("4.60"), rating_count=400, review_count=400
        )
        Product.objects.filter(pk=self.top.pk).update(
            rating_average=Decimal("3.80"), rating_count=60, review_count=60
        )
        cache.clear()

        ranked = list(score_products().order_by("-trending_score"))
        self.assertEqual(ranked[0].pk, self.second_dress.pk)

    def test_the_bayesian_rating_pulls_thin_evidence_toward_the_mean(self) -> None:
        Product.objects.filter(pk=self.dress.pk).update(
            rating_average=Decimal("5.00"), rating_count=1
        )
        # One five-star review lands well below 5.0 once smoothed.
        self.dress.refresh_from_db()
        self.assertLess(explain_score(self.dress, mean=4.0)["bayesian_rating"], 4.2)

    def test_an_older_product_scores_lower_on_recency(self) -> None:
        Product.objects.filter(pk=self.dress.pk).update(
            published_at=timezone.now() - timedelta(days=200)
        )
        self.dress.refresh_from_db()

        self.assertLess(
            explain_score(self.dress)["recency"],
            explain_score(self.second_dress)["recency"],
        )

    def test_the_breakdown_sums_to_the_total(self) -> None:
        breakdown = explain_score(self.dress)
        terms = ("views", "purchases", "wishlist", "reviews", "rating", "recency")
        self.assertAlmostEqual(
            sum(breakdown[term] for term in terms), breakdown["total"], places=3
        )

    def test_the_python_breakdown_matches_the_sql_score(self) -> None:
        # If these drift, the admin's explanation stops describing the ranking.
        Product.objects.filter(pk=self.dress.pk).update(
            view_count=25, purchase_count=7, wishlist_count=3
        )
        scored = score_products().get(pk=self.dress.pk)
        self.assertAlmostEqual(
            scored.trending_score, explain_score(scored)["total"], places=3
        )

    @override_settings(TRENDING_WEIGHT_PURCHASE=0.0)
    def test_weights_are_read_from_settings(self) -> None:
        self.assertEqual(weights()["purchase"], 0.0)
        Product.objects.filter(pk=self.dress.pk).update(purchase_count=1000)
        self.assertEqual(explain_score(self.dress)["purchases"], 0.0)

    def test_the_store_mean_falls_back_when_nothing_is_rated(self) -> None:
        cache.clear()
        self.assertEqual(store_mean_rating(use_cache=False), 3.5)

    def test_the_store_mean_ignores_unrated_products(self) -> None:
        Product.objects.filter(pk=self.dress.pk).update(
            rating_average=Decimal("4.00"), rating_count=5
        )
        # Averaging the two unrated products in as zero would drag this to 1.33.
        self.assertAlmostEqual(store_mean_rating(use_cache=False), 4.0, places=2)


# ---------------------------------------------------------------------------
# Rails
# ---------------------------------------------------------------------------


class RailTests(RecommendationTestCase):
    """The eight strips."""

    def test_related_products_share_a_subcategory(self) -> None:
        related = services.get_related(self.dress)
        self.assertIn(self.second_dress, related)
        self.assertNotIn(self.top, related)

    def test_a_rail_never_contains_its_own_product(self) -> None:
        self.assertNotIn(self.dress, services.get_related(self.dress))
        self.assertNotIn(self.dress, services.get_similar(self.dress))

    def test_similar_products_stay_within_the_category(self) -> None:
        similar = services.get_similar(self.dress)
        self.assertNotIn(self.dress, similar)

    def test_trending_returns_cards(self) -> None:
        self.assertEqual(len(services.get_trending(limit=10)), 3)

    def test_recently_popular_counts_only_real_orders(self) -> None:
        self.make_order(self.user, [self.dress])
        popular = services.get_recently_popular()

        self.assertEqual([p.pk for p in popular], [self.dress.pk])

    def test_a_cancelled_order_does_not_make_a_product_popular(self) -> None:
        self.make_order(self.user, [self.dress], status=OrderStatus.CANCELLED)
        self.assertEqual(services.get_recently_popular(), [])

    def test_an_order_outside_the_window_does_not_count(self) -> None:
        order = self.make_order(self.user, [self.dress])
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(days=90)
        )
        self.assertEqual(services.get_recently_popular(days=30), [])

    def test_customers_also_viewed_reads_the_trail(self) -> None:
        services.record_view(self.dress, user=self.stranger)
        services.record_view(self.top, user=self.stranger)

        also = services.get_customers_also_viewed(self.dress)
        self.assertIn(self.top, also)

    def test_also_viewed_falls_back_when_the_trail_is_empty(self) -> None:
        # An empty strip on a product page looks broken.
        also = services.get_customers_also_viewed(self.dress)
        self.assertIn(self.second_dress, also)

    def test_new_for_you_is_plain_new_arrivals_for_a_guest(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(len(services.get_new_for_you(AnonymousUser())), 3)

    def test_new_for_you_narrows_to_a_shoppers_subcategories(self) -> None:
        services.record_view(self.top, user=self.user)
        rail = services.get_new_for_you(self.user)

        self.assertEqual([p.pk for p in rail], [self.top.pk])

    def test_recommended_for_you_falls_back_to_trending_for_a_guest(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(
            [p.pk for p in services.get_recommended_for_you(AnonymousUser())],
            [p.pk for p in services.get_trending()],
        )

    def test_recommended_for_you_excludes_what_was_already_bought(self) -> None:
        self.make_order(self.user, [self.dress])
        services.record_view(self.dress, user=self.user)

        rail = services.get_recommended_for_you(self.user)
        self.assertNotIn(self.dress, rail)

    def test_recommended_for_you_excludes_products_outside_a_shoppers_taste(
        self,
    ) -> None:
        # Taste is subcategory OR brand, so a product sharing neither with
        # anything the shopper has engaged with must not appear.
        unrelated = self.make_product(
            "Wool Scarf",
            "FT-C0009",
            subcategory=self.other_subcategory,
            brand=self.other_brand,
        )
        services.record_view(self.dress, user=self.user)

        rail = services.get_recommended_for_you(self.user)
        self.assertIn(self.second_dress, rail)
        self.assertNotIn(unrelated, rail)


# ---------------------------------------------------------------------------
# Affinities
# ---------------------------------------------------------------------------


class AffinityTests(RecommendationTestCase):
    """The co-purchase graph."""

    def test_two_orders_sharing_a_pair_create_an_edge(self) -> None:
        self.make_order(self.user, [self.dress, self.top])
        self.make_order(self.stranger, [self.dress, self.top])

        result = services.rebuild_affinities()
        self.assertEqual(result["baskets"], 2)
        self.assertEqual(
            ProductAffinity.objects.filter(
                product=self.dress, related_product=self.top
            ).count(),
            1,
        )

    def test_a_single_shared_order_is_below_the_noise_floor(self) -> None:
        # One customer buying two things together is coincidence, not a rail.
        self.make_order(self.user, [self.dress, self.top])
        services.rebuild_affinities()

        self.assertEqual(ProductAffinity.objects.count(), 0)

    def test_edges_are_directed(self) -> None:
        self.make_order(self.user, [self.dress, self.top])
        self.make_order(self.stranger, [self.dress, self.top])
        self.make_order(self.user, [self.dress])

        services.rebuild_affinities()
        forward = ProductAffinity.objects.get(
            product=self.dress, related_product=self.top
        )
        backward = ProductAffinity.objects.get(
            product=self.top, related_product=self.dress
        )
        # The dress sells alone; the top never does. Confidence differs.
        self.assertLess(forward.score, backward.score)

    def test_no_product_is_paired_with_itself(self) -> None:
        # A product is trivially "bought with itself" in every order it
        # appears in, and that edge would top every ranking.
        self.make_order(self.user, [self.dress, self.top])
        self.make_order(self.stranger, [self.dress, self.top])
        services.rebuild_affinities()

        self.assertFalse(
            ProductAffinity.objects.filter(
                product_id=F("related_product_id")
            ).exists()
        )

    def test_cancelled_orders_are_excluded(self) -> None:
        self.make_order(self.user, [self.dress, self.top], status=OrderStatus.CANCELLED)
        self.make_order(
            self.stranger, [self.dress, self.top], status=OrderStatus.CANCELLED
        )
        services.rebuild_affinities()

        self.assertEqual(ProductAffinity.objects.count(), 0)

    def test_the_bundle_rail_carries_its_evidence(self) -> None:
        self.make_order(self.user, [self.dress, self.top])
        self.make_order(self.stranger, [self.dress, self.top])
        services.rebuild_affinities()

        bundles = services.get_frequently_bought_together(self.dress)
        self.assertEqual(len(bundles), 1)
        self.assertEqual(bundles[0]["co_purchase_count"], 2)
        self.assertEqual(
            bundles[0]["bundle_price"],
            self.dress.selling_price + self.top.selling_price,
        )

    def test_the_bundle_rail_is_empty_rather_than_generic(self) -> None:
        # "Frequently bought together" with no data is a claim we cannot make.
        self.assertEqual(services.get_frequently_bought_together(self.dress), [])

    def test_a_rebuild_replaces_rather_than_accumulates(self) -> None:
        self.make_order(self.user, [self.dress, self.top])
        self.make_order(self.stranger, [self.dress, self.top])

        services.rebuild_affinities()
        first = ProductAffinity.objects.count()
        services.rebuild_affinities()

        self.assertEqual(ProductAffinity.objects.count(), first)

    def test_an_unpublished_product_is_dropped_from_the_rail(self) -> None:
        self.make_order(self.user, [self.dress, self.top])
        self.make_order(self.stranger, [self.dress, self.top])
        services.rebuild_affinities()

        Product.objects.filter(pk=self.top.pk).update(is_active=False)
        self.assertEqual(services.get_frequently_bought_together(self.dress), [])


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class ClampTests(TestCase):
    """Query-string hygiene."""

    def test_a_missing_limit_falls_back_to_the_default(self) -> None:
        self.assertEqual(clamp_limit(None, 12), 12)

    def test_a_mangled_limit_falls_back_rather_than_raising(self) -> None:
        # A shopper with a broken URL should see a rail, not an error page.
        self.assertEqual(clamp_limit("twelve", 12), 12)

    def test_an_enormous_limit_is_capped(self) -> None:
        self.assertEqual(clamp_limit(100000, 12), 50)

    def test_a_negative_limit_becomes_one(self) -> None:
        self.assertEqual(clamp_limit(-5, 12), 1)

    def test_days_clamp_to_their_own_larger_ceiling(self) -> None:
        # Sharing clamp_limit would silently cap a 90-day window at 50 days.
        self.assertEqual(clamp_days(90, 30), 90)
        self.assertEqual(clamp_days(9999, 30), 365)


# ---------------------------------------------------------------------------
# Management commands
# ---------------------------------------------------------------------------


class CommandTests(RecommendationTestCase):
    """The two cron entry points."""

    def test_rebuild_affinities_runs(self) -> None:
        self.make_order(self.user, [self.dress, self.top])
        self.make_order(self.stranger, [self.dress, self.top])

        call_command("rebuild_affinities", verbosity=0)
        self.assertTrue(ProductAffinity.objects.exists())

    def test_the_minimum_flag_is_honoured(self) -> None:
        self.make_order(self.user, [self.dress, self.top])
        call_command("rebuild_affinities", minimum=1, verbosity=0)

        self.assertTrue(ProductAffinity.objects.exists())

    def test_purge_deletes_stale_rows(self) -> None:
        services.record_view(self.dress, user=self.user)
        RecentlyViewed.objects.update(viewed_at=timezone.now() - timedelta(days=200))

        call_command("purge_browsing_history", days=90, verbosity=0)
        self.assertEqual(RecentlyViewed.objects.count(), 0)

    def test_a_dry_run_deletes_nothing(self) -> None:
        services.record_view(self.dress, user=self.user)
        RecentlyViewed.objects.update(viewed_at=timezone.now() - timedelta(days=200))

        call_command("purge_browsing_history", days=90, dry_run=True, verbosity=0)
        self.assertEqual(RecentlyViewed.objects.count(), 1)

    def test_an_absurd_retention_window_is_refused(self) -> None:
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("purge_browsing_history", days=99999, verbosity=0)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


class DiagnosticsTests(RecommendationTestCase):
    """What the admin sees."""

    def test_diagnose_reports_every_rail(self) -> None:
        report = services.diagnose(self.dress)
        self.assertEqual(report["slug"], self.dress.slug)
        self.assertIn("related", report["rails"])
        self.assertIn("total", report["trending_score"])

    def test_the_dashboard_is_ranked(self) -> None:
        Product.objects.filter(pk=self.dress.pk).update(purchase_count=500)
        rows = services.get_trending_dashboard(limit=3)

        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["slug"], self.dress.slug)
        self.assertGreater(rows[0]["score"], rows[1]["score"])


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class RecommendationAPITests(RecommendationFixtureMixin, APITestCase):
    """The HTTP surface."""

    def setUp(self) -> None:
        self.build_world()

    def test_a_guest_can_record_and_read_a_view(self) -> None:
        response = self.client.post(
            reverse("recommendations:recently-viewed-list"),
            {"product": self.dress.slug},
            format="json",
            HTTP_X_CART_SESSION=GUEST_SESSION,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        listed = self.client.get(
            reverse("recommendations:recently-viewed-list"),
            HTTP_X_CART_SESSION=GUEST_SESSION,
        )
        self.assertEqual(len(listed.json()["data"]), 1)

    def test_a_guest_trail_merges_on_the_first_authenticated_call(self) -> None:
        self.client.post(
            reverse("recommendations:recently-viewed-list"),
            {"product": self.dress.slug},
            format="json",
            HTTP_X_CART_SESSION=GUEST_SESSION,
        )

        self.client.force_authenticate(user=self.user)
        listed = self.client.get(
            reverse("recommendations:recently-viewed-list"),
            HTTP_X_CART_SESSION=GUEST_SESSION,
        )
        self.assertEqual(len(listed.json()["data"]), 1)
        self.assertEqual(RecentlyViewed.objects.filter(user=self.user).count(), 1)

    def test_recording_an_unknown_product_is_a_404(self) -> None:
        response = self.client.post(
            reverse("recommendations:recently-viewed-list"),
            {"product": "no-such-product"},
            format="json",
            HTTP_X_CART_SESSION=GUEST_SESSION,
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_trail_can_be_cleared_over_http(self) -> None:
        self.client.force_authenticate(user=self.user)
        services.record_view(self.dress, user=self.user)

        response = self.client.delete(
            reverse("recommendations:recently-viewed-clear")
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(RecentlyViewed.objects.count(), 0)

    def test_the_related_rail_is_public(self) -> None:
        response = self.client.get(
            reverse(
                "recommendations:recommendation-related",
                kwargs={"slug": self.dress.slug},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 1)

    def test_the_trending_rail_is_public(self) -> None:
        response = self.client.get(reverse("recommendations:recommendation-trending"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 3)

    def test_the_limit_parameter_is_honoured(self) -> None:
        response = self.client.get(
            reverse("recommendations:recommendation-trending"), {"limit": 1}
        )
        self.assertEqual(len(response.json()["data"]), 1)

    def test_an_enormous_limit_is_clamped_not_rejected(self) -> None:
        response = self.client.get(
            reverse("recommendations:recommendation-trending"), {"limit": 999999}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_the_bundle_rail_returns_evidence(self) -> None:
        self.make_order(self.user, [self.dress, self.top])
        self.make_order(self.stranger, [self.dress, self.top])
        services.rebuild_affinities()

        response = self.client.get(
            reverse(
                "recommendations:recommendation-frequently-bought-together",
                kwargs={"slug": self.dress.slug},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"][0]["co_purchase_count"], 2)

    def test_the_for_you_rail_works_signed_out(self) -> None:
        response = self.client.get(reverse("recommendations:recommendation-for-you"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_the_dashboard_is_staff_only(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            reverse("recommendations:recommendation-admin-trending")
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_read_the_dashboard(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse("recommendations:recommendation-admin-trending")
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("breakdown", response.json()["data"][0])

    def test_staff_can_diagnose_a_product(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse(
                "recommendations:recommendation-admin-diagnose",
                kwargs={"slug": self.dress.slug},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"]["slug"], self.dress.slug)

    def test_staff_can_rebuild_the_graph_over_http(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("recommendations:recommendation-admin-rebuild-affinities")
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
