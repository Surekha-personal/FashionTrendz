"""Tests for the catalog module.

Covers the models and their slug rules, the managers, the service layer and its
cache, the serializers, every public endpoint, the permission boundary and the
seed command.
"""

from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
from django.db.utils import IntegrityError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog import services
from apps.catalog.models import (
    SEASONAL_COLLECTION_TYPES,
    Brand,
    Category,
    Collection,
    CollectionType,
    SubCategory,
)
from apps.catalog.serializers import CategoryDetailSerializer, CategorySerializer
from apps.catalog.utils import UploadPath
from apps.catalog.validators import validate_founded_year
from apps.users.models import User

STRONG_PASSWORD = "Tr3ndz!Shopper42"


def make_category(name: str = "Women", **extra: Any) -> Category:
    """Create a category with sensible defaults."""
    return Category.objects.create(name=name, **extra)


def make_subcategory(category: Category, name: str = "Dresses", **extra: Any) -> SubCategory:
    """Create a subcategory under ``category``."""
    return SubCategory.objects.create(category=category, name=name, **extra)


def make_brand(name: str = "Aarohi Couture", **extra: Any) -> Brand:
    """Create a brand with sensible defaults."""
    return Brand.objects.create(name=name, **extra)


def make_collection(title: str = "New Arrivals", **extra: Any) -> Collection:
    """Create a collection with sensible defaults."""
    extra.setdefault("type", CollectionType.NEW_ARRIVALS)
    return Collection.objects.create(title=title, **extra)


class CatalogTestCase(TestCase):
    """Base case that clears the catalog cache between tests."""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CategoryModelTests(CatalogTestCase):
    """Category slugs, ordering and counts."""

    def test_slug_is_generated_from_the_name(self) -> None:
        self.assertEqual(make_category("Women's Ethnic").slug, "womens-ethnic")

    def test_supplied_slug_is_respected(self) -> None:
        self.assertEqual(make_category("Women", slug="w").slug, "w")

    def test_colliding_names_get_distinct_slugs(self) -> None:
        first = make_category("Sale")
        second = Category.objects.create(name="Sale!")
        self.assertNotEqual(first.slug, second.slug)

    def test_name_is_unique(self) -> None:
        make_category("Women")
        with self.assertRaises(IntegrityError):
            Category.objects.create(name="Women")

    def test_default_ordering_is_display_order_then_name(self) -> None:
        make_category("Zebra", display_order=1)
        make_category("Alpha", display_order=2)
        self.assertEqual(
            [c.name for c in Category.objects.all()], ["Zebra", "Alpha"]
        )

    def test_subcategory_count_ignores_inactive_children(self) -> None:
        category = make_category()
        make_subcategory(category, "Dresses")
        make_subcategory(category, "Sarees", is_active=False)
        self.assertEqual(category.active_subcategory_count, 1)

    def test_uuid_and_timestamps_come_from_the_core_mixin(self) -> None:
        category = make_category()
        self.assertIsNotNone(category.uuid)
        self.assertIsNotNone(category.created_at)
        self.assertIsNotNone(category.updated_at)


class SubCategoryModelTests(CatalogTestCase):
    """Subcategory slug scoping and uniqueness."""

    def setUp(self) -> None:
        super().setUp()
        self.women = make_category("Women")
        self.kids = make_category("Kids")

    def test_slug_is_prefixed_with_the_parent_name(self) -> None:
        self.assertEqual(make_subcategory(self.women, "Dresses").slug, "women-dresses")

    def test_same_name_under_two_parents_yields_readable_slugs(self) -> None:
        # The reason slugs are parent-scoped: neither needs a random suffix.
        self.assertEqual(make_subcategory(self.women, "Dresses").slug, "women-dresses")
        self.assertEqual(make_subcategory(self.kids, "Dresses").slug, "kids-dresses")

    def test_duplicate_name_within_one_parent_is_rejected(self) -> None:
        make_subcategory(self.women, "Dresses")
        with self.assertRaises(IntegrityError):
            SubCategory.objects.create(category=self.women, name="Dresses")

    def test_str_includes_the_parent(self) -> None:
        self.assertEqual(str(make_subcategory(self.women, "Dresses")), "Women / Dresses")

    def test_is_visible_requires_an_active_parent(self) -> None:
        sub = make_subcategory(self.women, "Dresses")
        self.assertTrue(sub.is_visible)

        self.women.is_active = False
        self.women.save(update_fields=["is_active"])
        sub.refresh_from_db()
        self.assertFalse(sub.is_visible)

    def test_deleting_a_category_removes_its_children(self) -> None:
        make_subcategory(self.women, "Dresses")
        self.women.delete()
        self.assertEqual(SubCategory.objects.count(), 0)


