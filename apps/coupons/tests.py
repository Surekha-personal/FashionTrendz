"""Tests for the coupons module."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.cart import services as cart_services
from apps.catalog.models import Brand, Category, SubCategory
from apps.coupons import services
from apps.coupons.models import Coupon, CouponUsage, DiscountType
from apps.coupons.services import CouponError
from apps.orders import services as order_services
from apps.products.models import Product, ProductVariant, Size
from apps.users.models import Address, User

STRONG_PASSWORD = "Tr3ndz!Shopper42"


class CouponFixtureMixin:
    """Builds products, a cart and a customer."""

    def build_world(self) -> None:
        """Create the taxonomy, two products and a customer with a full bag."""
        self.category = Category.objects.create(name="Women")
        self.other_category = Category.objects.create(name="Footwear", display_order=2)
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Dresses"
        )
        self.other_subcategory = SubCategory.objects.create(
            category=self.other_category, name="Heels"
        )
        self.brand = Brand.objects.create(name="Nordwyn")
        self.other_brand = Brand.objects.create(name="Kadam")

        self.product = self.make_product(
            "Classic Midi Dress", "FT-K0001", self.category, self.subcategory,
            self.brand, Decimal("2000.00"),
        )
        self.variant = self.make_variant(self.product, "FT-K0001-0")

        self.shoe = self.make_product(
            "Block Heels", "FT-K0002", self.other_category, self.other_subcategory,
            self.other_brand, Decimal("1000.00"),
        )
        self.shoe_variant = self.make_variant(self.shoe, "FT-K0002-0")

        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.address = Address.objects.create(
            user=self.user, full_name="Aditi Sharma", mobile="+919876543210",
            address_line_1="12 Linking Road", city="Mumbai", state="MH",
            country="India", postal_code="400050",
        )

    def make_product(
        self, name: str, sku: str, category: Any, subcategory: Any, brand: Any, price: Decimal
    ) -> Product:
        """Create a published product at ``price``."""
        return Product.objects.create(
            name=name, sku=sku, category=category, subcategory=subcategory,
            brand=brand, mrp=price, selling_price=price,
            published_at=timezone.now() - timezone.timedelta(days=1),
        )

    def make_variant(self, product: Product, sku: str) -> ProductVariant:
        """Create a stocked variant."""
        return ProductVariant.objects.create(
            product=product, sku=sku, color="Navy", size=Size.M, stock=20
        )

    def make_coupon(self, code: str = "SAVE20", **extra: Any) -> Coupon:
        """Create a percentage coupon with a cap."""
        defaults: dict[str, Any] = {
            "code": code,
            "discount_type": DiscountType.PERCENTAGE,
            "value": Decimal("20.00"),
            "max_discount": Decimal("500.00"),
        }
        defaults.update(extra)
        return Coupon.objects.create(**defaults)

    def fill_cart(self, product: Product | None = None, quantity: int = 1) -> Any:
        """Put a product in the customer's bag."""
        target = product or self.product
        variant = self.variant if target is self.product else self.shoe_variant
        cart = cart_services.get_or_create_cart(user=self.user)
        cart_services.add_to_cart(cart, target.slug, variant.sku, quantity)
        return cart


