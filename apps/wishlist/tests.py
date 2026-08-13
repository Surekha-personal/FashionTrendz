"""Tests for the wishlist module."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Brand, Category, SubCategory
from apps.core.exceptions import BusinessRuleViolation
from apps.products.models import Product, ProductVariant, Size
from apps.users.models import User
from apps.wishlist import services
from apps.wishlist.models import Wishlist, WishlistItem

STRONG_PASSWORD = "Tr3ndz!Shopper42"


class WishlistFixtureMixin:
    """Builds the taxonomy, products and users the tests share."""

    def build_world(self) -> None:
        """Create categories, a brand, two products and two users."""
        self.category = Category.objects.create(name="Women")
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Dresses"
        )
        self.brand = Brand.objects.create(name="Nordwyn")

        self.product = self.make_product("Classic Midi Dress", "FT-W0001")
        self.other = self.make_product("Linen Shirt", "FT-W0002")

        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.stranger = User.objects.create_user(
            email="other@example.com", password=STRONG_PASSWORD, first_name="Other"
        )

    def make_product(self, name: str, sku: str, **extra: Any) -> Product:
        """Create a published product."""
        defaults: dict[str, Any] = {
            "name": name,
            "sku": sku,
            "category": self.category,
            "subcategory": self.subcategory,
            "brand": self.brand,
            "mrp": Decimal("2000.00"),
            "selling_price": Decimal("1500.00"),
            "published_at": timezone.now() - timezone.timedelta(days=1),
        }
        defaults.update(extra)
        return Product.objects.create(**defaults)

    def make_variant(self, product: Product, sku: str, stock: int = 10) -> ProductVariant:
        """Create a variant with stock."""
        return ProductVariant.objects.create(
            product=product, sku=sku, color="Navy", size=Size.M, stock=stock
        )


class WishlistModelTests(WishlistFixtureMixin, TestCase):
    """Model invariants."""

    def setUp(self) -> None:
        self.build_world()

    def test_one_wishlist_per_user(self) -> None:
        Wishlist.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            Wishlist.objects.create(user=self.user)

    def test_a_product_can_only_be_saved_once(self) -> None:
        wishlist = Wishlist.objects.create(user=self.user)
        WishlistItem.objects.create(wishlist=wishlist, product=self.product)
        with self.assertRaises(IntegrityError):
            WishlistItem.objects.create(wishlist=wishlist, product=self.product)

    def test_two_users_can_save_the_same_product(self) -> None:
        for user in (self.user, self.stranger):
            wishlist = Wishlist.objects.create(user=user)
            WishlistItem.objects.create(wishlist=wishlist, product=self.product)
        self.assertEqual(WishlistItem.objects.count(), 2)

    def test_item_count(self) -> None:
        wishlist = Wishlist.objects.create(user=self.user)
        WishlistItem.objects.create(wishlist=wishlist, product=self.product)
        self.assertEqual(wishlist.item_count, 1)

    def test_deleting_a_user_removes_the_wishlist(self) -> None:
        Wishlist.objects.create(user=self.user)
        self.user.delete()
        self.assertEqual(Wishlist.objects.count(), 0)


class WishlistServiceTests(WishlistFixtureMixin, TestCase):
    """Service behaviour."""

    def setUp(self) -> None:
        self.build_world()

    def test_wishlist_is_created_lazily(self) -> None:
        self.assertEqual(Wishlist.objects.count(), 0)
        services.get_or_create_wishlist(self.user)
        self.assertEqual(Wishlist.objects.count(), 1)

    def test_add_returns_created_true_then_false(self) -> None:
        _item, created = services.add_to_wishlist(self.user, self.product.slug)
        self.assertTrue(created)

        _item, created = services.add_to_wishlist(self.user, self.product.slug)
        self.assertFalse(created)

    def test_adding_twice_does_not_raise(self) -> None:
        # A double tap on the heart icon must not produce an error toast.
        services.add_to_wishlist(self.user, self.product.slug)
        services.add_to_wishlist(self.user, self.product.slug)
        self.assertEqual(services.get_wishlist_count(self.user), 1)

    def test_add_increments_the_product_counter(self) -> None:
        services.add_to_wishlist(self.user, self.product.slug)
        self.product.refresh_from_db()
        self.assertEqual(self.product.wishlist_count, 1)

    def test_remove_decrements_the_product_counter(self) -> None:
        services.add_to_wishlist(self.user, self.product.slug)
        services.remove_from_wishlist(self.user, self.product.slug)
        self.product.refresh_from_db()
        self.assertEqual(self.product.wishlist_count, 0)

    def test_counter_never_goes_negative(self) -> None:
        # Removing something never added must not drive the positive integer
        # column below zero, which the database would reject.
        services.remove_from_wishlist(self.user, self.product.slug)
        self.product.refresh_from_db()
        self.assertEqual(self.product.wishlist_count, 0)

    def test_adding_an_unavailable_product_is_rejected(self) -> None:
        self.product.is_active = False
        self.product.save()
        with self.assertRaises(BusinessRuleViolation):
            services.add_to_wishlist(self.user, self.product.slug)

    def test_toggle_adds_then_removes(self) -> None:
        first = services.toggle_wishlist(self.user, self.product.slug)
        self.assertTrue(first["in_wishlist"])
        self.assertEqual(first["count"], 1)

        second = services.toggle_wishlist(self.user, self.product.slug)
        self.assertFalse(second["in_wishlist"])
        self.assertEqual(second["count"], 0)

    def test_clear_removes_everything(self) -> None:
        services.add_to_wishlist(self.user, self.product.slug)
        services.add_to_wishlist(self.user, self.other.slug)
        self.assertEqual(services.clear_wishlist(self.user), 2)
        self.assertEqual(services.get_wishlist_count(self.user), 0)

    def test_count_excludes_products_that_became_unavailable(self) -> None:
        # The badge must match what the page renders, or it reads as a bug.
        services.add_to_wishlist(self.user, self.product.slug)
        services.add_to_wishlist(self.user, self.other.slug)

        self.other.is_active = False
        self.other.save()
        self.assertEqual(services.get_wishlist_count(self.user), 1)

    def test_hidden_products_are_kept_but_not_listed(self) -> None:
        services.add_to_wishlist(self.user, self.other.slug)
        self.other.is_active = False
        self.other.save()

        self.assertEqual(services.get_wishlist_items(self.user).count(), 0)
        self.assertEqual(WishlistItem.objects.for_user(self.user).count(), 1)

    def test_slugs_helper_returns_everything_in_one_query(self) -> None:
        services.add_to_wishlist(self.user, self.product.slug)
        with self.assertNumQueries(1):
            self.assertEqual(
                services.wishlist_product_slugs(self.user), {self.product.slug}
            )

    def test_wishlists_are_isolated_between_users(self) -> None:
        services.add_to_wishlist(self.user, self.product.slug)
        self.assertEqual(services.get_wishlist_count(self.stranger), 0)

    def test_move_to_cart_requires_the_item_to_be_saved(self) -> None:
        self.make_variant(self.product, "FT-W0001-0")
        with self.assertRaises(BusinessRuleViolation):
            services.move_to_cart(self.user, self.product.slug, "FT-W0001-0")

    def test_move_to_cart_transfers_the_item(self) -> None:
        variant = self.make_variant(self.product, "FT-W0001-0")
        services.add_to_wishlist(self.user, self.product.slug)

        result = services.move_to_cart(self.user, self.product.slug, variant.sku, 2)

        self.assertEqual(result["wishlist_count"], 0)
        self.assertEqual(result["cart_item"].quantity, 2)
        self.assertEqual(services.get_wishlist_count(self.user), 0)

    def test_move_to_cart_keeps_the_item_when_stock_fails(self) -> None:
        # One transaction: a stock failure must not lose the item from both
        # the wishlist and the cart.
        variant = self.make_variant(self.product, "FT-W0001-0", stock=1)
        services.add_to_wishlist(self.user, self.product.slug)

        with self.assertRaises(Exception):
            services.move_to_cart(self.user, self.product.slug, variant.sku, 5)

        self.assertEqual(services.get_wishlist_count(self.user), 1)


class WishlistAPITests(WishlistFixtureMixin, APITestCase):
    """/api/v1/wishlist/"""

    def setUp(self) -> None:
        self.build_world()
        self.client.force_authenticate(user=self.user)

    def test_authentication_is_required(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("wishlist:wishlist-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_is_empty_for_a_new_user(self) -> None:
        body = self.client.get(reverse("wishlist:wishlist-list")).json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"], [])

    def test_add_endpoint(self) -> None:
        response = self.client.post(
            reverse("wishlist:wishlist-add"), {"product": self.product.slug}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.json()["data"]["product"]["slug"], self.product.slug
        )

    def test_adding_twice_returns_200_not_an_error(self) -> None:
        self.client.post(reverse("wishlist:wishlist-add"), {"product": self.product.slug})
        response = self.client.post(
            reverse("wishlist:wishlist-add"), {"product": self.product.slug}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_add_rejects_an_unknown_product(self) -> None:
        response = self.client.post(
            reverse("wishlist:wishlist-add"), {"product": "no-such-product"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product", response.json()["errors"])

    def test_toggle_endpoint(self) -> None:
        url = reverse("wishlist:wishlist-toggle")
        first = self.client.post(url, {"product": self.product.slug}).json()
        self.assertTrue(first["data"]["in_wishlist"])

        second = self.client.post(url, {"product": self.product.slug}).json()
        self.assertFalse(second["data"]["in_wishlist"])

    def test_remove_endpoint(self) -> None:
        self.client.post(reverse("wishlist:wishlist-add"), {"product": self.product.slug})
        body = self.client.post(
            reverse("wishlist:wishlist-remove"), {"product": self.product.slug}
        ).json()
        self.assertEqual(body["data"]["count"], 0)

    def test_count_endpoint(self) -> None:
        self.client.post(reverse("wishlist:wishlist-add"), {"product": self.product.slug})
        body = self.client.get(reverse("wishlist:wishlist-count")).json()
        self.assertEqual(body["data"]["count"], 1)

    def test_clear_endpoint(self) -> None:
        self.client.post(reverse("wishlist:wishlist-add"), {"product": self.product.slug})
        self.client.post(reverse("wishlist:wishlist-add"), {"product": self.other.slug})

        body = self.client.post(reverse("wishlist:wishlist-clear")).json()
        self.assertEqual(body["data"]["removed"], 2)
        self.assertEqual(body["data"]["count"], 0)

    def test_slugs_endpoint(self) -> None:
        self.client.post(reverse("wishlist:wishlist-add"), {"product": self.product.slug})
        body = self.client.get(reverse("wishlist:wishlist-slugs")).json()
        self.assertEqual(body["data"]["slugs"], [self.product.slug])

    def test_move_to_cart_endpoint(self) -> None:
        variant = self.make_variant(self.product, "FT-W0001-0")
        self.client.post(reverse("wishlist:wishlist-add"), {"product": self.product.slug})

        body = self.client.post(
            reverse("wishlist:wishlist-move-to-cart"),
            {"product": self.product.slug, "variant": variant.sku, "quantity": 2},
        ).json()

        self.assertEqual(body["data"]["wishlist_count"], 0)
        self.assertEqual(body["data"]["cart_item"]["quantity"], 2)

    def test_list_embeds_a_product_card(self) -> None:
        self.client.post(reverse("wishlist:wishlist-add"), {"product": self.product.slug})
        card = self.client.get(reverse("wishlist:wishlist-list")).json()["data"][0][
            "product"
        ]
        # Identical shape to a listing tile, so the frontend reuses one component.
        for key in ("slug", "brand", "selling_price", "discount_percentage"):
            self.assertIn(key, card)

    def test_a_user_never_sees_another_users_wishlist(self) -> None:
        self.client.post(reverse("wishlist:wishlist-add"), {"product": self.product.slug})

        self.client.force_authenticate(user=self.stranger)
        body = self.client.get(reverse("wishlist:wishlist-list")).json()
        self.assertEqual(body["data"], [])