class BrandModelTests(CatalogTestCase):
    """Brand slugs and validation."""

    def test_slug_is_generated_from_the_name(self) -> None:
        self.assertEqual(make_brand("Casa Marbella").slug, "casa-marbella")

    def test_name_is_unique(self) -> None:
        make_brand("Nordwyn")
        with self.assertRaises(IntegrityError):
            Brand.objects.create(name="Nordwyn")

    def test_founded_year_rejects_the_future(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_founded_year(9999)

    def test_founded_year_rejects_an_implausible_past(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_founded_year(1092)

    def test_founded_year_accepts_a_heritage_house(self) -> None:
        validate_founded_year(1854)


class CollectionModelTests(CatalogTestCase):
    """Collection slugs and seasonal classification."""

    def test_slug_is_generated_from_the_title(self) -> None:
        self.assertEqual(make_collection("Editor's Picks").slug, "editors-picks")

    def test_seasonal_flag_matches_the_type(self) -> None:
        self.assertTrue(make_collection("Summer", type=CollectionType.SUMMER).is_seasonal)
        self.assertFalse(
            make_collection("Trending", type=CollectionType.TRENDING).is_seasonal
        )

    def test_seasonal_set_holds_only_season_driven_types(self) -> None:
        self.assertNotIn(CollectionType.TRENDING, SEASONAL_COLLECTION_TYPES)
        self.assertIn(CollectionType.WEDDING, SEASONAL_COLLECTION_TYPES)


class UploadPathTests(SimpleTestCase):
    """Upload paths discard the client filename."""

    def test_client_filename_is_replaced_by_a_uuid(self) -> None:
        path = UploadPath("catalog/test")("instance", "../../etc/passwd.png")
        self.assertTrue(path.startswith("catalog/test/"))
        self.assertTrue(path.endswith(".png"))
        self.assertNotIn("passwd", path)
        self.assertNotIn("..", path)

    def test_two_uploads_of_the_same_name_do_not_collide(self) -> None:
        builder = UploadPath("catalog/test")
        self.assertNotEqual(builder(None, "a.png"), builder(None, "a.png"))

    def test_instances_compare_equal_so_migrations_do_not_churn(self) -> None:
        self.assertEqual(UploadPath("catalog/x"), UploadPath("catalog/x"))


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------


class ManagerTests(CatalogTestCase):
    """Queryset helpers."""

    def setUp(self) -> None:
        super().setUp()
        self.women = make_category("Women", is_featured=True, is_trending=True)
        self.luxury = make_category("Luxury", is_luxury=True, display_order=2)
        self.hidden = make_category("Hidden", is_active=False)

    def test_active_excludes_deactivated_rows(self) -> None:
        self.assertNotIn(self.hidden, Category.objects.active())

    def test_featured_trending_and_luxury_filters(self) -> None:
        self.assertEqual(list(Category.objects.featured()), [self.women])
        self.assertEqual(list(Category.objects.trending()), [self.women])
        self.assertEqual(list(Category.objects.luxury()), [self.luxury])

    def test_with_counts_annotates_only_active_children(self) -> None:
        make_subcategory(self.women, "Dresses")
        make_subcategory(self.women, "Sarees", is_active=False)
        annotated = Category.objects.with_counts().get(pk=self.women.pk)
        self.assertEqual(annotated.subcategory_count, 1)

    def test_subcategory_visible_requires_an_active_parent(self) -> None:
        make_subcategory(self.hidden, "Orphan")
        visible = make_subcategory(self.women, "Dresses")
        self.assertEqual(list(SubCategory.objects.visible()), [visible])

    def test_brand_popular_orders_by_score(self) -> None:
        low = make_brand("Low", popularity_score=10)
        high = make_brand("High", popularity_score=900)
        self.assertEqual(list(Brand.objects.popular())[:2], [high, low])

    def test_collection_seasonal_filter(self) -> None:
        seasonal = make_collection("Winter Edit", type=CollectionType.WINTER)
        make_collection("Trending Edit", type=CollectionType.TRENDING)
        self.assertEqual(list(Collection.objects.seasonal()), [seasonal])


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


class ServiceTests(CatalogTestCase):
    """Tree, mega menu, homepage payload and cache behaviour."""

    def setUp(self) -> None:
        super().setUp()
        self.women = make_category("Women", is_featured=True, is_trending=True)
        self.luxury = make_category("Luxury", is_luxury=True, display_order=2)
        make_subcategory(self.women, "Dresses")
        make_subcategory(self.women, "Hidden", is_active=False)

        self.brand = make_brand("Aarohi Couture", is_featured=True, popularity_score=800)
        self.brand.categories.set([self.women])

        self.collection = make_collection("Festive Edit", type=CollectionType.FESTIVAL,
                                          is_featured=True)
        self.collection.categories.set([self.women])

    def test_tree_nests_only_active_subcategories(self) -> None:
        tree = services.get_category_tree(use_cache=False)
        women = next(node for node in tree if node["slug"] == "women")
        self.assertEqual([sub["name"] for sub in women["subcategories"]], ["Dresses"])

    def test_tree_excludes_inactive_categories(self) -> None:
        make_category("Hidden", is_active=False)
        slugs = {node["slug"] for node in services.get_category_tree(use_cache=False)}
        self.assertNotIn("hidden", slugs)

    def test_mega_menu_has_all_four_columns(self) -> None:
        menu = services.get_mega_menu(use_cache=False)
        women = next(node for node in menu if node["slug"] == "women")
        self.assertEqual([s["name"] for s in women["subcategories"]], ["Dresses"])
        self.assertEqual([c["title"] for c in women["collections"]], ["Festive Edit"])
        self.assertEqual([b["name"] for b in women["brands"]], ["Aarohi Couture"])

    def test_mega_menu_query_count_does_not_grow_with_categories(self) -> None:
        # The prefetch is the whole point: adding categories must not add
        # queries, or the menu degrades linearly as the catalogue grows.
        with self.assertNumQueries(4):
            services.get_mega_menu(use_cache=False)

        for index in range(8):
            make_category(f"Extra {index}")

        with self.assertNumQueries(4):
            services.get_mega_menu(use_cache=False)

    def test_tree_is_cached_between_calls(self) -> None:
        services.get_category_tree()
        with self.assertNumQueries(0):
            services.get_category_tree()

    def test_saving_a_category_invalidates_the_cache(self) -> None:
        services.get_category_tree()
        make_category("Brand New")
        self.assertIsNone(cache.get(services.CACHE_KEY_TREE))

    def test_m2m_change_invalidates_the_cache(self) -> None:
        services.get_mega_menu()
        self.brand.categories.add(self.luxury)
        self.assertIsNone(cache.get(services.CACHE_KEY_MEGA_MENU))

    def test_missing_image_serialises_as_null_not_an_exception(self) -> None:
        # Accessing .url on an empty ImageField raises ValueError; every cached
        # payload has to survive a category with no artwork uploaded yet.
        tree = services.get_category_tree(use_cache=False)
        self.assertIsNone(tree[0]["icon"])

    def test_top_brands_falls_back_to_popular_when_none_featured(self) -> None:
        Brand.objects.update(is_featured=False)
        popular = make_brand("Very Popular", popularity_score=5000)
        self.assertEqual(list(services.get_top_brands())[0], popular)

    def test_homepage_payload_has_every_rail(self) -> None:
        payload = services.get_homepage_payload()
        self.assertEqual(
            set(payload),
            {
                "featured_categories",
                "trending_categories",
                "luxury_categories",
                "top_brands",
                "featured_brands",
                "luxury_brands",
                "featured_collections",
                "editors_picks",
                "seasonal_collections",
            },
        )


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class SerializerTests(CatalogTestCase):
    """Field naming and nesting."""

    def setUp(self) -> None:
        super().setUp()
        self.category = make_category(
            "Women", meta_title="Women | FT", meta_description="Shop women's wear."
        )
        make_subcategory(self.category, "Dresses")

    def test_seo_fields_are_exposed_under_their_public_names(self) -> None:
        data = CategorySerializer(self.category).data
        self.assertEqual(data["seo_title"], "Women | FT")
        self.assertEqual(data["seo_description"], "Shop women's wear.")
        self.assertNotIn("meta_title", data)

    def test_id_is_the_public_uuid_not_the_primary_key(self) -> None:
        data = CategorySerializer(self.category).data
        self.assertEqual(data["id"], str(self.category.uuid))

    def test_detail_serializer_nests_active_subcategories(self) -> None:
        make_subcategory(self.category, "Hidden", is_active=False)
        data = CategoryDetailSerializer(self.category).data
        self.assertEqual([s["name"] for s in data["subcategories"]], ["Dresses"])

    def test_public_serializer_hides_the_is_active_flag(self) -> None:
        self.assertNotIn("is_active", CategorySerializer(self.category).data)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class CatalogAPITestCase(APITestCase):
    """Base case with a seeded catalogue and both kinds of user."""

    def setUp(self) -> None:
        cache.clear()
        self.customer = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com",
            password=STRONG_PASSWORD,
            first_name="Staff",
            is_staff=True,
        )

        self.women = make_category("Women", is_featured=True, is_trending=True)
        self.luxury = make_category("Luxury", is_luxury=True, display_order=2)
        self.hidden = make_category("Hidden", is_active=False, display_order=9)

        self.dresses = make_subcategory(self.women, "Dresses")
        make_subcategory(self.women, "Archived", is_active=False)

        self.brand = make_brand(
            "Aarohi Couture", is_featured=True, is_luxury=True, popularity_score=900
        )
        self.brand.categories.set([self.women, self.luxury])
        make_brand("Quiet Label", popularity_score=100)

        self.collection = make_collection(
            "Festive Edit", type=CollectionType.FESTIVAL, is_featured=True
        )
        self.collection.categories.set([self.women])
        make_collection("Editors Choice", type=CollectionType.EDITORS_PICKS)


class CategoryAPITests(CatalogAPITestCase):
    """/api/v1/categories/"""

    def test_list_is_public(self) -> None:
        response = self.client.get(reverse("catalog:category-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_hides_inactive_categories_from_customers(self) -> None:
        body = self.client.get(reverse("catalog:category-list")).json()
        self.assertNotIn("hidden", {row["slug"] for row in body["data"]})

    def test_staff_see_inactive_categories(self) -> None:
        self.client.force_authenticate(user=self.staff)
        body = self.client.get(reverse("catalog:category-list")).json()
        self.assertIn("hidden", {row["slug"] for row in body["data"]})

    def test_response_uses_the_core_envelope_and_pagination(self) -> None:
        body = self.client.get(reverse("catalog:category-list")).json()
        self.assertTrue(body["success"])
        self.assertIsInstance(body["data"], list)
        self.assertIn("pagination", body)

    def test_retrieve_by_slug_nests_subcategories(self) -> None:
        url = reverse("catalog:category-detail", args=["women"])
        body = self.client.get(url).json()
        self.assertEqual(body["data"]["slug"], "women")
        self.assertEqual([s["name"] for s in body["data"]["subcategories"]], ["Dresses"])

    def test_retrieving_an_inactive_category_is_a_404_for_customers(self) -> None:
        url = reverse("catalog:category-detail", args=["hidden"])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_tree_endpoint(self) -> None:
        body = self.client.get(reverse("catalog:category-tree")).json()
        self.assertTrue(body["success"])
        self.assertIn("women", {node["slug"] for node in body["data"]})

    def test_mega_menu_endpoint(self) -> None:
        body = self.client.get(reverse("catalog:category-mega-menu")).json()
        women = next(node for node in body["data"] if node["slug"] == "women")
        self.assertEqual([c["title"] for c in women["collections"]], ["Festive Edit"])
        self.assertIn("Aarohi Couture", {b["name"] for b in women["brands"]})

    def test_featured_trending_and_luxury_endpoints(self) -> None:
        for route, expected in (
            ("catalog:category-featured", "women"),
            ("catalog:category-trending", "women"),
            ("catalog:category-luxury", "luxury"),
        ):
            body = self.client.get(reverse(route)).json()
            self.assertIn(expected, {row["slug"] for row in body["data"]}, msg=route)

    def test_homepage_endpoint_returns_every_rail(self) -> None:
        body = self.client.get(reverse("catalog:category-homepage")).json()
        self.assertIn("featured_categories", body["data"])
        self.assertIn("top_brands", body["data"])
        self.assertIn("seasonal_collections", body["data"])

    def test_subcategories_of_a_category(self) -> None:
        url = reverse("catalog:category-subcategories", args=["women"])
        body = self.client.get(url).json()
        self.assertEqual([row["slug"] for row in body["data"]], ["women-dresses"])

    def test_brands_of_a_category(self) -> None:
        url = reverse("catalog:category-brands", args=["women"])
        body = self.client.get(url).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Aarohi Couture"])

    def test_collections_of_a_category(self) -> None:
        url = reverse("catalog:category-collections", args=["women"])
        body = self.client.get(url).json()
        self.assertEqual([row["title"] for row in body["data"]], ["Festive Edit"])

    def test_search_by_name(self) -> None:
        body = self.client.get(reverse("catalog:category-list"), {"search": "lux"}).json()
        self.assertEqual([row["slug"] for row in body["data"]], ["luxury"])

    def test_filter_by_featured(self) -> None:
        body = self.client.get(
            reverse("catalog:category-list"), {"is_featured": "true"}
        ).json()
        self.assertEqual([row["slug"] for row in body["data"]], ["women"])

    def test_ordering_by_name(self) -> None:
        body = self.client.get(
            reverse("catalog:category-list"), {"ordering": "name"}
        ).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Luxury", "Women"])


class CategoryWritePermissionTests(CatalogAPITestCase):
    """Only staff may modify the catalogue."""

    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("catalog:category-list")
        self.payload = {"name": "Home & Living", "description": "Cushions and throws."}

    def test_anonymous_cannot_create(self) -> None:
        self.assertEqual(
            self.client.post(self.url, self.payload).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_customer_cannot_create(self) -> None:
        self.client.force_authenticate(user=self.customer)
        self.assertEqual(
            self.client.post(self.url, self.payload).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_staff_can_create_and_the_slug_is_generated(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["data"]["slug"], "home-living")

    def test_customer_cannot_delete(self) -> None:
        self.client.force_authenticate(user=self.customer)
        url = reverse("catalog:category-detail", args=["women"])
        self.assertEqual(
            self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN
        )

    def test_staff_can_patch(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("catalog:category-detail", args=["women"])
        response = self.client.patch(url, {"display_order": 7})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.women.refresh_from_db()
        self.assertEqual(self.women.display_order, 7)


class SubCategoryAPITests(CatalogAPITestCase):
    """/api/v1/subcategories/"""

    def test_list_hides_children_of_inactive_parents(self) -> None:
        make_subcategory(self.hidden, "Orphan")
        body = self.client.get(reverse("catalog:subcategory-list")).json()
        self.assertEqual([row["slug"] for row in body["data"]], ["women-dresses"])

    def test_filter_by_parent_slug(self) -> None:
        body = self.client.get(
            reverse("catalog:subcategory-list"), {"category": "women"}
        ).json()
        self.assertEqual(len(body["data"]), 1)

    def test_detail_inlines_the_parent(self) -> None:
        url = reverse("catalog:subcategory-detail", args=["women-dresses"])
        body = self.client.get(url).json()
        self.assertEqual(body["data"]["category"]["slug"], "women")

    def test_duplicate_name_under_one_parent_is_a_400_not_a_409(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("catalog:subcategory-list"),
            {"category": self.women.pk, "name": "Dresses"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.json()["errors"])


class BrandAPITests(CatalogAPITestCase):
    """/api/v1/brands/"""

    def test_list_is_public(self) -> None:
        body = self.client.get(reverse("catalog:brand-list")).json()
        self.assertEqual(len(body["data"]), 2)

    def test_featured_luxury_and_popular_endpoints(self) -> None:
        for route in ("catalog:brand-featured", "catalog:brand-luxury"):
            body = self.client.get(reverse(route)).json()
            self.assertEqual([row["name"] for row in body["data"]], ["Aarohi Couture"])

        body = self.client.get(reverse("catalog:brand-popular")).json()
        self.assertEqual(body["data"][0]["name"], "Aarohi Couture")

    def test_top_endpoint(self) -> None:
        body = self.client.get(reverse("catalog:brand-top")).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Aarohi Couture"])

    def test_search_by_name(self) -> None:
        body = self.client.get(reverse("catalog:brand-list"), {"search": "quiet"}).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Quiet Label"])

    def test_starts_with_filter_backs_the_a_to_z_index(self) -> None:
        body = self.client.get(
            reverse("catalog:brand-list"), {"starts_with": "a"}
        ).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Aarohi Couture"])

    def test_filter_by_category_slug(self) -> None:
        body = self.client.get(
            reverse("catalog:brand-list"), {"category": "luxury"}
        ).json()
        self.assertEqual([row["name"] for row in body["data"]], ["Aarohi Couture"])

    def test_detail_by_slug(self) -> None:
        url = reverse("catalog:brand-detail", args=["aarohi-couture"])
        body = self.client.get(url).json()
        self.assertEqual(body["data"]["name"], "Aarohi Couture")


class CollectionAPITests(CatalogAPITestCase):
    """/api/v1/collections/"""

    def test_list_is_public(self) -> None:
        body = self.client.get(reverse("catalog:collection-list")).json()
        self.assertEqual(len(body["data"]), 2)

    def test_featured_endpoint(self) -> None:
        body = self.client.get(reverse("catalog:collection-featured")).json()
        self.assertEqual([row["title"] for row in body["data"]], ["Festive Edit"])

    def test_seasonal_endpoint(self) -> None:
        body = self.client.get(reverse("catalog:collection-seasonal")).json()
        self.assertEqual([row["title"] for row in body["data"]], ["Festive Edit"])

    def test_editors_picks_endpoint(self) -> None:
        body = self.client.get(reverse("catalog:collection-editors-picks")).json()
        self.assertEqual([row["title"] for row in body["data"]], ["Editors Choice"])

    def test_homepage_rails_are_keyed_by_name(self) -> None:
        body = self.client.get(reverse("catalog:collection-homepage")).json()
        self.assertIn("featured", body["data"])
        self.assertIn("seasonal", body["data"])
        self.assertIn("editors_picks", body["data"])

    def test_filter_by_type(self) -> None:
        body = self.client.get(
            reverse("catalog:collection-list"), {"type": CollectionType.FESTIVAL}
        ).json()
        self.assertEqual([row["title"] for row in body["data"]], ["Festive Edit"])

    def test_unknown_type_is_rejected(self) -> None:
        response = self.client.get(
            reverse("catalog:collection-list"), {"type": "not-a-type"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Seed command
# ---------------------------------------------------------------------------


class SeedCommandTests(CatalogTestCase):
    """The seed_catalog management command."""

    def test_seeding_creates_the_expected_volume(self) -> None:
        call_command("seed_catalog", verbosity=0)
        self.assertEqual(Category.objects.count(), 10)
        self.assertEqual(Brand.objects.count(), 50)
        self.assertEqual(Collection.objects.count(), 12)
        self.assertGreater(SubCategory.objects.count(), 80)

    def test_seeding_is_idempotent(self) -> None:
        call_command("seed_catalog", verbosity=0)
        counts = (Category.objects.count(), SubCategory.objects.count(),
                  Brand.objects.count(), Collection.objects.count())

        call_command("seed_catalog", verbosity=0)
        self.assertEqual(
            counts,
            (Category.objects.count(), SubCategory.objects.count(),
             Brand.objects.count(), Collection.objects.count()),
        )

    def test_seeded_slugs_are_readable_and_unique(self) -> None:
        call_command("seed_catalog", verbosity=0)
        slugs = list(SubCategory.objects.values_list("slug", flat=True))
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertIn("women-sarees", slugs)
        self.assertIn("men-shirts", slugs)

    def test_dry_run_writes_nothing(self) -> None:
        call_command("seed_catalog", "--dry-run", verbosity=0)
        self.assertEqual(Category.objects.count(), 0)

    def test_seeded_homepage_payload_is_populated(self) -> None:
        call_command("seed_catalog", verbosity=0)
        payload = services.get_homepage_payload()
        self.assertTrue(payload["featured_categories"].exists())
        self.assertTrue(payload["top_brands"].exists())
        self.assertTrue(payload["seasonal_collections"].exists())

    def test_seeded_mega_menu_covers_every_category(self) -> None:
        call_command("seed_catalog", verbosity=0)
        self.assertEqual(len(services.get_mega_menu(use_cache=False)), 10)
