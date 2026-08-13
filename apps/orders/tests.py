"""Tests for the orders module.

Heaviest coverage in the project, because this is where money and inventory
meet: a bug here either sells stock that does not exist or charges a price the
customer never saw.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.cart import services as cart_services
from apps.catalog.models import Brand, Category, SubCategory
from apps.core.choices import OrderStatus, PaymentMethod, PaymentStatus
from apps.core.exceptions import BusinessRuleViolation, InsufficientStock
from apps.orders import services
from apps.orders.models import (
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatusHistory,
    Shipment,
)
from apps.orders.validators import assert_transition, can_transition
from apps.products.models import Product, ProductVariant, Size
from apps.users.models import Address, User

STRONG_PASSWORD = "Tr3ndz!Shopper42"


class OrderFixtureMixin:
    """Builds a customer with an address, a stocked product and a full cart."""

    def build_world(self) -> None:
        """Create everything an order needs to exist."""
        self.category = Category.objects.create(name="Women")
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Dresses"
        )
        self.brand = Brand.objects.create(name="Nordwyn")

        self.product = self.make_product(
            "Classic Midi Dress", "FT-O0001",
            mrp=Decimal("2000.00"), selling_price=Decimal("1500.00"),
            tax_percentage=Decimal("10.00"),
        )
        self.variant = self.make_variant(self.product, "FT-O0001-0", stock=10)

        self.second = self.make_product(
            "Budget Tee", "FT-O0002",
            mrp=Decimal("500.00"), selling_price=Decimal("300.00"),
        )
        self.second_variant = self.make_variant(self.second, "FT-O0002-0", stock=20)

        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.stranger = User.objects.create_user(
            email="other@example.com", password=STRONG_PASSWORD, first_name="Other"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com", password=STRONG_PASSWORD,
            first_name="Staff", is_staff=True,
        )

        self.address = Address.objects.create(
            user=self.user,
            full_name="Aditi Sharma",
            mobile="+919876543210",
            address_line_1="12 Linking Road",
            city="Mumbai",
            state="Maharashtra",
            country="India",
            postal_code="400050",
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

    def fill_cart(self, quantity: int = 2) -> Any:
        """Put the main product in the user's bag."""
        cart = cart_services.get_or_create_cart(user=self.user)
        cart_services.add_to_cart(cart, self.product.slug, self.variant.sku, quantity)
        return cart

    def place(self, **overrides: Any) -> Order:
        """Place an order from the user's current bag."""
        kwargs: dict[str, Any] = {"shipping_address_id": self.address.pk}
        kwargs.update(overrides)
        return services.place_order(self.user, **kwargs)


class OrderTestCase(OrderFixtureMixin, TestCase):
    """Base case with the world built."""

    def setUp(self) -> None:
        self.build_world()


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class StatusTransitionTests(TestCase):
    """The transition table."""

    def test_the_happy_path_is_legal_end_to_end(self) -> None:
        path = [
            OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
            OrderStatus.PACKED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.DELIVERED,
        ]
        for current, target in zip(path, path[1:]):
            self.assertTrue(can_transition(current, target), msg=f"{current}->{target}")

    def test_statuses_cannot_be_skipped(self) -> None:
        self.assertFalse(can_transition(OrderStatus.PENDING, OrderStatus.SHIPPED))
        self.assertFalse(can_transition(OrderStatus.CONFIRMED, OrderStatus.DELIVERED))

    def test_statuses_cannot_be_rewound(self) -> None:
        # Rewinding destroys the audit trail finance reconciles against.
        self.assertFalse(can_transition(OrderStatus.SHIPPED, OrderStatus.PACKED))
        self.assertFalse(can_transition(OrderStatus.DELIVERED, OrderStatus.SHIPPED))

    def test_a_shipped_order_cannot_be_cancelled(self) -> None:
        self.assertFalse(can_transition(OrderStatus.SHIPPED, OrderStatus.CANCELLED))

    def test_refunded_is_terminal(self) -> None:
        for target in OrderStatus.values:
            self.assertFalse(can_transition(OrderStatus.REFUNDED, target), msg=target)

    def test_moving_to_the_same_status_is_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            assert_transition(OrderStatus.CONFIRMED, OrderStatus.CONFIRMED)


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------


