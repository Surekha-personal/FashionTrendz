"""Tests for the cart module."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.cart import services
from apps.cart.models import MAX_QUANTITY_PER_LINE, Cart, CartItem
from apps.catalog.models import Brand, Category, SubCategory
from apps.core.exceptions import BusinessRuleViolation, InsufficientStock
from apps.products.models import Product, ProductVariant, Size
from apps.users.models import User
from apps.wishlist.models import WishlistItem

STRONG_PASSWORD = "Tr3ndz!Shopper42"
GUEST_SESSION = "guest-session-key-0001"


class CartFixtureMixin:
    """Builds the taxonomy, products, variants and users the tests share."""

    def build_world(self) -> None:
        """Create everything a cart needs to point at."""
        self.category = Category.objects.create(name="Women")
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Dresses"
        )
        self.brand = Brand.objects.create(name="Nordwyn")

        self.product = self.make_product(
            "Classic Midi Dress", "FT-C0001",
            mrp=Decimal("2000.00"), selling_price=Decimal("1500.00"),
            tax_percentage=Decimal("10.00"),
        )
        self.variant = self.make_variant(self.product, "FT-C0001-0", stock=10)
        self.variant_b = self.make_variant(
            self.product, "FT-C0001-1", stock=4, color="Rust", size=Size.L
        )

        self.cheap = self.make_product(
            "Budget Tee", "FT-C0002",
            mrp=Decimal("500.00"), selling_price=Decimal("300.00"),
        )
        self.cheap_variant = self.make_variant(self.cheap, "FT-C0002-0", stock=50)

        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
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

    def make_variant(
        self, product: Product, sku: str, stock: int = 10, **extra: Any
    ) -> ProductVariant:
        """Create a variant with stock."""
        defaults: dict[str, Any] = {
            "product": product,
            "sku": sku,
            "color": "Navy",
            "size": Size.M,
            "stock": stock,
        }
        defaults.update(extra)
        return ProductVariant.objects.create(**defaults)


class CartTestCase(CartFixtureMixin, TestCase):
    """Base case with the world built."""

    def setUp(self) -> None:
        self.build_world()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CartModelTests(CartTestCase):
    """Ownership and quantity invariants."""

    def test_user_cart_and_guest_cart_can_both_exist(self) -> None:
        Cart.objects.create(user=self.user)
        Cart.objects.create(session_key=GUEST_SESSION)
        self.assertEqual(Cart.objects.count(), 2)

    def test_a_cart_owned_by_neither_is_rejected(self) -> None:
        # A NULL/NULL row is an orphan nobody can reach.
        with self.assertRaises(IntegrityError):
            Cart.objects.create()

    def test_a_cart_owned_by_both_is_rejected(self) -> None:
        with self.assertRaises(IntegrityError):
            Cart.objects.create(user=self.user, session_key=GUEST_SESSION)

    def test_one_active_cart_per_user(self) -> None:
        Cart.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            Cart.objects.create(user=self.user)

    def test_a_deactivated_cart_frees_the_slot(self) -> None:
        first = Cart.objects.create(user=self.user)
        first.is_active = False
        first.save()
        Cart.objects.create(user=self.user)
        self.assertEqual(Cart.objects.filter(user=self.user).count(), 2)

    def test_one_active_cart_per_guest_session(self) -> None:
        Cart.objects.create(session_key=GUEST_SESSION)
        with self.assertRaises(IntegrityError):
            Cart.objects.create(session_key=GUEST_SESSION)

    def test_one_line_per_variant(self) -> None:
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, variant=self.variant)
        with self.assertRaises(IntegrityError):
            CartItem.objects.create(
                cart=cart, product=self.product, variant=self.variant
            )

    def test_quantity_must_be_at_least_one(self) -> None:
        cart = Cart.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            CartItem.objects.create(
                cart=cart, product=self.product, variant=self.variant, quantity=0
            )

    def test_quantity_ceiling_is_enforced_by_the_database(self) -> None:
        cart = Cart.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            CartItem.objects.create(
                cart=cart,
                product=self.product,
                variant=self.variant,
                quantity=MAX_QUANTITY_PER_LINE + 1,
            )


class CartMoneyTests(CartTestCase):
    """The per-line money snapshot."""

    def setUp(self) -> None:
        super().setUp()
        self.cart = Cart.objects.create(user=self.user)

    def test_line_money_is_computed_on_save(self) -> None:
        item = CartItem.objects.create(
            cart=self.cart, product=self.product, variant=self.variant, quantity=2
        )
        self.assertEqual(item.unit_price, Decimal("1500.00"))
        self.assertEqual(item.unit_mrp, Decimal("2000.00"))
        self.assertEqual(item.subtotal, Decimal("3000.00"))
        self.assertEqual(item.discount, Decimal("1000.00"))
        self.assertEqual(item.tax, Decimal("300.00"))
        self.assertEqual(item.total, Decimal("3000.00"))

    def test_a_variant_price_override_wins(self) -> None:
        self.variant.price_override = Decimal("1200.00")
        self.variant.save()

        item = CartItem.objects.create(
            cart=self.cart, product=self.product, variant=self.variant
        )
        self.assertEqual(item.unit_price, Decimal("1200.00"))

    def test_recalculate_picks_up_a_price_change(self) -> None:
        # A bag quoting yesterday's price and a checkout charging today's is
        # the worst possible order of events.
        item = CartItem.objects.create(
            cart=self.cart, product=self.product, variant=self.variant
        )
        self.assertEqual(item.unit_price, Decimal("1500.00"))

        self.product.selling_price = Decimal("999.00")
        self.product.save()

        services.recalculate_cart(self.cart)
        item.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal("999.00"))

    def test_recalculate_writes_nothing_when_prices_are_unchanged(self) -> None:
        # Asserting "no UPDATE" rather than an exact query count: the point is
        # that the common case costs no writes, and a count would also be
        # counting savepoints and prefetches that are not what this guards.
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        CartItem.objects.create(
            cart=self.cart, product=self.product, variant=self.variant
        )
        with CaptureQueriesContext(connection) as captured:
            services.recalculate_cart(self.cart)

        # startswith, not "in": every SELECT lists an "updated_at" column,
        # which contains the substring "UPDATE".
        updates = [
            q["sql"]
            for q in captured.captured_queries
            if q["sql"].lstrip().upper().startswith("UPDATE")
        ]
        self.assertEqual(updates, [])


class CartSummaryTests(CartTestCase):
    """The price breakdown."""

    def setUp(self) -> None:
        super().setUp()
        self.cart = Cart.objects.create(user=self.user)

    def test_empty_cart_has_no_fees(self) -> None:
        summary = services.get_cart_summary(self.cart)
        self.assertEqual(summary["grand_total"], Decimal("0.00"))
        self.assertEqual(summary["shipping"], Decimal("0.00"))
        self.assertEqual(summary["platform_fee"], Decimal("0.00"))

    def test_shipping_is_charged_below_the_threshold(self) -> None:
        services.add_to_cart(self.cart, self.cheap.slug, self.cheap_variant.sku, 1)
        summary = services.get_cart_summary(self.cart)

        self.assertEqual(summary["subtotal"], Decimal("300.00"))
        self.assertEqual(summary["shipping"], Decimal("79.00"))
        self.assertEqual(summary["platform_fee"], Decimal("20.00"))
        self.assertEqual(summary["grand_total"], Decimal("399.00"))
        self.assertEqual(summary["amount_to_free_shipping"], Decimal("699.00"))

    def test_shipping_is_free_above_the_threshold(self) -> None:
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)
        summary = services.get_cart_summary(self.cart)

        self.assertEqual(summary["shipping"], Decimal("0.00"))
        self.assertEqual(summary["grand_total"], Decimal("1520.00"))
        self.assertEqual(summary["amount_to_free_shipping"], Decimal("0.00"))

    def test_savings_reflect_mrp_minus_selling_price(self) -> None:
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 2)
        summary = services.get_cart_summary(self.cart)
        self.assertEqual(summary["discount"], Decimal("1000.00"))
        self.assertEqual(summary["total_savings"], Decimal("1000.00"))

    def test_saved_for_later_lines_are_excluded_from_the_total(self) -> None:
        # The classic "why is my bag more than it looks" bug.
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)
        services.add_to_cart(self.cart, self.cheap.slug, self.cheap_variant.sku, 1)
        services.save_for_later(self.cart, self.cheap_variant.sku)

        summary = services.get_cart_summary(self.cart)
        self.assertEqual(summary["subtotal"], Decimal("1500.00"))
        self.assertEqual(summary["item_count"], 1)

    def test_delivery_estimate_uses_the_slowest_line(self) -> None:
        self.product.estimated_delivery_days = 3
        self.product.save()
        self.cheap.estimated_delivery_days = 9
        self.cheap.save()

        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)
        services.add_to_cart(self.cart, self.cheap.slug, self.cheap_variant.sku, 1)

        self.assertEqual(services.get_cart_summary(self.cart)["estimated_delivery_days"], 9)

    def test_coupon_placeholder_captures_but_does_not_discount(self) -> None:
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)
        result = services.apply_coupon(self.cart, "festive50")

        self.assertEqual(result["code"], "FESTIVE50")
        self.assertFalse(result["applied"])
        self.assertEqual(services.get_cart_summary(self.cart)["coupon_discount"], Decimal("0.00"))


class CartMutationTests(CartTestCase):
    """Adding, updating and removing lines."""

    def setUp(self) -> None:
        super().setUp()
        self.cart = Cart.objects.create(user=self.user)

    def test_add_creates_a_line(self) -> None:
        item = services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 2)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(self.cart.items.count(), 1)

    def test_adding_the_same_variant_merges_into_one_line(self) -> None:
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 2)
        item = services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 3)

        self.assertEqual(item.quantity, 5)
        self.assertEqual(self.cart.items.count(), 1)

    def test_merging_still_respects_the_purchase_limit(self) -> None:
        # "add 6" twice must not smuggle 12 units past a limit of 10.
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 6)
        with self.assertRaises(BusinessRuleViolation):
            services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 6)

    def test_adding_more_than_stock_is_rejected(self) -> None:
        with self.assertRaises(InsufficientStock):
            services.add_to_cart(self.cart, self.product.slug, self.variant_b.sku, 9)

    def test_reserved_stock_reduces_what_can_be_added(self) -> None:
        self.variant.reserved_stock = 8
        self.variant.save()
        with self.assertRaises(InsufficientStock):
            services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 5)

    def test_adding_to_cart_does_not_touch_inventory(self) -> None:
        # A cart that holds stock lets anyone empty the store for free.
        before = self.variant.stock
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 3)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, before)
        self.assertEqual(self.variant.reserved_stock, 0)

    def test_a_variant_from_another_product_is_rejected(self) -> None:
        # Pairing any SKU with any slug would let a ₹90,000 coat be bought at
        # a ₹499 tee's price.
        with self.assertRaises(BusinessRuleViolation):
            services.add_to_cart(self.cart, self.product.slug, self.cheap_variant.sku, 1)

    def test_an_unavailable_product_is_rejected(self) -> None:
        self.product.is_active = False
        self.product.save()
        with self.assertRaises(BusinessRuleViolation):
            services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)

    def test_an_inactive_variant_is_rejected(self) -> None:
        self.variant.is_active = False
        self.variant.save()
        with self.assertRaises(BusinessRuleViolation):
            services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)

    def test_update_quantity(self) -> None:
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)
        item = services.update_quantity(self.cart, self.variant.sku, 4)
        self.assertEqual(item.quantity, 4)

    def test_update_to_zero_removes_the_line(self) -> None:
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 3)
        self.assertIsNone(services.update_quantity(self.cart, self.variant.sku, 0))
        self.assertEqual(self.cart.items.count(), 0)

    def test_increase_and_decrease(self) -> None:
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 2)

        self.assertEqual(services.change_quantity(self.cart, self.variant.sku, 1).quantity, 3)
        self.assertEqual(services.change_quantity(self.cart, self.variant.sku, -1).quantity, 2)

    def test_decreasing_to_zero_removes_the_line(self) -> None:
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)
        self.assertIsNone(services.change_quantity(self.cart, self.variant.sku, -1))

    def test_remove_line(self) -> None:
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)
        self.assertTrue(services.remove_from_cart(self.cart, self.variant.sku))
        self.assertEqual(self.cart.items.count(), 0)

    def test_clear_keeps_saved_items_by_default(self) -> None:
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)
        services.add_to_cart(self.cart, self.cheap.slug, self.cheap_variant.sku, 1)
        services.save_for_later(self.cart, self.cheap_variant.sku)

        services.clear_cart(self.cart)
        self.assertEqual(self.cart.items.count(), 1)
        self.assertTrue(self.cart.items.first().saved_for_later)

    def test_clear_can_include_saved_items(self) -> None:
        services.add_to_cart(self.cart, self.cheap.slug, self.cheap_variant.sku, 1)
        services.save_for_later(self.cart, self.cheap_variant.sku)

        services.clear_cart(self.cart, include_saved=True)
        self.assertEqual(self.cart.items.count(), 0)

    def test_acting_on_a_missing_line_is_a_domain_error(self) -> None:
        with self.assertRaises(BusinessRuleViolation):
            services.update_quantity(self.cart, "FT-NOPE", 1)


class SaveForLaterTests(CartTestCase):
    """Moving lines between the bag and the saved section."""

    def setUp(self) -> None:
        super().setUp()
        self.cart = Cart.objects.create(user=self.user)
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 2)

    def test_save_for_later_moves_the_line_out_of_the_bag(self) -> None:
        services.save_for_later(self.cart, self.variant.sku)
        self.assertEqual(self.cart.line_count, 0)
        self.assertEqual(self.cart.saved_items.count(), 1)

    def test_move_to_bag_brings_it_back(self) -> None:
        services.save_for_later(self.cart, self.variant.sku)
        services.move_to_bag(self.cart, self.variant.sku)
        self.assertEqual(self.cart.line_count, 1)

    def test_move_to_bag_rechecks_stock(self) -> None:
        services.save_for_later(self.cart, self.variant.sku)
        self.variant.stock = 1
        self.variant.save()

        with self.assertRaises(InsufficientStock):
            services.move_to_bag(self.cart, self.variant.sku)

    def test_adding_a_saved_variant_returns_it_to_the_bag(self) -> None:
        services.save_for_later(self.cart, self.variant.sku)
        item = services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)
        self.assertFalse(item.saved_for_later)


class MoveToWishlistTests(CartTestCase):
    """Cart to wishlist."""

    def setUp(self) -> None:
        super().setUp()
        self.cart = Cart.objects.create(user=self.user)
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 1)

    def test_move_transfers_the_product(self) -> None:
        result = services.move_to_wishlist(self.cart, self.variant.sku)

        self.assertEqual(result["wishlist_count"], 1)
        self.assertEqual(self.cart.items.count(), 0)
        self.assertTrue(
            WishlistItem.objects.filter(
                wishlist__user=self.user, product=self.product
            ).exists()
        )

    def test_a_guest_cannot_move_to_a_wishlist(self) -> None:
        guest_cart = Cart.objects.create(session_key=GUEST_SESSION)
        services.add_to_cart(guest_cart, self.product.slug, self.variant.sku, 1)

        with self.assertRaises(BusinessRuleViolation):
            services.move_to_wishlist(guest_cart, self.variant.sku)


class MergeCartTests(CartTestCase):
    """Folding a guest bag into a signed-in customer's bag."""

    def setUp(self) -> None:
        super().setUp()
        self.guest_cart = Cart.objects.create(session_key=GUEST_SESSION)

    def test_guest_lines_move_to_the_user_cart(self) -> None:
        services.add_to_cart(self.guest_cart, self.product.slug, self.variant.sku, 2)
        user_cart = services.merge_carts(self.user, GUEST_SESSION)

        self.assertEqual(user_cart.user, self.user)
        self.assertEqual(user_cart.items.count(), 1)
        self.assertEqual(user_cart.items.first().quantity, 2)

    def test_quantities_are_added_not_replaced(self) -> None:
        # Two as a guest plus one signed in is three, not one.
        user_cart = services.get_or_create_cart(user=self.user)
        services.add_to_cart(user_cart, self.product.slug, self.variant.sku, 1)
        services.add_to_cart(self.guest_cart, self.product.slug, self.variant.sku, 2)

        merged = services.merge_carts(self.user, GUEST_SESSION)
        self.assertEqual(merged.items.count(), 1)
        self.assertEqual(merged.items.first().quantity, 3)

    def test_merged_quantity_is_clamped_to_the_limit(self) -> None:
        user_cart = services.get_or_create_cart(user=self.user)
        services.add_to_cart(user_cart, self.product.slug, self.variant.sku, 8)
        services.add_to_cart(self.guest_cart, self.product.slug, self.variant.sku, 8)

        merged = services.merge_carts(self.user, GUEST_SESSION)
        self.assertEqual(merged.items.first().quantity, MAX_QUANTITY_PER_LINE)

    def test_distinct_variants_both_survive(self) -> None:
        user_cart = services.get_or_create_cart(user=self.user)
        services.add_to_cart(user_cart, self.product.slug, self.variant.sku, 1)
        services.add_to_cart(self.guest_cart, self.cheap.slug, self.cheap_variant.sku, 1)

        merged = services.merge_carts(self.user, GUEST_SESSION)
        self.assertEqual(merged.items.count(), 2)

    def test_the_guest_cart_is_deactivated_not_deleted(self) -> None:
        services.add_to_cart(self.guest_cart, self.product.slug, self.variant.sku, 1)
        services.merge_carts(self.user, GUEST_SESSION)

        self.guest_cart.refresh_from_db()
        self.assertFalse(self.guest_cart.is_active)

    def test_merging_an_unknown_session_is_harmless(self) -> None:
        cart = services.merge_carts(self.user, "no-such-session")
        self.assertEqual(cart.user, self.user)