class CouponTestCase(CouponFixtureMixin, TestCase):
    """Base case with the world built."""

    def setUp(self) -> None:
        self.build_world()


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class CouponModelTests(CouponTestCase):
    """Model invariants."""

    def test_the_code_is_upper_cased_on_save(self) -> None:
        self.assertEqual(self.make_coupon("save30").code, "SAVE30")

    def test_the_code_is_unique(self) -> None:
        self.make_coupon("UNIQUE1")
        with self.assertRaises(IntegrityError):
            Coupon.objects.create(code="UNIQUE1", value=Decimal("10"))

    def test_a_window_that_closes_before_it_opens_is_rejected(self) -> None:
        now = timezone.now()
        with self.assertRaises(IntegrityError):
            Coupon.objects.create(
                code="BACKWARDS",
                value=Decimal("10"),
                valid_from=now,
                valid_until=now - timezone.timedelta(days=1),
            )

    def test_unlimited_uses_is_expressed_as_zero(self) -> None:
        coupon = self.make_coupon(max_uses=0)
        self.assertIsNone(coupon.remaining_uses)
        self.assertFalse(coupon.is_exhausted)

    def test_exhaustion(self) -> None:
        coupon = self.make_coupon(max_uses=2, times_used=2)
        self.assertTrue(coupon.is_exhausted)
        self.assertEqual(coupon.remaining_uses, 0)

    def test_expiry(self) -> None:
        past = timezone.now() - timezone.timedelta(days=1)
        coupon = self.make_coupon(
            valid_from=past - timezone.timedelta(days=2), valid_until=past
        )
        self.assertTrue(coupon.is_expired)
        self.assertFalse(coupon.is_redeemable)

    def test_a_scheduled_coupon_is_not_yet_redeemable(self) -> None:
        coupon = self.make_coupon(valid_from=timezone.now() + timezone.timedelta(days=2))
        self.assertFalse(coupon.has_started)
        self.assertFalse(coupon.is_redeemable)

    def test_display_value(self) -> None:
        self.assertEqual(self.make_coupon("PCT", value=Decimal("25")).display_value, "25% OFF")
        flat = self.make_coupon("FLAT", discount_type=DiscountType.FLAT, value=Decimal("300"))
        self.assertEqual(flat.display_value, "INR 300.00 OFF")

    def test_one_usage_row_per_order(self) -> None:
        coupon = self.make_coupon("ONCE")
        self.fill_cart()
        order = order_services.place_order(
            self.user, shipping_address_id=self.address.pk
        )
        CouponUsage.objects.filter(order=order).delete()

        CouponUsage.objects.create(coupon=coupon, user=self.user, order=order)
        with self.assertRaises(IntegrityError):
            CouponUsage.objects.create(coupon=coupon, user=self.user, order=order)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class CouponValidationTests(CouponTestCase):
    """What the validator refuses, and why."""

    def setUp(self) -> None:
        super().setUp()
        self.cart = self.fill_cart()

    def test_an_unknown_code_is_rejected(self) -> None:
        with self.assertRaises(CouponError):
            services.find_coupon("NOSUCHCODE")

    def test_a_valid_coupon_passes(self) -> None:
        coupon = self.make_coupon()
        self.assertEqual(
            services.validate_coupon(coupon, self.cart, self.user), Decimal("2000.00")
        )

    def test_an_inactive_coupon_is_rejected(self) -> None:
        with self.assertRaises(CouponError):
            services.validate_coupon(
                self.make_coupon(is_active=False), self.cart, self.user
            )

    def test_an_expired_coupon_is_rejected(self) -> None:
        past = timezone.now() - timezone.timedelta(days=1)
        coupon = self.make_coupon(
            valid_from=past - timezone.timedelta(days=5), valid_until=past
        )
        with self.assertRaises(CouponError):
            services.validate_coupon(coupon, self.cart, self.user)

    def test_a_scheduled_coupon_is_rejected(self) -> None:
        coupon = self.make_coupon(valid_from=timezone.now() + timezone.timedelta(days=1))
        with self.assertRaises(CouponError):
            services.validate_coupon(coupon, self.cart, self.user)

    def test_an_exhausted_coupon_is_rejected(self) -> None:
        with self.assertRaises(CouponError):
            services.validate_coupon(
                self.make_coupon(max_uses=1, times_used=1), self.cart, self.user
            )

    def test_a_cart_below_the_minimum_is_rejected_with_the_shortfall(self) -> None:
        coupon = self.make_coupon(min_cart_value=Decimal("5000.00"))
        with self.assertRaises(CouponError) as caught:
            services.validate_coupon(coupon, self.cart, self.user)
        # Actionable message: the customer can see what to add.
        self.assertIn("3000.00", str(caught.exception.detail))

    def test_an_empty_bag_is_rejected(self) -> None:
        cart_services.clear_cart(self.cart)
        self.cart.refresh_from_db()
        with self.assertRaises(CouponError):
            services.validate_coupon(self.make_coupon(), self.cart, self.user)

    def test_the_per_user_limit_is_enforced(self) -> None:
        coupon = self.make_coupon(uses_per_user=1)
        CouponUsage.objects.create(coupon=coupon, user=self.user)

        with self.assertRaises(CouponError):
            services.validate_coupon(coupon, self.cart, self.user)

    def test_a_released_usage_does_not_count_against_the_limit(self) -> None:
        # A customer who cancels must not have silently burned their one use.
        coupon = self.make_coupon(uses_per_user=1)
        CouponUsage.objects.create(coupon=coupon, user=self.user, is_released=True)

        services.validate_coupon(coupon, self.cart, self.user)

    def test_first_order_only_blocks_a_returning_customer(self) -> None:
        coupon = self.make_coupon(first_order_only=True)
        order_services.place_order(self.user, shipping_address_id=self.address.pk)
        self.fill_cart()

        cart = cart_services.get_or_create_cart(user=self.user)
        with self.assertRaises(CouponError):
            services.validate_coupon(coupon, cart, self.user)