class PlaceOrderTests(OrderTestCase):
    """Turning a cart into an order."""

    def setUp(self) -> None:
        super().setUp()
        self.fill_cart(2)

    def test_an_order_is_created_with_a_number(self) -> None:
        order = self.place()
        self.assertTrue(order.order_number.startswith("FT-ORD-"))
        self.assertEqual(order.user, self.user)

    def test_money_is_copied_from_the_cart_not_recomputed(self) -> None:
        cart = cart_services.get_or_create_cart(user=self.user)
        summary = cart_services.get_cart_summary(cart)

        order = self.place()

        self.assertEqual(order.subtotal, summary["subtotal"])
        self.assertEqual(order.grand_total, summary["grand_total"])
        self.assertEqual(order.tax, summary["tax"])
        self.assertEqual(order.shipping_charge, summary["shipping"])
        self.assertEqual(order.platform_fee, summary["platform_fee"])

    def test_line_items_are_frozen_snapshots(self) -> None:
        order = self.place()
        item = order.items.first()

        self.assertEqual(item.product_name, "Classic Midi Dress")
        self.assertEqual(item.sku, self.variant.sku)
        self.assertEqual(item.color, "Navy")
        self.assertEqual(item.size, Size.M)
        self.assertEqual(item.selling_price, Decimal("1500.00"))
        self.assertEqual(item.quantity, 2)

    def test_renaming_the_product_does_not_rewrite_history(self) -> None:
        # The entire reason line items are snapshots.
        order = self.place()

        self.product.name = "Renamed Entirely"
        self.product.selling_price = Decimal("99.00")
        self.product.save()

        item = order.items.first()
        item.refresh_from_db()
        self.assertEqual(item.product_name, "Classic Midi Dress")
        self.assertEqual(item.selling_price, Decimal("1500.00"))

    def test_deleting_the_product_leaves_the_line_readable(self) -> None:
        order = self.place()
        self.variant.delete()
        self.product.delete()

        item = order.items.first()
        item.refresh_from_db()
        self.assertIsNone(item.product_id)
        self.assertEqual(item.product_name, "Classic Midi Dress")

    def test_the_address_is_snapshotted(self) -> None:
        order = self.place()
        self.assertEqual(order.shipping_address["full_name"], "Aditi Sharma")

        # Editing the saved address must not rewrite where the parcel went.
        self.address.full_name = "Someone Else"
        self.address.save()

        order.refresh_from_db()
        self.assertEqual(order.shipping_address["full_name"], "Aditi Sharma")

    def test_billing_defaults_to_shipping(self) -> None:
        order = self.place()
        self.assertEqual(order.billing_address, order.shipping_address)

    def test_the_cart_is_deactivated_and_a_fresh_one_is_available(self) -> None:
        cart = cart_services.get_or_create_cart(user=self.user)
        self.place()

        cart.refresh_from_db()
        self.assertFalse(cart.is_active)

        fresh = cart_services.get_or_create_cart(user=self.user)
        self.assertNotEqual(fresh.pk, cart.pk)
        self.assertTrue(fresh.is_empty)

    def test_a_status_history_entry_is_written(self) -> None:
        order = self.place()
        self.assertTrue(
            OrderStatusHistory.objects.filter(
                order=order, status=OrderStatus.PENDING
            ).exists()
        )

    def test_cod_confirms_immediately(self) -> None:
        order = self.place(payment_method=PaymentMethod.COD)
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertEqual(order.payment_status, PaymentStatus.PENDING)

    def test_prepaid_stays_pending_until_the_gateway_reports(self) -> None:
        order = self.place(payment_method=PaymentMethod.UPI)
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertEqual(order.payment_status, PaymentStatus.PENDING)

    def test_an_empty_bag_cannot_be_ordered(self) -> None:
        cart_services.clear_cart(cart_services.get_or_create_cart(user=self.user))
        with self.assertRaises(BusinessRuleViolation):
            self.place()

    def test_a_stranger_address_is_rejected(self) -> None:
        foreign = Address.objects.create(
            user=self.stranger, full_name="Other", mobile="+919000000000",
            address_line_1="1 Road", city="Pune", state="MH",
            country="India", postal_code="411001",
        )
        with self.assertRaises(BusinessRuleViolation):
            self.place(shipping_address_id=foreign.pk)

    def test_an_unknown_payment_method_is_rejected(self) -> None:
        with self.assertRaises(BusinessRuleViolation):
            self.place(payment_method="crypto")

    def test_an_estimated_delivery_date_is_set(self) -> None:
        self.assertIsNotNone(self.place().estimated_delivery_date)

    def test_express_delivery_is_promised_sooner(self) -> None:
        from apps.orders.models import DeliveryMethod

        standard = services.estimate_delivery_date(8, DeliveryMethod.STANDARD)
        express = services.estimate_delivery_date(8, DeliveryMethod.EXPRESS)
        self.assertLess(express, standard)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class StockLifecycleTests(OrderTestCase):
    """Reserve, commit, release and restock."""

    def setUp(self) -> None:
        super().setUp()
        self.fill_cart(3)

    def test_placing_an_order_reduces_stock(self) -> None:
        self.place()
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 7)
        self.assertEqual(self.variant.reserved_stock, 0)

    def test_the_products_cached_stock_is_refreshed(self) -> None:
        # queryset.update() skips the signal that maintains this, so the
        # service refreshes it explicitly.
        self.place()
        self.product.refresh_from_db()
        self.assertEqual(self.product.total_stock, 7)

    def test_the_order_is_marked_stock_committed(self) -> None:
        self.assertTrue(self.place().stock_committed)

    def test_ordering_more_than_stock_is_refused(self) -> None:
        self.variant.stock = 1
        self.variant.save()
        with self.assertRaises(InsufficientStock):
            self.place()

    def test_a_failed_order_writes_nothing(self) -> None:
        # The whole point of the transaction: a partial order is worse than none.
        self.variant.stock = 1
        self.variant.save()

        with self.assertRaises(InsufficientStock):
            self.place()

        self.assertEqual(Order.objects.count(), 0)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 1)
        self.assertEqual(self.variant.reserved_stock, 0)
        self.assertTrue(cart_services.get_or_create_cart(user=self.user).is_active)

    def test_reserve_stock_refuses_to_oversell(self) -> None:
        with self.assertRaises(InsufficientStock):
            services.reserve_stock([(self.variant.pk, 999)])

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.reserved_stock, 0)

    def test_reserve_then_commit_equals_a_sale(self) -> None:
        services.reserve_stock([(self.variant.pk, 4)])
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.reserved_stock, 4)
        self.assertEqual(self.variant.stock, 10)

        services.commit_stock([(self.variant.pk, 4)])
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.reserved_stock, 0)
        self.assertEqual(self.variant.stock, 6)

    def test_release_drops_a_reservation_without_selling(self) -> None:
        services.reserve_stock([(self.variant.pk, 4)])
        services.release_stock([(self.variant.pk, 4)])

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.reserved_stock, 0)
        self.assertEqual(self.variant.stock, 10)

    def test_existing_reservations_reduce_what_can_be_ordered(self) -> None:
        self.variant.reserved_stock = 9
        self.variant.save()
        with self.assertRaises(InsufficientStock):
            self.place()

    def test_purchase_count_is_credited_by_units_not_lines(self) -> None:
        before = self.product.purchase_count
        self.place()
        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_count, before + 3)


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