class CartIssueTests(CartTestCase):
    """Blocking problems reported on the cart page."""

    def setUp(self) -> None:
        super().setUp()
        self.cart = Cart.objects.create(user=self.user)
        services.add_to_cart(self.cart, self.product.slug, self.variant.sku, 3)

    def test_a_healthy_cart_reports_no_issues(self) -> None:
        self.assertEqual(services.get_cart_issues(self.cart), [])
        self.assertTrue(services.get_checkout_payload(self.cart)["is_checkout_ready"])

    def test_stock_selling_out_is_reported(self) -> None:
        # Kinder to surface this on the cart page than to fail at payment.
        self.variant.stock = 1
        self.variant.save()

        issues = services.get_cart_issues(self.cart)
        self.assertEqual(issues[0]["reason"], "insufficient_stock")
        self.assertEqual(issues[0]["available"], 1)

    def test_a_deactivated_product_is_reported(self) -> None:
        self.product.is_active = False
        self.product.save()
        self.assertEqual(services.get_cart_issues(self.cart)[0]["reason"], "unavailable")

    def test_an_issue_blocks_checkout(self) -> None:
        self.variant.stock = 0
        self.variant.save()
        self.assertFalse(services.get_checkout_payload(self.cart)["is_checkout_ready"])

    def test_an_empty_cart_is_not_checkout_ready(self) -> None:
        services.clear_cart(self.cart)
        self.cart.refresh_from_db()
        self.assertFalse(services.get_checkout_payload(self.cart)["is_checkout_ready"])