class CouponRestrictionTests(CouponTestCase):
    """Category, brand and product restrictions."""

    def setUp(self) -> None:
        super().setUp()
        self.cart = self.fill_cart()
        cart_services.add_to_cart(self.cart, self.shoe.slug, self.shoe_variant.sku, 1)

    def test_an_unrestricted_coupon_sees_the_whole_bag(self) -> None:
        coupon = self.make_coupon()
        self.assertEqual(
            services.eligible_subtotal(self.cart, coupon), Decimal("3000.00")
        )

    def test_a_category_restriction_discounts_only_that_category(self) -> None:
        # The most expensive coupon bug there is: 20% off Footwear must not
        # take 20% off the dress in the same bag.
        coupon = self.make_coupon()
        coupon.categories.add(self.other_category)

        self.assertEqual(
            services.eligible_subtotal(self.cart, coupon), Decimal("1000.00")
        )

    def test_a_brand_restriction(self) -> None:
        coupon = self.make_coupon()
        coupon.brands.add(self.brand)
        self.assertEqual(
            services.eligible_subtotal(self.cart, coupon), Decimal("2000.00")
        )

    def test_a_product_restriction(self) -> None:
        coupon = self.make_coupon()
        coupon.products.add(self.shoe)
        self.assertEqual(
            services.eligible_subtotal(self.cart, coupon), Decimal("1000.00")
        )

    def test_restrictions_are_ored_not_anded(self) -> None:
        coupon = self.make_coupon()
        coupon.categories.add(self.category)
        coupon.brands.add(self.other_brand)
        self.assertEqual(
            services.eligible_subtotal(self.cart, coupon), Decimal("3000.00")
        )

    def test_a_coupon_matching_nothing_in_the_bag_is_rejected(self) -> None:
        empty_category = Category.objects.create(name="Beauty", display_order=9)
        coupon = self.make_coupon()
        coupon.categories.add(empty_category)

        with self.assertRaises(CouponError):
            services.validate_coupon(coupon, self.cart, self.user)


class DiscountCalculationTests(CouponTestCase):
    """The arithmetic."""

    def setUp(self) -> None:
        super().setUp()
        self.cart = self.fill_cart()

    def test_a_percentage_discount(self) -> None:
        coupon = self.make_coupon(value=Decimal("10"), max_discount=None)
        self.assertEqual(
            services.calculate_discount(coupon, Decimal("2000.00"), self.cart),
            Decimal("200.00"),
        )

    def test_the_cap_binds(self) -> None:
        # Without max_discount, "50% off" on a luxury coat is a giveaway.
        coupon = self.make_coupon(value=Decimal("50"), max_discount=Decimal("300.00"))
        self.assertEqual(
            services.calculate_discount(coupon, Decimal("2000.00"), self.cart),
            Decimal("300.00"),
        )

    def test_a_flat_discount(self) -> None:
        coupon = self.make_coupon(
            "FLAT300", discount_type=DiscountType.FLAT, value=Decimal("300.00")
        )
        self.assertEqual(
            services.calculate_discount(coupon, Decimal("2000.00"), self.cart),
            Decimal("300.00"),
        )

    def test_a_discount_never_exceeds_the_eligible_subtotal(self) -> None:
        # Otherwise the order total goes negative.
        coupon = self.make_coupon(
            "HUGE",
            discount_type=DiscountType.FLAT,
            value=Decimal("99999.00"),
            max_discount=None,
        )
        self.assertEqual(
            services.calculate_discount(coupon, Decimal("2000.00"), self.cart),
            Decimal("2000.00"),
        )

    def test_free_shipping_takes_nothing_off_the_items(self) -> None:
        coupon = self.make_coupon("SHIPFREE", discount_type=DiscountType.FREE_SHIPPING)
        self.assertEqual(
            services.calculate_discount(coupon, Decimal("2000.00"), self.cart),
            Decimal("0.00"),
        )