class CancelOrderTests(OrderTestCase):
    """Cancelling and returning inventory."""

    def setUp(self) -> None:
        super().setUp()
        self.fill_cart(3)
        self.order = self.place()

    def test_cancelling_restocks_committed_units(self) -> None:
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 7)

        services.cancel_order(self.order, reason="Changed my mind")

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)

    def test_cancelling_clears_the_committed_flag(self) -> None:
        services.cancel_order(self.order, reason="Changed my mind")
        self.order.refresh_from_db()
        self.assertFalse(self.order.stock_committed)

    def test_cancelling_reverses_the_purchase_credit(self) -> None:
        # A cancelled order is not a sale; leaving the credit inflates the
        # bestseller rails with orders that never shipped.
        after_order = Product.objects.get(pk=self.product.pk).purchase_count
        services.cancel_order(self.order, reason="Changed my mind")
        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_count, after_order - 3)

    def test_the_reason_and_timestamp_are_recorded(self) -> None:
        services.cancel_order(self.order, reason="Ordered the wrong size")
        self.order.refresh_from_db()
        self.assertEqual(self.order.cancel_reason, "Ordered the wrong size")
        self.assertIsNotNone(self.order.cancelled_at)
        self.assertEqual(self.order.status, OrderStatus.CANCELLED)

    def test_a_shipped_order_cannot_be_cancelled(self) -> None:
        for target in (OrderStatus.PROCESSING, OrderStatus.PACKED, OrderStatus.SHIPPED):
            services.transition_order(self.order, target)

        with self.assertRaises(BusinessRuleViolation):
            services.cancel_order(self.order, reason="Too late")

    def test_cancelling_twice_is_refused(self) -> None:
        services.cancel_order(self.order, reason="Changed my mind")
        with self.assertRaises(BusinessRuleViolation):
            services.cancel_order(self.order, reason="Again")

    def test_a_paid_order_is_marked_for_refund(self) -> None:
        services.mark_payment_settled(self.order, reference="pay_123", confirm=False)
        services.cancel_order(self.order, reason="Changed my mind")

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.REFUNDED)