class CartQueryCountTests(CartTestCase):
    """The cart page is on the critical path to revenue."""

    def test_loading_a_cart_does_not_scale_with_line_count(self) -> None:
        cart = Cart.objects.create(user=self.user)
        services.add_to_cart(cart, self.product.slug, self.variant.sku, 1)
        services.add_to_cart(cart, self.product.slug, self.variant_b.sku, 1)
        services.add_to_cart(cart, self.cheap.slug, self.cheap_variant.sku, 1)

        loaded = services.load_cart(cart)
        with self.assertNumQueries(0):
            self.assertEqual(len(list(loaded.items.all())), 3)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class CartAPITests(CartFixtureMixin, APITestCase):
    """/api/v1/cart/"""

    def setUp(self) -> None:
        self.build_world()

    def guest(self) -> dict[str, str]:
        """Return the header a guest client sends."""
        return {"HTTP_X_CART_SESSION": GUEST_SESSION}

    def test_a_guest_can_use_the_cart(self) -> None:
        response = self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku, "quantity": 1},
            **self.guest(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_a_signed_in_customer_can_use_the_cart(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_add_returns_the_whole_cart(self) -> None:
        body = self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku, "quantity": 2},
            **self.guest(),
        ).json()

        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]["items"]), 1)
        self.assertEqual(body["data"]["summary"]["unit_count"], 2)

    def test_count_endpoint_creates_no_cart(self) -> None:
        # An anonymous visitor browsing must not write a row per page view.
        self.client.get(reverse("cart:cart-count"), **self.guest())
        self.assertEqual(Cart.objects.count(), 0)

    def test_count_endpoint_reports_units(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku, "quantity": 3},
            **self.guest(),
        )
        body = self.client.get(reverse("cart:cart-count"), **self.guest()).json()
        self.assertEqual(body["data"]["count"], 3)

    def test_update_endpoint(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
            **self.guest(),
        )
        body = self.client.post(
            reverse("cart:cart-update"),
            {"variant": self.variant.sku, "quantity": 5},
            **self.guest(),
        ).json()
        self.assertEqual(body["data"]["items"][0]["quantity"], 5)

    def test_increase_and_decrease_endpoints(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku, "quantity": 2},
            **self.guest(),
        )
        body = self.client.post(
            reverse("cart:cart-increase"), {"variant": self.variant.sku}, **self.guest()
        ).json()
        self.assertEqual(body["data"]["items"][0]["quantity"], 3)

        body = self.client.post(
            reverse("cart:cart-decrease"), {"variant": self.variant.sku}, **self.guest()
        ).json()
        self.assertEqual(body["data"]["items"][0]["quantity"], 2)

    def test_remove_endpoint(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
            **self.guest(),
        )
        body = self.client.post(
            reverse("cart:cart-remove"), {"variant": self.variant.sku}, **self.guest()
        ).json()
        self.assertEqual(body["data"]["items"], [])

    def test_clear_endpoint(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
            **self.guest(),
        )
        body = self.client.post(reverse("cart:cart-clear"), **self.guest()).json()
        self.assertEqual(body["data"]["items"], [])

    def test_save_for_later_and_move_to_bag(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
            **self.guest(),
        )
        body = self.client.post(
            reverse("cart:cart-save-for-later"),
            {"variant": self.variant.sku},
            **self.guest(),
        ).json()
        self.assertEqual(body["data"]["items"], [])
        self.assertEqual(len(body["data"]["saved_items"]), 1)

        body = self.client.post(
            reverse("cart:cart-move-to-bag"),
            {"variant": self.variant.sku},
            **self.guest(),
        ).json()
        self.assertEqual(len(body["data"]["items"]), 1)

    def test_move_to_wishlist_requires_sign_in(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
            **self.guest(),
        )
        response = self.client.post(
            reverse("cart:cart-move-to-wishlist"),
            {"variant": self.variant.sku},
            **self.guest(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_move_to_wishlist_when_signed_in(self) -> None:
        self.client.force_authenticate(user=self.user)
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
        )
        body = self.client.post(
            reverse("cart:cart-move-to-wishlist"), {"variant": self.variant.sku}
        ).json()

        self.assertEqual(body["data"]["wishlist_count"], 1)
        self.assertEqual(body["data"]["cart"]["items"], [])

    def test_summary_endpoint(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
            **self.guest(),
        )
        body = self.client.get(reverse("cart:cart-summary"), **self.guest()).json()
        for key in ("subtotal", "shipping", "platform_fee", "grand_total", "tax"):
            self.assertIn(key, body["data"])

    def test_checkout_endpoint(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
            **self.guest(),
        )
        body = self.client.get(reverse("cart:cart-checkout"), **self.guest()).json()
        self.assertTrue(body["data"]["is_checkout_ready"])
        self.assertEqual(body["data"]["issues"], [])

    def test_checkout_on_an_empty_bag_is_rejected(self) -> None:
        response = self.client.get(reverse("cart:cart-checkout"), **self.guest())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_over_stock_add_returns_409(self) -> None:
        response = self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant_b.sku, "quantity": 9},
            **self.guest(),
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(response.json()["success"])

    def test_guest_cart_merges_automatically_on_first_signed_in_request(self) -> None:
        # No explicit merge call: sending the session header after signing in
        # is enough, which is what makes JWT login lossless for the bag.
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku, "quantity": 2},
            **self.guest(),
        )

        self.client.force_authenticate(user=self.user)
        body = self.client.get(reverse("cart:cart-list"), **self.guest()).json()

        self.assertEqual(len(body["data"]["items"]), 1)
        self.assertEqual(body["data"]["items"][0]["quantity"], 2)
        self.assertFalse(body["data"]["is_guest"])

    def test_explicit_merge_endpoint(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
            **self.guest(),
        )
        self.client.force_authenticate(user=self.user)
        body = self.client.post(
            reverse("cart:cart-merge"), {"session_key": GUEST_SESSION}
        ).json()
        self.assertEqual(len(body["data"]["items"]), 1)

    def test_two_guests_do_not_share_a_cart(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
            **self.guest(),
        )
        body = self.client.get(
            reverse("cart:cart-list"), HTTP_X_CART_SESSION="a-different-guest"
        ).json()
        self.assertEqual(body["data"]["items"], [])

    def test_coupon_endpoints(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant.sku},
            **self.guest(),
        )
        body = self.client.post(
            reverse("cart:cart-apply-coupon"), {"code": "festive50"}, **self.guest()
        ).json()
        self.assertEqual(body["data"]["code"], "FESTIVE50")
        self.assertFalse(body["data"]["applied"])

        body = self.client.post(
            reverse("cart:cart-remove-coupon"), **self.guest()
        ).json()
        self.assertEqual(body["data"]["coupon_code"], "")

    def test_max_quantity_is_reported_for_the_stepper(self) -> None:
        self.client.post(
            reverse("cart:cart-add"),
            {"product": self.product.slug, "variant": self.variant_b.sku},
            **self.guest(),
        )
        body = self.client.get(reverse("cart:cart-list"), **self.guest()).json()
        # Stock is 4, limit is 10 — the control must offer the lower of the two.
        self.assertEqual(body["data"]["items"][0]["max_quantity"], 4)