# ---------------------------------------------------------------------------
# Apply, redeem, release
# ---------------------------------------------------------------------------


class CouponApplyTests(CouponTestCase):
    """Applying to a cart and redeeming through an order."""

    def setUp(self) -> None:
        super().setUp()
        self.cart = self.fill_cart()
        self.coupon = self.make_coupon(value=Decimal("10"), max_discount=None)

    def test_apply_writes_the_discount_to_the_cart(self) -> None:
        result = services.apply_coupon_to_cart(self.cart, "SAVE20", self.user)

        self.cart.refresh_from_db()
        self.assertTrue(result["applied"])
        self.assertEqual(self.cart.coupon_code, "SAVE20")
        self.assertEqual(self.cart.coupon_discount, Decimal("200.00"))

    def test_the_cart_summary_picks_the_discount_up(self) -> None:
        # Module 6 reserved these two columns for exactly this.
        services.apply_coupon_to_cart(self.cart, "SAVE20", self.user)
        summary = cart_services.get_cart_summary(self.cart)

        self.assertEqual(summary["coupon_discount"], Decimal("200.00"))
        self.assertEqual(summary["grand_total"], Decimal("1820.00"))

    def test_remove_clears_it(self) -> None:
        services.apply_coupon_to_cart(self.cart, "SAVE20", self.user)
        services.remove_coupon_from_cart(self.cart)

        self.cart.refresh_from_db()
        self.assertEqual(self.cart.coupon_code, "")
        self.assertEqual(self.cart.coupon_discount, Decimal("0.00"))

    def test_revalidate_drops_a_coupon_that_stopped_qualifying(self) -> None:
        # Applied twenty minutes ago; the window closed since.
        services.apply_coupon_to_cart(self.cart, "SAVE20", self.user)

        self.coupon.is_active = False
        self.coupon.save()

        result = services.revalidate_cart_coupon(self.cart, self.user)
        self.cart.refresh_from_db()

        self.assertFalse(result["applied"])
        self.assertEqual(self.cart.coupon_discount, Decimal("0.00"))

    def test_placing_an_order_records_the_redemption(self) -> None:
        services.apply_coupon_to_cart(self.cart, "SAVE20", self.user)
        order = order_services.place_order(
            self.user, shipping_address_id=self.address.pk
        )

        usage = CouponUsage.objects.get(order=order)
        self.assertEqual(usage.coupon, self.coupon)
        self.assertEqual(usage.discount_amount, Decimal("200.00"))

        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.times_used, 1)

    def test_the_order_carries_the_discount(self) -> None:
        services.apply_coupon_to_cart(self.cart, "SAVE20", self.user)
        order = order_services.place_order(
            self.user, shipping_address_id=self.address.pk
        )

        self.assertEqual(order.coupon_code, "SAVE20")
        self.assertEqual(order.coupon_discount, Decimal("200.00"))
        self.assertEqual(order.grand_total, Decimal("1820.00"))

    def test_cancelling_gives_the_redemption_back(self) -> None:
        services.apply_coupon_to_cart(self.cart, "SAVE20", self.user)
        order = order_services.place_order(
            self.user, shipping_address_id=self.address.pk
        )

        order_services.cancel_order(order, reason="Changed my mind")

        usage = CouponUsage.objects.get(order=order)
        self.assertTrue(usage.is_released)

        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.times_used, 0)

    def test_a_released_redemption_lets_the_customer_use_it_again(self) -> None:
        self.coupon.uses_per_user = 1
        self.coupon.save()

        services.apply_coupon_to_cart(self.cart, "SAVE20", self.user)
        order = order_services.place_order(
            self.user, shipping_address_id=self.address.pk
        )
        order_services.cancel_order(order, reason="Changed my mind")

        fresh_cart = self.fill_cart()
        services.apply_coupon_to_cart(fresh_cart, "SAVE20", self.user)

    def test_recording_the_same_order_twice_counts_once(self) -> None:
        # A retried signal must not burn two redemptions.
        order = order_services.place_order(
            self.user, shipping_address_id=self.address.pk
        )
        services.record_usage(self.coupon, self.user, order, Decimal("100.00"))
        services.record_usage(self.coupon, self.user, order, Decimal("100.00"))

        self.assertEqual(CouponUsage.objects.filter(order=order).count(), 1)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class CouponAPITests(CouponFixtureMixin, APITestCase):
    """/api/v1/coupons/"""

    def setUp(self) -> None:
        self.build_world()
        self.staff = User.objects.create_user(
            email="staff@example.com", password=STRONG_PASSWORD,
            first_name="Staff", is_staff=True,
        )
        self.coupon = self.make_coupon(value=Decimal("10"), max_discount=None)
        self.client.force_authenticate(user=self.user)
        self.fill_cart()

    def test_the_offers_list_is_public(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("coupons:coupon-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_private_coupons_are_hidden_from_the_offers_list(self) -> None:
        self.make_coupon("SECRET50", is_public=False)
        body = self.client.get(reverse("coupons:coupon-list")).json()
        self.assertNotIn("SECRET50", {row["code"] for row in body["data"]})

    def test_expired_coupons_are_hidden(self) -> None:
        past = timezone.now() - timezone.timedelta(days=1)
        self.make_coupon(
            "OLDCODE", valid_from=past - timezone.timedelta(days=5), valid_until=past
        )
        body = self.client.get(reverse("coupons:coupon-list")).json()
        self.assertNotIn("OLDCODE", {row["code"] for row in body["data"]})

    def test_the_public_payload_hides_the_usage_cap(self) -> None:
        body = self.client.get(reverse("coupons:coupon-list")).json()
        self.assertNotIn("max_uses", body["data"][0])
        self.assertNotIn("times_used", body["data"][0])

    def test_validate_endpoint_reports_the_saving(self) -> None:
        body = self.client.post(
            reverse("coupons:coupon-validate"), {"code": "save20"}
        ).json()
        self.assertEqual(body["data"]["discount"], "200.00")
        self.assertFalse(body["data"]["applied"])

    def test_apply_endpoint(self) -> None:
        body = self.client.post(
            reverse("coupons:coupon-apply"), {"code": "SAVE20"}
        ).json()
        self.assertTrue(body["data"]["applied"])
        self.assertEqual(body["data"]["discount"], "200.00")

    def test_apply_rejects_an_unknown_code(self) -> None:
        response = self.client.post(
            reverse("coupons:coupon-apply"), {"code": "NOPE123"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.json()["success"])

    def test_remove_endpoint(self) -> None:
        self.client.post(reverse("coupons:coupon-apply"), {"code": "SAVE20"})
        body = self.client.post(reverse("coupons:coupon-remove")).json()
        self.assertFalse(body["data"]["applied"])

    def test_apply_requires_authentication(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.post(
            reverse("coupons:coupon-apply"), {"code": "SAVE20"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_customer_cannot_create_a_coupon(self) -> None:
        response = self.client.post(
            reverse("coupons:coupon-list"), {"code": "HACK50", "value": "50"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create_a_coupon(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("coupons:coupon-list"),
            {
                "code": "NEWYEAR",
                "discount_type": DiscountType.PERCENTAGE,
                "value": "25.00",
                "max_discount": "1000.00",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_an_uncapped_percentage_coupon_is_refused(self) -> None:
        # Refusing by default: an uncapped percentage on a luxury catalogue is
        # a blank cheque.
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("coupons:coupon-list"),
            {"code": "UNCAPPED", "discount_type": DiscountType.PERCENTAGE, "value": "50"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("max_discount", response.json()["errors"])

    def test_usage_history_endpoint(self) -> None:
        self.client.post(reverse("coupons:coupon-apply"), {"code": "SAVE20"})
        order_services.place_order(self.user, shipping_address_id=self.address.pk)

        body = self.client.get(reverse("coupons:coupon-usages")).json()
        self.assertEqual(body["data"][0]["code"], "SAVE20")