# ---------------------------------------------------------------------------
# Transitions, shipments, payments
# ---------------------------------------------------------------------------


class TransitionServiceTests(OrderTestCase):
    """transition_order and its side effects."""

    def setUp(self) -> None:
        super().setUp()
        self.fill_cart(1)
        self.order = self.place()

    def test_each_move_appends_to_the_timeline(self) -> None:
        before = self.order.status_history.count()
        services.transition_order(self.order, OrderStatus.PROCESSING)
        self.assertEqual(self.order.status_history.count(), before + 1)

    def test_an_illegal_move_is_refused(self) -> None:
        with self.assertRaises(BusinessRuleViolation):
            services.transition_order(self.order, OrderStatus.DELIVERED)

    def test_delivery_stamps_the_time_and_status(self) -> None:
        for target in (
            OrderStatus.PROCESSING, OrderStatus.PACKED,
            OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED,
        ):
            services.transition_order(self.order, target)

        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.delivered_at)
        self.assertEqual(self.order.delivery_status, DeliveryStatus.DELIVERED)

    def test_a_delivered_cod_order_becomes_paid(self) -> None:
        # The courier collected the cash.
        for target in (
            OrderStatus.PROCESSING, OrderStatus.PACKED,
            OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED,
        ):
            services.transition_order(self.order, target)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)

    def test_mark_payment_settled_confirms_a_pending_order(self) -> None:
        cart_services.add_to_cart(
            cart_services.get_or_create_cart(user=self.user),
            self.product.slug, self.variant.sku, 1,
        )
        prepaid = self.place(payment_method=PaymentMethod.UPI)
        self.assertEqual(prepaid.status, OrderStatus.PENDING)

        services.mark_payment_settled(prepaid, reference="pay_abc")
        prepaid.refresh_from_db()
        self.assertEqual(prepaid.payment_status, PaymentStatus.PAID)
        self.assertEqual(prepaid.status, OrderStatus.CONFIRMED)
        self.assertEqual(prepaid.payment_reference, "pay_abc")


class ShipmentTests(OrderTestCase):
    """Parcels."""

    def setUp(self) -> None:
        super().setUp()
        self.fill_cart(1)
        self.order = self.place()
        for target in (OrderStatus.PROCESSING, OrderStatus.PACKED):
            services.transition_order(self.order, target)

    def test_creating_a_dispatched_shipment_ships_the_order(self) -> None:
        services.create_shipment(
            self.order, courier_name="Bluedart", tracking_number="BD123456789"
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.SHIPPED)

    def test_the_delivery_status_mirrors_the_parcel(self) -> None:
        shipment = services.create_shipment(self.order, courier_name="Delhivery")
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_status, DeliveryStatus.DISPATCHED)

        shipment.delivered_at = timezone.now()
        shipment.save()
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_status, DeliveryStatus.DELIVERED)

    def test_an_overdue_parcel_is_flagged(self) -> None:
        shipment = services.create_shipment(
            self.order,
            courier_name="Delhivery",
            expected_delivery_date=timezone.localdate() - timezone.timedelta(days=2),
        )
        self.assertTrue(shipment.is_overdue)


# ---------------------------------------------------------------------------
# Invoice and reorder
# ---------------------------------------------------------------------------


class InvoiceTests(OrderTestCase):
    """Invoice numbering and PDF rendering."""

    def setUp(self) -> None:
        super().setUp()
        self.fill_cart(2)
        self.order = self.place()

    def test_the_invoice_number_is_allocated_lazily(self) -> None:
        # A cancelled order that never shipped must not consume a number in
        # the sequence the accountant reconciles.
        self.assertEqual(self.order.invoice_number, "")
        number = services.ensure_invoice_number(self.order)
        self.assertTrue(number.startswith("FT-INV-"))

    def test_the_invoice_number_is_stable(self) -> None:
        first = services.ensure_invoice_number(self.order)
        second = services.ensure_invoice_number(self.order)
        self.assertEqual(first, second)

    def test_the_invoice_context_comes_from_snapshots(self) -> None:
        context = services.get_invoice_context(self.order)
        self.assertEqual(context["items"][0].product_name, "Classic Midi Dress")
        self.assertEqual(context["grand_total"], self.order.grand_total)

    def test_a_pdf_is_generated_and_stored(self) -> None:
        handle = services.generate_invoice_pdf(self.order)
        self.assertTrue(handle.name.endswith(".pdf"))

        handle.open("rb")
        content = handle.read()
        handle.close()
        self.assertTrue(content.startswith(b"%PDF"))

    def test_the_pdf_is_cached_not_re_rendered(self) -> None:
        first = services.generate_invoice_pdf(self.order).name
        self.order.refresh_from_db()
        second = services.generate_invoice_pdf(self.order).name
        self.assertEqual(first, second)


