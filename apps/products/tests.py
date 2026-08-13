"""Tests for the products module.

Covers pricing arithmetic, stock invariants, the primary-image rule, the
managers, the service layer, search, filters, every public endpoint, the
permission boundary and the seed command.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Brand, Category, Collection, CollectionType, SubCategory
from apps.core.choices import StockStatus
from apps.products import services
from apps.products.models import (
    LOW_STOCK_THRESHOLD,
    Material,
    Occasion,
    Product,
    ProductImage,
    ProductSpecification,
    ProductTag,
    ProductVariant,
    Size,
)
from apps.users.models import User

STRONG_PASSWORD = "Tr3ndz!Shopper42"


class ProductFixtureMixin:
    """Builds the taxonomy and product rows the tests share."""

    def build_taxonomy(self) -> None:
        """Create one category, subcategory, brand and collection."""
        self.category = Category.objects.create(name="Women", is_active=True)
        self.other_category = Category.objects.create(name="Men", display_order=2)
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Dresses"
        )
        self.other_subcategory = SubCategory.objects.create(
            category=self.other_category, name="Shirts"
        )
        self.brand = Brand.objects.create(name="Nordwyn", country="Denmark")
        self.luxury_brand = Brand.objects.create(name="Roux Atelier", is_luxury=True)
        self.collection = Collection.objects.create(
            title="Editor's Picks", type=CollectionType.EDITORS_PICKS
        )

    def make_product(self, name: str = "Classic Midi Dress", **extra: Any) -> Product:
        """Create a published, active product."""
        defaults: dict[str, Any] = {
            "name": name,
            "sku": extra.pop("sku", f"FT-{abs(hash(name)) % 100000:05d}"),
            "category": self.category,
            "subcategory": self.subcategory,
            "brand": self.brand,
            "mrp": Decimal("2000.00"),
            "selling_price": Decimal("1500.00"),
            "published_at": timezone.now() - timezone.timedelta(days=1),
        }
        defaults.update(extra)
        return Product.objects.create(**defaults)

    def make_variant(self, product: Product, **extra: Any) -> ProductVariant:
        """Create a variant with stock."""
        defaults: dict[str, Any] = {
            "product": product,
            "sku": extra.pop("sku", f"{product.sku}-{ProductVariant.objects.count()}"),
            "color": "Navy",
            "size": Size.M,
            "stock": 10,
        }
        defaults.update(extra)
        return ProductVariant.objects.create(**defaults)


class ProductTestCase(ProductFixtureMixin, TestCase):
    """Base case that clears the cache and builds the taxonomy."""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.build_taxonomy()


# ---------------------------------------------------------------------------
# Model: pricing
# ---------------------------------------------------------------------------


class PricingTests(ProductTestCase):
    """Derived discount fields."""

    def test_discount_is_derived_from_mrp_and_selling_price(self) -> None:
        product = self.make_product(
            mrp=Decimal("2000.00"), selling_price=Decimal("1500.00")
        )
        self.assertEqual(product.discount_amount, Decimal("500.00"))
        self.assertEqual(product.discount_percentage, Decimal("25.00"))

    def test_no_discount_when_prices_are_equal(self) -> None:
        product = self.make_product(
            mrp=Decimal("999.00"), selling_price=Decimal("999.00")
        )
        self.assertEqual(product.discount_percentage, Decimal("0.00"))
        self.assertFalse(product.is_on_sale)

    def test_discount_recomputes_when_the_price_changes(self) -> None:
        product = self.make_product()
        product.selling_price = Decimal("1000.00")
        product.save()
        self.assertEqual(product.discount_percentage, Decimal("50.00"))

    def test_selling_price_above_mrp_is_rejected_by_the_database(self) -> None:
        # The check constraint is the real guard: a bulk import bypasses forms.
        with self.assertRaises(IntegrityError):
            self.make_product(
                name="Broken", mrp=Decimal("100.00"), selling_price=Decimal("500.00")
            )

    def test_tax_amount_is_computed_from_the_selling_price(self) -> None:
        product = self.make_product(
            selling_price=Decimal("1000.00"), tax_percentage=Decimal("18.00")
        )
        self.assertEqual(product.tax_amount, Decimal("180.00"))

    def test_prices_are_quantised_to_two_places(self) -> None:
        product = self.make_product(
            mrp=Decimal("1999.999"), selling_price=Decimal("999.994")
        )
        self.assertEqual(product.mrp, Decimal("2000.00"))
        self.assertEqual(product.selling_price, Decimal("999.99"))


# ---------------------------------------------------------------------------
# Model: slugs, visibility
# ---------------------------------------------------------------------------


class ProductModelTests(ProductTestCase):
    """Slugs, publication and visibility."""

    def test_slug_is_brand_prefixed(self) -> None:
        self.assertEqual(
            self.make_product("Linen Shirt").slug, "nordwyn-linen-shirt"
        )

    def test_same_name_from_two_brands_does_not_collide(self) -> None:
        first = self.make_product("Linen Shirt", sku="FT-A0001")
        second = self.make_product(
            "Linen Shirt", sku="FT-A0002", brand=self.luxury_brand
        )
        self.assertNotEqual(first.slug, second.slug)
        self.assertEqual(second.slug, "roux-atelier-linen-shirt")

    def test_sku_is_unique(self) -> None:
        self.make_product("A", sku="FT-DUP01")
        with self.assertRaises(IntegrityError):
            self.make_product("B", sku="FT-DUP01")

    def test_unpublished_product_is_not_visible(self) -> None:
        self.make_product("Draft", published_at=None)
        self.assertEqual(Product.objects.visible().count(), 0)

    def test_future_publication_is_not_visible_yet(self) -> None:
        self.make_product(
            "Embargoed", published_at=timezone.now() + timezone.timedelta(days=3)
        )
        self.assertEqual(Product.objects.visible().count(), 0)

    def test_deactivating_a_category_hides_its_products(self) -> None:
        self.make_product("Visible")
        self.assertEqual(Product.objects.visible().count(), 1)

        self.category.is_active = False
        self.category.save(update_fields=["is_active"])
        self.assertEqual(Product.objects.visible().count(), 0)

    def test_category_with_products_cannot_be_deleted(self) -> None:
        from django.db.models import ProtectedError

        self.make_product()
        with self.assertRaises(ProtectedError):
            self.category.delete()


# ---------------------------------------------------------------------------
# Model: stock
# ---------------------------------------------------------------------------


class StockTests(ProductTestCase):
    """Variant stock and the cached product figures."""

    def setUp(self) -> None:
        super().setUp()
        self.product = self.make_product()

    def test_product_starts_out_of_stock(self) -> None:
        self.assertEqual(self.product.total_stock, 0)
        self.assertEqual(self.product.stock_status, StockStatus.OUT_OF_STOCK)

    def test_adding_a_variant_updates_cached_stock(self) -> None:
        self.make_variant(self.product, stock=25)
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 25)
        self.assertEqual(self.product.stock_status, StockStatus.IN_STOCK)

    def test_available_stock_excludes_reservations(self) -> None:
        variant = self.make_variant(self.product, stock=10, reserved_stock=4)
        self.assertEqual(variant.available_stock, 6)

        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 6)

    def test_low_stock_status_is_derived(self) -> None:
        self.make_variant(self.product, stock=LOW_STOCK_THRESHOLD)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_status, StockStatus.LOW_STOCK)

    def test_fully_reserved_variant_is_out_of_stock(self) -> None:
        self.make_variant(self.product, stock=5, reserved_stock=5)
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 0)
        self.assertFalse(self.product.is_in_stock)

    def test_reserving_more_than_stock_is_rejected(self) -> None:
        with self.assertRaises(IntegrityError):
            self.make_variant(self.product, stock=3, reserved_stock=9)

    def test_deleting_a_variant_updates_cached_stock(self) -> None:
        variant = self.make_variant(self.product, stock=40)
        variant.delete()
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 0)

    def test_inactive_variants_do_not_count(self) -> None:
        self.make_variant(self.product, stock=100, is_active=False)
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 0)

    def test_duplicate_colour_size_is_rejected(self) -> None:
        self.make_variant(self.product, color="Navy", size=Size.M, sku="FT-V1")
        with self.assertRaises(IntegrityError):
            self.make_variant(self.product, color="Navy", size=Size.M, sku="FT-V2")

    def test_variant_price_override(self) -> None:
        variant = self.make_variant(
            self.product, price_override=Decimal("1899.00")
        )
        self.assertEqual(variant.effective_price, Decimal("1899.00"))

    def test_variant_without_override_uses_the_product_price(self) -> None:
        variant = self.make_variant(self.product)
        self.assertEqual(variant.effective_price, self.product.selling_price)


# ---------------------------------------------------------------------------
# Model: images
# ---------------------------------------------------------------------------


class ProductImageTests(ProductTestCase):
    """The single-primary-image invariant."""

    def setUp(self) -> None:
        super().setUp()
        self.product = self.make_product()

    def add_image(self, order: int = 0, primary: bool = False) -> ProductImage:
        """Create an image row without touching storage."""
        return ProductImage.objects.create(
            product=self.product,
            image=f"products/images/test-{order}.jpg",
            display_order=order,
            is_primary=primary,
        )

    def test_first_image_becomes_primary_automatically(self) -> None:
        image = self.add_image()
        image.refresh_from_db()
        self.assertTrue(image.is_primary)

    def test_second_image_is_not_primary(self) -> None:
        self.add_image(0)
        second = self.add_image(1)
        second.refresh_from_db()
        self.assertFalse(second.is_primary)

    def test_promoting_an_image_demotes_the_previous_primary(self) -> None:
        first = self.add_image(0)
        second = self.add_image(1)

        second.is_primary = True
        second.save()

        first.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(ProductImage.objects.get(pk=second.pk).is_primary)

    def test_only_one_primary_survives_a_direct_update(self) -> None:
        self.add_image(0)
        second = self.add_image(1)
        # Prove the guarantee lives in the database, not only in Python.
        with self.assertRaises(IntegrityError):
            ProductImage.objects.filter(pk=second.pk).update(is_primary=True)

    def test_deleting_the_primary_promotes_another(self) -> None:
        first = self.add_image(0)
        second = self.add_image(1)

        first.delete()
        second.refresh_from_db()
        self.assertTrue(second.is_primary)

    def test_alt_text_falls_back_to_the_product_name(self) -> None:
        self.assertEqual(self.add_image().get_alt_text(), self.product.name)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------


class ManagerTests(ProductTestCase):
    """Queryset helpers."""

    def setUp(self) -> None:
        super().setUp()
        self.cheap = self.make_product(
            "Cheap Tee", sku="FT-M0001", mrp=Decimal("999.00"),
            selling_price=Decimal("499.00"), purchase_count=5, rating_average=Decimal("4.9"),
            rating_count=2,
        )
        self.pricey = self.make_product(
            "Silk Gown", sku="FT-M0002", mrp=Decimal("20000.00"),
            selling_price=Decimal("19000.00"), purchase_count=500,
            rating_average=Decimal("4.1"), rating_count=300, is_luxury=True,
        )

    def test_cheapest_and_most_expensive(self) -> None:
        self.assertEqual(Product.objects.cheapest().first(), self.cheap)
        self.assertEqual(Product.objects.most_expensive().first(), self.pricey)

    def test_on_sale_filter(self) -> None:
        self.assertIn(self.cheap, Product.objects.on_sale(50))
        self.assertNotIn(self.pricey, Product.objects.on_sale(50))

    def test_best_rated_requires_a_minimum_review_count(self) -> None:
        # 4.9 from two ratings must not outrank 4.1 from three hundred.
        self.assertEqual(Product.objects.best_rated().first(), self.pricey)

    def test_by_popularity_ranks_purchases_above_views(self) -> None:
        self.assertEqual(Product.objects.by_popularity().first(), self.pricey)

    def test_in_stock_filter(self) -> None:
        self.make_variant(self.cheap, stock=5)
        self.cheap.refresh_from_db()
        self.assertEqual(list(Product.objects.in_stock()), [self.cheap])

    def test_card_data_avoids_n_plus_one(self) -> None:
        for index in range(10):
            self.make_product(f"Extra {index}", sku=f"FT-N{index:04d}")

        # One query for products, one per prefetch — never one per row.
        with self.assertNumQueries(2):
            list(Product.objects.visible().with_card_data())


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


class ServiceTests(ProductTestCase):
    """Rails, related products, search and facets."""

    def setUp(self) -> None:
        super().setUp()
        self.featured = self.make_product(
            "Featured Dress", sku="FT-S0001", is_featured=True, purchase_count=90
        )
        self.discounted = self.make_product(
            "Half Price Dress", sku="FT-S0002",
            mrp=Decimal("4000.00"), selling_price=Decimal("1600.00"),
        )
        self.make_variant(self.discounted, stock=20)
        self.other = self.make_product(
            "Mens Shirt", sku="FT-S0003",
            category=self.other_category, subcategory=self.other_subcategory,
        )

    def test_featured_rail(self) -> None:
        self.assertIn(self.featured, services.get_featured_products())

    def test_flash_sale_requires_stock(self) -> None:
        # The discounted product has stock; a discounted product without any
        # must not appear, because an unbuyable sale item destroys trust.
        no_stock = self.make_product(
            "Sold Out Sale", sku="FT-S0004",
            mrp=Decimal("4000.00"), selling_price=Decimal("1200.00"),
        )
        results = list(services.get_flash_sale_products())
        self.assertIn(self.discounted, results)
        self.assertNotIn(no_stock, results)

    def test_new_arrivals_falls_back_when_nothing_is_flagged(self) -> None:
        Product.objects.update(is_new_arrival=False)
        self.assertTrue(services.get_new_arrivals().exists())

    def test_related_products_share_the_subcategory(self) -> None:
        related = list(services.get_related_products(self.featured))
        self.assertIn(self.discounted, related)
        self.assertNotIn(self.other, related)
        self.assertNotIn(self.featured, related)

    def test_similar_products_exclude_the_product_itself(self) -> None:
        self.assertNotIn(self.featured, services.get_similar_products(self.featured))

    def test_recently_viewed_preserves_the_given_order(self) -> None:
        order = [self.discounted.slug, self.featured.slug]
        self.assertEqual(
            [p.slug for p in services.get_recently_viewed(order)], order
        )

    def test_recently_viewed_drops_unknown_slugs(self) -> None:
        result = services.get_recently_viewed(["nope", self.featured.slug])
        self.assertEqual([p.slug for p in result], [self.featured.slug])

    def test_recently_viewed_is_capped(self) -> None:
        slugs = [f"slug-{i}" for i in range(200)]
        self.assertEqual(services.get_recently_viewed(slugs), [])

    def test_record_view_increments_atomically(self) -> None:
        before = self.featured.view_count
        services.record_product_view(self.featured)
        self.featured.refresh_from_db()
        self.assertEqual(self.featured.view_count, before + 1)

    def test_search_matches_name_and_brand(self) -> None:
        self.assertIn(self.featured, services.search_products("Featured"))
        self.assertIn(self.featured, services.search_products("Nordwyn"))

    def test_search_ranks_exact_matches_first(self) -> None:
        results = list(services.search_products("Featured Dress"))
        self.assertEqual(results[0], self.featured)

    def test_short_queries_return_nothing(self) -> None:
        self.assertEqual(services.search_products("a").count(), 0)

    def test_search_excludes_hidden_products(self) -> None:
        self.featured.is_active = False
        self.featured.save()
        self.assertNotIn(self.featured, services.search_products("Featured"))

    def test_suggestions_are_grouped(self) -> None:
        suggestions = services.get_search_suggestions("Nord")
        self.assertEqual(
            set(suggestions), {"products", "brands", "categories"}
        )
        self.assertTrue(suggestions["brands"])

    def test_facets_reflect_the_filtered_set(self) -> None:
        facets = services.get_filter_facets(
            services.visible_products().for_category("women")
        )
        brand_slugs = {row["slug"] for row in facets["brands"]}
        self.assertIn("nordwyn", brand_slugs)
        self.assertGreater(facets["price"]["max"], 0)

    def test_facet_colours_come_from_variants(self) -> None:
        facets = services.get_filter_facets()
        self.assertIn("Navy", {row["color"] for row in facets["colors"]})

    def test_apply_sort_falls_back_for_an_unknown_value(self) -> None:
        queryset = services.apply_sort(services.visible_products(), "nonsense")
        self.assertTrue(queryset.exists())

    def test_availability_matrix_groups_by_colour(self) -> None:
        self.make_variant(self.featured, color="Rust", size=Size.S, sku="FT-AV1")
        self.make_variant(self.featured, color="Rust", size=Size.M, sku="FT-AV2")
        matrix = services.get_variant_availability(self.featured)
        rust = next(c for c in matrix["colors"] if c["color"] == "Rust")
        self.assertEqual({s["size"] for s in rust["sizes"]}, {Size.S, Size.M})


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class ProductAPITestCase(ProductFixtureMixin, APITestCase):
    """Base case with products and both kinds of user."""

    def setUp(self) -> None:
        cache.clear()
        self.build_taxonomy()

        self.customer = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com", password=STRONG_PASSWORD,
            first_name="Staff", is_staff=True,
        )

        self.product = self.make_product(
            "Classic Midi Dress", sku="FT-A0001",
            is_featured=True, material=Material.LINEN, occasion=Occasion.CASUAL,
        )
        self.make_variant(self.product, color="Navy", size=Size.M, stock=12, sku="FT-A0001-0")
        self.make_variant(self.product, color="Rust", size=Size.L, stock=3, sku="FT-A0001-1")

        self.cheap = self.make_product(
            "Budget Tee", sku="FT-A0002",
            mrp=Decimal("999.00"), selling_price=Decimal("499.00"),
        )
        self.hidden = self.make_product("Draft Dress", sku="FT-A0003", is_active=False)


class ProductListAPITests(ProductAPITestCase):
    """/api/v1/products/"""

    def test_list_is_public(self) -> None:
        response = self.client.get(reverse("products:product-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_inactive_products_are_hidden_from_customers(self) -> None:
        body = self.client.get(reverse("products:product-list")).json()
        self.assertNotIn("Draft Dress", {row["name"] for row in body["data"]})

    def test_staff_see_inactive_products(self) -> None:
        self.client.force_authenticate(user=self.staff)
        body = self.client.get(reverse("products:product-list")).json()
        self.assertIn("Draft Dress", {row["name"] for row in body["data"]})

    def test_response_uses_the_core_envelope(self) -> None:
        body = self.client.get(reverse("products:product-list")).json()
        self.assertTrue(body["success"])
        self.assertIsInstance(body["data"], list)
        self.assertIn("pagination", body)

    def test_default_page_size_is_the_product_grid_size(self) -> None:
        body = self.client.get(reverse("products:product-list")).json()
        self.assertEqual(body["pagination"]["page_size"], 24)

    def test_page_size_is_clamped(self) -> None:
        body = self.client.get(
            reverse("products:product-list"), {"page_size": 100000}
        ).json()
        self.assertLessEqual(len(body["data"]), 96)

    def test_card_payload_excludes_the_long_description(self) -> None:
        body = self.client.get(reverse("products:product-list")).json()
        self.assertNotIn("long_description", body["data"][0])

    def test_filter_by_price_range(self) -> None:
        body = self.client.get(
            reverse("products:product-list"), {"max_price": "600"}
        ).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Budget Tee"])

    def test_filter_by_colour_returns_each_product_once(self) -> None:
        # The product has two variants; a join without distinct() duplicates it.
        body = self.client.get(
            reverse("products:product-list"), {"color": "Navy"}
        ).json()
        names = [row["name"] for row in body["data"]]
        self.assertEqual(names.count("Classic Midi Dress"), 1)

    def test_filter_by_size(self) -> None:
        body = self.client.get(reverse("products:product-list"), {"size": "L"}).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Classic Midi Dress"])

    def test_filter_by_material_and_brand(self) -> None:
        body = self.client.get(
            reverse("products:product-list"),
            {"material": Material.LINEN, "brand": "nordwyn"},
        ).json()
        self.assertEqual(len(body["data"]), 1)

    def test_filter_by_minimum_discount(self) -> None:
        body = self.client.get(
            reverse("products:product-list"), {"min_discount": "40"}
        ).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Budget Tee"])

    def test_filter_in_stock(self) -> None:
        body = self.client.get(
            reverse("products:product-list"), {"in_stock": "true"}
        ).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Classic Midi Dress"])

    def test_sort_price_low_to_high(self) -> None:
        body = self.client.get(
            reverse("products:product-list"), {"sort": "price_low"}
        ).json()
        self.assertEqual(body["data"][0]["name"], "Budget Tee")

    def test_sort_price_high_to_low(self) -> None:
        body = self.client.get(
            reverse("products:product-list"), {"sort": "price_high"}
        ).json()
        self.assertEqual(body["data"][0]["name"], "Classic Midi Dress")

    def test_unknown_sort_does_not_error(self) -> None:
        response = self.client.get(
            reverse("products:product-list"), {"sort": "by_vibes"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ProductDetailAPITests(ProductAPITestCase):
    """/api/v1/products/{slug}/"""

    def test_retrieve_by_slug(self) -> None:
        url = reverse("products:product-detail", args=[self.product.slug])
        body = self.client.get(url).json()
        self.assertEqual(body["data"]["name"], "Classic Midi Dress")

    def test_detail_includes_variants_and_availability(self) -> None:
        url = reverse("products:product-detail", args=[self.product.slug])
        data = self.client.get(url).json()["data"]
        self.assertEqual(len(data["variants"]), 2)
        self.assertIn("colors", data["availability"])

    def test_variant_payload_hides_raw_stock(self) -> None:
        url = reverse("products:product-detail", args=[self.product.slug])
        variant = self.client.get(url).json()["data"]["variants"][0]
        self.assertNotIn("stock", variant)
        self.assertIn("available_stock", variant)

    def test_retrieving_increments_the_view_counter(self) -> None:
        before = self.product.view_count
        self.client.get(reverse("products:product-detail", args=[self.product.slug]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.view_count, before + 1)

    def test_hidden_product_is_a_404_for_customers(self) -> None:
        url = reverse("products:product-detail", args=[self.hidden.slug])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_quick_view_endpoint(self) -> None:
        url = reverse("products:product-quick-view", args=[self.product.slug])
        data = self.client.get(url).json()["data"]
        self.assertIn("variants", data)
        self.assertNotIn("specifications", data)

    def test_related_and_similar_endpoints(self) -> None:
        for route in ("products:product-related", "products:product-similar"):
            url = reverse(route, args=[self.product.slug])
            self.assertEqual(
                self.client.get(url).status_code, status.HTTP_200_OK, msg=route
            )

    def test_availability_endpoint(self) -> None:
        url = reverse("products:product-availability", args=[self.product.slug])
        data = self.client.get(url).json()["data"]
        self.assertEqual({c["color"] for c in data["colors"]}, {"Navy", "Rust"})

    def test_recently_viewed_endpoint_preserves_order(self) -> None:
        url = reverse("products:product-recently-viewed")
        body = self.client.get(
            url, {"slugs": f"{self.cheap.slug},{self.product.slug}"}
        ).json()
        self.assertEqual(
            [row["slug"] for row in body["data"]],
            [self.cheap.slug, self.product.slug],
        )


class ProductRailAPITests(ProductAPITestCase):
    """Homepage rail endpoints."""

    def test_every_rail_endpoint_responds(self) -> None:
        for route in (
            "products:product-featured",
            "products:product-trending",
            "products:product-new-arrivals",
            "products:product-best-sellers",
            "products:product-luxury",
            "products:product-flash-sale",
            "products:product-editors-picks",
            "products:product-trending-this-week",
            "products:product-recommended",
            "products:product-recently-added",
        ):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=route)

    def test_featured_rail_contains_the_featured_product(self) -> None:
        body = self.client.get(reverse("products:product-featured")).json()
        self.assertIn("Classic Midi Dress", {row["name"] for row in body["data"]})

    def test_homepage_endpoint_returns_every_rail(self) -> None:
        body = self.client.get(reverse("products:product-homepage")).json()
        self.assertEqual(
            set(body["data"]),
            {
                "featured", "trending", "new_arrivals", "best_sellers", "luxury",
                "flash_sale", "editors_picks", "trending_this_week",
                "recommended", "recently_added",
            },
        )


class ProductSearchAPITests(ProductAPITestCase):
    """Search endpoints."""

    def test_search_returns_matches(self) -> None:
        body = self.client.get(
            reverse("products:product-search"), {"q": "Midi"}
        ).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Classic Midi Dress"])

    def test_search_uses_the_smaller_page_size(self) -> None:
        body = self.client.get(reverse("products:product-search"), {"q": "dress"}).json()
        self.assertEqual(body["pagination"]["page_size"], 20)

    def test_empty_query_returns_nothing_rather_than_everything(self) -> None:
        body = self.client.get(reverse("products:product-search"), {"q": ""}).json()
        self.assertEqual(body["data"], [])

    def test_suggestions_endpoint(self) -> None:
        body = self.client.get(
            reverse("products:product-suggestions"), {"q": "Nord"}
        ).json()
        self.assertIn("brands", body["data"])
        self.assertTrue(body["data"]["brands"])

    def test_search_defaults_endpoint(self) -> None:
        body = self.client.get(reverse("products:product-search-defaults")).json()
        self.assertIn("popular_products", body["data"])
        self.assertIn("trending_searches", body["data"])


class ProductFacetAPITests(ProductAPITestCase):
    """/api/v1/products/filters/"""

    def test_facets_endpoint(self) -> None:
        body = self.client.get(reverse("products:product-filters")).json()
        for key in ("price", "brands", "categories", "colors", "sizes"):
            self.assertIn(key, body["data"])

    def test_facets_respect_the_current_filters(self) -> None:
        # Filtering to the cheap product must not offer Navy, which only the
        # other product has — that is the point of computing facets per result set.
        body = self.client.get(
            reverse("products:product-filters"), {"max_price": "600"}
        ).json()
        self.assertEqual(body["data"]["colors"], [])


class ProductPermissionTests(ProductAPITestCase):
    """Only staff may modify the catalogue."""

    def payload(self) -> dict[str, Any]:
        """Return a valid create payload."""
        return {
            "name": "New Product",
            "sku": "FT-NEW01",
            "category": self.category.pk,
            "subcategory": self.subcategory.pk,
            "brand": self.brand.pk,
            "mrp": "1000.00",
            "selling_price": "800.00",
        }

    def test_anonymous_cannot_create(self) -> None:
        response = self.client.post(reverse("products:product-list"), self.payload())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_cannot_create(self) -> None:
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse("products:product-list"), self.payload())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(reverse("products:product-list"), self.payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_mismatched_taxonomy_is_rejected_with_a_field_error(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("products:product-list"),
            {**self.payload(), "subcategory": self.other_subcategory.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("subcategory", response.json()["errors"])

    def test_selling_price_above_mrp_is_rejected_with_a_field_error(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("products:product-list"),
            {**self.payload(), "selling_price": "5000.00"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("selling_price", response.json()["errors"])

    def test_low_stock_endpoint_is_staff_only(self) -> None:
        url = reverse("products:product-low-stock")
        self.assertEqual(
            self.client.get(url).status_code, status.HTTP_403_FORBIDDEN
        )

        self.client.force_authenticate(user=self.staff)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)


class ProductTagAPITests(ProductAPITestCase):
    """/api/v1/product-tags/"""

    def setUp(self) -> None:
        super().setUp()
        self.tag = ProductTag.objects.create(name="Linen Edit")
        self.product.tags.add(self.tag)

    def test_list_endpoint(self) -> None:
        body = self.client.get(reverse("products:product-tag-list")).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Linen Edit"])

    def test_products_for_a_tag(self) -> None:
        url = reverse("products:product-tag-products", args=[self.tag.slug])
        body = self.client.get(url).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Classic Midi Dress"])


# ---------------------------------------------------------------------------
# Seed command
# ---------------------------------------------------------------------------


class SeedProductsTests(TestCase):
    """The seed_products management command."""

    def setUp(self) -> None:
        cache.clear()

    def test_seeding_without_a_catalogue_fails_loudly(self) -> None:
        with self.assertRaises(CommandError):
            call_command("seed_products", count=5, verbosity=0)

    def test_seeding_creates_products_with_satellites(self) -> None:
        call_command("seed_catalog", verbosity=0)
        call_command("seed_products", count=40, verbosity=0)

        self.assertEqual(Product.objects.count(), 40)
        self.assertGreater(ProductVariant.objects.count(), 40)
        self.assertGreater(ProductSpecification.objects.count(), 40)

    def test_seeded_products_have_coherent_pricing(self) -> None:
        call_command("seed_catalog", verbosity=0)
        call_command("seed_products", count=40, verbosity=0)

        for product in Product.objects.all():
            self.assertLessEqual(product.selling_price, product.mrp)
            self.assertGreaterEqual(product.discount_percentage, Decimal("0"))

    def test_seeded_stock_matches_the_variants(self) -> None:
        call_command("seed_catalog", verbosity=0)
        call_command("seed_products", count=25, verbosity=0)

        for product in Product.objects.prefetch_related("variants"):
            self.assertEqual(product.total_stock, product.compute_stock())

    def test_seeding_is_idempotent(self) -> None:
        call_command("seed_catalog", verbosity=0)
        call_command("seed_products", count=30, verbosity=0)
        call_command("seed_products", count=30, verbosity=0)
        self.assertEqual(Product.objects.count(), 30)

    def test_seeded_catalogue_powers_the_homepage(self) -> None:
        call_command("seed_catalog", verbosity=0)
        call_command("seed_products", count=60, verbosity=0)

        payload = services.get_homepage_payload()
        self.assertTrue(payload["new_arrivals"].exists())
        self.assertTrue(payload["best_sellers"].exists())