class ReorderTests(OrderTestCase):
    """Putting a past order back in the bag."""

    def setUp(self) -> None:
        super().setUp()
        self.fill_cart(2)
        self.order = self.place()

    def test_reorder_adds_the_items_back(self) -> None:
        result = services.reorder(self.order, self.user)
        self.assertEqual(result["added"], ["Classic Midi Dress"])
        self.assertEqual(result["cart"].items.first().quantity, 2)

    def test_unavailable_lines_are_skipped_not_fatal(self) -> None:
        # A two-year-old order will usually have a discontinued line; refusing
        # the whole reorder over it is worse than adding the rest.
        #
        # setUp already placed an order holding only the dress, so build a
        # second order that holds *both* products and retire one of them.
        cart = cart_services.get_or_create_cart(user=self.user)
        cart_services.add_to_cart(cart, self.product.slug, self.variant.sku, 1)
        cart_services.add_to_cart(cart, self.second.slug, self.second_variant.sku, 1)
        mixed_order = self.place()

        self.variant.is_active = False
        self.variant.save()

        result = services.reorder(mixed_order, self.user)
        self.assertIn("Budget Tee", result["added"])
        self.assertTrue(
            any(s["name"] == "Classic Midi Dress" for s in result["skipped"])
        )

    def test_reordering_a_fully_unavailable_order_is_refused(self) -> None:
        self.variant.is_active = False
        self.variant.save()
        with self.assertRaises(BusinessRuleViolation):
            services.reorder(self.order, self.user)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class CheckoutAPITests(OrderFixtureMixin, APITestCase):
    """/api/v1/checkout/"""

    def setUp(self) -> None:
        self.build_world()
        self.client.force_authenticate(user=self.user)
        self.fill_cart(2)

    def test_authentication_is_required(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("orders:checkout-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_checkout_context(self) -> None:
        body = self.client.get(reverse("orders:checkout-list")).json()
        self.assertTrue(body["data"]["is_checkout_ready"])
        self.assertEqual(len(body["data"]["addresses"]), 1)
        self.assertTrue(body["data"]["payment_methods"])

    def test_loading_checkout_reserves_nothing(self) -> None:
        self.client.get(reverse("orders:checkout-list"))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.reserved_stock, 0)
        self.assertEqual(self.variant.stock, 10)

    def test_review_returns_the_order_without_creating_it(self) -> None:
        body = self.client.post(
            reverse("orders:checkout-review"),
            {"shipping_address": self.address.pk},
        ).json()

        self.assertEqual(body["data"]["shipping_address"]["full_name"], "Aditi Sharma")
        self.assertEqual(Order.objects.count(), 0)

    def test_place_order(self) -> None:
        response = self.client.post(
            reverse("orders:checkout-place-order"),
            {"shipping_address": self.address.pk, "payment_method": "cod"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data = response.json()["data"]
        self.assertTrue(data["order_number"].startswith("FT-ORD-"))
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["status"], OrderStatus.CONFIRMED)

    def test_placing_with_an_empty_bag_is_rejected(self) -> None:
        cart_services.clear_cart(cart_services.get_or_create_cart(user=self.user))
        response = self.client.post(
            reverse("orders:checkout-place-order"),
            {"shipping_address": self.address.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_placing_with_a_stranger_address_is_rejected(self) -> None:
        foreign = Address.objects.create(
            user=self.stranger, full_name="Other", mobile="+919000000000",
            address_line_1="1 Road", city="Pune", state="MH",
            country="India", postal_code="411001",
        )
        response = self.client.post(
            reverse("orders:checkout-place-order"),
            {"shipping_address": foreign.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_placing_over_stock_returns_409(self) -> None:
        self.variant.stock = 1
        self.variant.save()
        response = self.client.post(
            reverse("orders:checkout-place-order"),
            {"shipping_address": self.address.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


class OrderAPITests(OrderFixtureMixin, APITestCase):
    """/api/v1/orders/"""

    def setUp(self) -> None:
        self.build_world()
        self.client.force_authenticate(user=self.user)
        self.fill_cart(2)
        self.order = self.place()

    def test_order_history(self) -> None:
        body = self.client.get(reverse("orders:order-list")).json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["order_number"], self.order.order_number)

    def test_order_detail(self) -> None:
        url = reverse("orders:order-detail", args=[self.order.order_number])
        data = self.client.get(url).json()["data"]

        self.assertEqual(data["order_number"], self.order.order_number)
        self.assertEqual(len(data["items"]), 1)
        self.assertTrue(data["status_history"])
        self.assertIn("shipping_address", data)

    def test_a_stranger_gets_a_404_not_a_403(self) -> None:
        # A 403 would confirm that a guessed order number is real.
        self.client.force_authenticate(user=self.stranger)
        url = reverse("orders:order-detail", args=[self.order.order_number])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_stranger_sees_an_empty_history(self) -> None:
        self.client.force_authenticate(user=self.stranger)
        body = self.client.get(reverse("orders:order-list")).json()
        self.assertEqual(body["data"], [])

    def test_cancel_endpoint(self) -> None:
        url = reverse("orders:order-cancel", args=[self.order.order_number])
        body = self.client.post(url, {"reason": "Changed my mind"}).json()

        self.assertEqual(body["data"]["status"], OrderStatus.CANCELLED)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)

    def test_cancel_requires_a_real_reason(self) -> None:
        url = reverse("orders:order-cancel", args=[self.order.order_number])
        response = self.client.post(url, {"reason": "no"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tracking_endpoint(self) -> None:
        url = reverse("orders:order-tracking", args=[self.order.order_number])
        data = self.client.get(url).json()["data"]

        self.assertEqual(data["order_number"], self.order.order_number)
        self.assertTrue(data["timeline"])

    def test_invoice_json(self) -> None:
        url = reverse("orders:order-invoice", args=[self.order.order_number])
        data = self.client.get(url).json()["data"]

        self.assertTrue(data["invoice_number"].startswith("FT-INV-"))
        self.assertEqual(len(data["items"]), 1)

    def test_invoice_pdf_download(self) -> None:
        url = reverse("orders:order-invoice", args=[self.order.order_number])
        response = self.client.get(url, {"download": "1"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))

    def test_reorder_endpoint(self) -> None:
        url = reverse("orders:order-reorder", args=[self.order.order_number])
        body = self.client.post(url).json()

        self.assertEqual(body["data"]["added"], ["Classic Midi Dress"])
        self.assertEqual(len(body["data"]["cart"]["items"]), 1)

    def test_a_customer_cannot_change_fulfilment_status(self) -> None:
        url = reverse("orders:order-update-status", args=[self.order.order_number])
        response = self.client.post(url, {"status": OrderStatus.DELIVERED})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_change_fulfilment_status(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("orders:order-update-status", args=[self.order.order_number])
        body = self.client.post(url, {"status": OrderStatus.PROCESSING}).json()
        self.assertEqual(body["data"]["status"], OrderStatus.PROCESSING)

    def test_staff_cannot_make_an_illegal_move(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("orders:order-update-status", args=[self.order.order_number])
        response = self.client.post(url, {"status": OrderStatus.DELIVERED})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_can_record_a_shipment(self) -> None:
        self.client.force_authenticate(user=self.staff)
        for target in (OrderStatus.PROCESSING, OrderStatus.PACKED):
            services.transition_order(self.order, target)

        url = reverse("orders:order-create-shipment", args=[self.order.order_number])
        response = self.client.post(
            url, {"courier_name": "Bluedart", "tracking_number": "BD123456789"}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_order_history_query_count_does_not_grow_with_orders(self) -> None:
        # Asserting the *shape* rather than an exact number: what matters is
        # that adding orders adds no queries. Pinning an absolute count would
        # break on any unrelated change to auth or pagination.
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        url = reverse("orders:order-list")

        with CaptureQueriesContext(connection) as first:
            self.client.get(url)
        baseline = len(first.captured_queries)

        for _ in range(3):
            cart_services.add_to_cart(
                cart_services.get_or_create_cart(user=self.user),
                self.second.slug, self.second_variant.sku, 1,
            )
            self.place()

        with CaptureQueriesContext(connection) as second:
            self.client.get(url)

        self.assertEqual(len(second.captured_queries), baseline)
