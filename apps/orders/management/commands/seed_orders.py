"""Seed orders with items, status history, shipments, payments and refunds.

Writes the model rows directly rather than driving the checkout service. The
service reserves stock, validates coupons and enforces the state machine, all
of which is correct for a real order and wrong for a fixture: seeding two
thousand historical orders through it would drain the catalogue's stock and
refuse every order dated in the past.

Everything the service would have written is still written here — snapshots,
status history, payment and shipment rows — so the seeded data satisfies every
foreign key and every CHECK constraint, and the admin screens have complete
records to render.
"""

from __future__ import annotations

import random
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.core.choices import OrderStatus, PaymentMethod, PaymentStatus
from apps.coupons.models import Coupon, CouponUsage
from apps.orders.models import (
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatusHistory,
    Shipment,
)
from apps.payments.models import Payment, PaymentState, Refund, RefundReason, RefundState
from apps.products.models import Product
from apps.users.models import Address, User

ZERO = Decimal("0.00")

#: Realistic outcome mix. Most orders complete; a minority fail the way real
#: orders do. Seeding only happy paths leaves the cancellation and refund
#: screens with nothing to show.
STATUS_WEIGHTS: list[tuple[str, int]] = [
    (OrderStatus.DELIVERED, 58),
    (OrderStatus.SHIPPED, 9),
    (OrderStatus.OUT_FOR_DELIVERY, 5),
    (OrderStatus.PACKED, 5),
    (OrderStatus.CONFIRMED, 7),
    (OrderStatus.PENDING, 6),
    (OrderStatus.CANCELLED, 8),
    (OrderStatus.RETURNED, 2),
]

#: Forward path each status implies, for the history trail.
STATUS_PATH: list[str] = [
    OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
    OrderStatus.PACKED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
]

COURIERS = ["Bluedart", "Delhivery", "Ekart", "DTDC", "India Post", "Shadowfax"]
CANCEL_REASONS = [
    "Ordered by mistake", "Found a better price elsewhere",
    "Delivery date too late", "Changed my mind", "Duplicate order",
]


class Command(BaseCommand):
    """Create historical orders across the full status spectrum."""

    help = "Seed orders with items, payments, shipments and refunds."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--count", type=int, default=1200, help="How many orders to create."
        )
        parser.add_argument(
            "--flush", action="store_true", help="Delete existing orders first."
        )
        parser.add_argument(
            "--seed", type=int, default=20260804, help="Random seed, for reproducibility."
        )
        parser.add_argument(
            "--days", type=int, default=540, help="Spread orders over this many days."
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed orders, rolling back entirely on any error."""
        verbosity = options.get("verbosity", 1)
        rng = random.Random(options["seed"])

        customers = list(
            User.objects.filter(is_staff=False, is_active=True).only("id")
        )
        products = list(
            Product.objects.filter(is_active=True)
            .prefetch_related("variants")
            .only("id", "name", "slug", "sku", "mrp", "selling_price", "tax_percentage")
        )

        if not customers:
            raise CommandError("No customers found. Run seed_users first.")
        if not products:
            raise CommandError("No products found. Run seed_products first.")

        if options["flush"]:
            # Payments PROTECT their order, so they go first. Refunds PROTECT
            # their payment, so they go before that.
            Refund.objects.all().delete()
            Payment.objects.all().delete()
            CouponUsage.objects.all().delete()
            deleted, _ = Order.objects.all().delete()
            if verbosity:
                self.stdout.write(self.style.WARNING(f"Deleted {deleted} order row(s)."))

        existing = Order.objects.count()
        wanted = max(0, options["count"] - existing)
        if wanted == 0:
            if verbosity:
                self.stdout.write(
                    f"Orders: {existing} already present, nothing to do."
                )
            return

        addresses = {
            address.user_id: address
            for address in Address.objects.filter(is_default=True)
        }
        coupons = list(
            Coupon.objects.filter(is_active=True, is_public=True)[:8]
        )
        now = timezone.now()

        counters = {"orders": 0, "items": 0, "payments": 0,
                    "shipments": 0, "refunds": 0, "usages": 0}

        for index in range(wanted):
            placed_at = now - timezone.timedelta(
                days=rng.randint(0, options["days"]),
                hours=rng.randint(0, 23),
                minutes=rng.randint(0, 59),
            )
            self._create_order(
                sequence=existing + index + 1,
                customer=rng.choice(customers),
                addresses=addresses,
                products=products,
                coupons=coupons,
                placed_at=placed_at,
                rng=rng,
                counters=counters,
            )

        if verbosity:
            self.stdout.write(self.style.SUCCESS("Orders seeded:"))
            for label, value in counters.items():
                self.stdout.write(f"  {label:<14} {value}")
            self.stdout.write(f"  total orders   {Order.objects.count()}")

    # -- one order ----------------------------------------------------------

    def _create_order(
        self,
        *,
        sequence: int,
        customer: User,
        addresses: dict[int, Address],
        products: list[Product],
        coupons: list[Coupon],
        placed_at: Any,
        rng: random.Random,
        counters: dict[str, int],
    ) -> None:
        """Write one order and everything that hangs off it."""
        status = rng.choices(
            [s for s, _ in STATUS_WEIGHTS], weights=[w for _, w in STATUS_WEIGHTS]
        )[0]
        address = addresses.get(customer.pk)
        snapshot = self._address_snapshot(customer, address)

        chosen = rng.sample(products, k=min(rng.randint(1, 4), len(products)))
        lines = [(product, rng.randint(1, 3)) for product in chosen]

        subtotal = sum(
            (product.selling_price * quantity for product, quantity in lines), ZERO
        )
        discount = sum(
            ((product.mrp - product.selling_price) * quantity
             for product, quantity in lines),
            ZERO,
        )

        coupon = rng.choice(coupons) if coupons and rng.random() < 0.22 else None
        coupon_discount = ZERO
        if coupon and subtotal >= coupon.min_cart_value:
            coupon_discount = self._coupon_discount(coupon, subtotal)
        else:
            coupon = None

        shipping = ZERO if subtotal >= Decimal("999.00") else Decimal("79.00")
        platform_fee = Decimal("20.00")
        tax = (subtotal * Decimal("0.05")).quantize(Decimal("0.01"))
        grand_total = max(
            ZERO, subtotal - coupon_discount + shipping + platform_fee + tax
        )

        method = rng.choices(
            [PaymentMethod.UPI, PaymentMethod.CARD, PaymentMethod.COD,
             PaymentMethod.NET_BANKING, PaymentMethod.WALLET],
            weights=[42, 26, 20, 8, 4],
        )[0]
        payment_status = self._payment_status(status, method)

        order = Order.objects.create(
            user=customer,
            # Sequence rather than a timestamp: the generator is time-based and
            # two seeded orders in the same millisecond collide on the unique
            # index.
            order_number=f"FT-SEED-{sequence:07d}",
            invoice_number=(
                f"INV-{placed_at:%Y%m}-{sequence:06d}"
                if payment_status == PaymentStatus.PAID
                else ""
            ),
            shipping_address=snapshot,
            billing_address=snapshot,
            subtotal=subtotal,
            discount=discount,
            coupon_code=coupon.code if coupon else "",
            coupon_discount=coupon_discount,
            shipping_charge=shipping,
            platform_fee=platform_fee,
            tax=tax,
            grand_total=grand_total,
            payment_method=method,
            payment_status=payment_status,
            payment_reference=(
                f"pay_{rng.getrandbits(48):012x}"
                if payment_status == PaymentStatus.PAID
                else ""
            ),
            status=status,
            delivery_status=self._delivery_status(status),
            delivery_method=rng.choices(
                ["standard", "express", "scheduled"], weights=[76, 20, 4]
            )[0],
            estimated_delivery_date=(placed_at + timezone.timedelta(
                days=rng.randint(2, 9))).date(),
            delivered_at=(
                placed_at + timezone.timedelta(days=rng.randint(2, 9))
                if status in {OrderStatus.DELIVERED, OrderStatus.RETURNED}
                else None
            ),
            cancelled_at=(
                placed_at + timezone.timedelta(hours=rng.randint(1, 72))
                if status == OrderStatus.CANCELLED
                else None
            ),
            cancel_reason=(
                rng.choice(CANCEL_REASONS) if status == OrderStatus.CANCELLED else ""
            ),
            stock_committed=status not in {OrderStatus.PENDING, OrderStatus.CANCELLED},
        )
        # auto_now_add ignores an assigned value, so the placement date is
        # backdated with an UPDATE. Without this every order is dated today and
        # the revenue chart is a single spike.
        Order.objects.filter(pk=order.pk).update(created_at=placed_at)
        counters["orders"] += 1

        counters["items"] += self._create_items(order, lines, rng)
        counters["payments"] += self._create_payment(
            order, method, payment_status, placed_at, rng
        )
        self._create_history(order, status, placed_at, rng)

        if status in {OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY,
                      OrderStatus.DELIVERED, OrderStatus.RETURNED}:
            counters["shipments"] += self._create_shipment(order, placed_at, rng)

        if coupon:
            # The redemption row is written by coupons.signals on Order
            # post_save — creating one here too violates the partial unique
            # index on (coupon, order). Only the release flag is ours to set.
            if status == OrderStatus.CANCELLED:
                CouponUsage.objects.filter(order=order).update(
                    is_released=True, released_at=order.cancelled_at
                )
            counters["usages"] += CouponUsage.objects.filter(order=order).count()

        if status == OrderStatus.RETURNED or (
            status == OrderStatus.CANCELLED and payment_status == PaymentStatus.PAID
        ):
            counters["refunds"] += self._create_refund(order, status, placed_at, rng)

    # -- parts --------------------------------------------------------------

    @staticmethod
    def _address_snapshot(customer: User, address: Address | None) -> dict[str, Any]:
        """Return the frozen address JSON an order stores.

        A snapshot, not a foreign key: the delivery address on a two-year-old
        order must stay what it was, whatever the customer has since edited.
        """
        if address is None:
            return {
                "full_name": f"{customer.first_name} {customer.last_name}".strip(),
                "mobile": customer.mobile_number or "",
                "address_line_1": "Address not on file",
                "city": "Mumbai", "state": "Maharashtra",
                "country": "India", "postal_code": "400001",
            }
        return {
            "full_name": address.full_name,
            "mobile": address.mobile,
            "address_line_1": address.address_line_1,
            "address_line_2": address.address_line_2,
            "city": address.city,
            "state": address.state,
            "country": address.country,
            "postal_code": address.postal_code,
        }

    def _create_items(
        self, order: Order, lines: list[tuple[Product, int]], rng: random.Random
    ) -> int:
        """Write the snapshotted order lines."""
        created = 0
        for product, quantity in lines:
            variants = list(product.variants.all())
            variant = rng.choice(variants) if variants else None
            unit = variant.price_override if variant and variant.price_override else product.selling_price

            OrderItem.objects.create(
                order=order,
                product=product,
                variant=variant,
                product_name=product.name,
                product_slug=product.slug,
                brand_name=product.brand.name if product.brand_id else "",
                sku=variant.sku if variant else product.sku,
                size=variant.size if variant else "",
                color=variant.color if variant else "",
                image_url="",
                mrp=product.mrp,
                selling_price=unit,
                discount=(product.mrp - unit) * quantity,
                tax=(unit * quantity * Decimal("0.05")).quantize(Decimal("0.01")),
                quantity=quantity,
                subtotal=unit * quantity,
                grand_total=unit * quantity,
            )
            created += 1
        return created

    def _create_payment(
        self,
        order: Order,
        method: str,
        payment_status: str,
        placed_at: Any,
        rng: random.Random,
    ) -> int:
        """Write the payment intent, unless the order is unpaid cash on delivery."""
        if method == PaymentMethod.COD and payment_status != PaymentStatus.PAID:
            return 0

        state = {
            PaymentStatus.PAID: PaymentState.CAPTURED,
            PaymentStatus.FAILED: PaymentState.FAILED,
            PaymentStatus.CANCELLED: PaymentState.CANCELLED,
        }.get(payment_status, PaymentState.CREATED)

        payment = Payment.objects.create(
            order=order,
            gateway="razorpay" if method != PaymentMethod.COD else "cod",
            method=method,
            gateway_order_id=f"order_{rng.getrandbits(48):012x}",
            gateway_payment_id=(
                f"pay_{rng.getrandbits(48):012x}"
                if state == PaymentState.CAPTURED
                else ""
            ),
            amount=order.grand_total,
            currency=order.currency,
            status=state,
            failure_reason=(
                rng.choice([
                    "Insufficient funds.",
                    "Card declined by issuing bank.",
                    "Payment authentication failed.",
                ])
                if state == PaymentState.FAILED
                else ""
            ),
            captured_at=(
                placed_at + timezone.timedelta(minutes=rng.randint(1, 12))
                if state == PaymentState.CAPTURED
                else None
            ),
        )
        Payment.objects.filter(pk=payment.pk).update(created_at=placed_at)
        return 1

    def _create_history(
        self, order: Order, status: str, placed_at: Any, rng: random.Random
    ) -> None:
        """Write the append-only status trail up to the order's current state.

        This table, not the order's status column, is what the notification
        engine watches — so a seeded order produces a plausible timeline on the
        tracking page.
        """
        if status in {OrderStatus.CANCELLED, OrderStatus.RETURNED}:
            path = [OrderStatus.PENDING, OrderStatus.CONFIRMED]
            if status == OrderStatus.RETURNED:
                path = STATUS_PATH[:]
            path.append(status)
        else:
            path = STATUS_PATH[: STATUS_PATH.index(status) + 1]

        previous = ""
        offset = 0
        rows = []
        for step in path:
            offset += rng.randint(2, 30)
            rows.append(
                OrderStatusHistory(
                    order=order,
                    previous_status=previous,
                    status=step,
                    remarks=f"Order {step.replace('_', ' ')}.",
                )
            )
            previous = step

        OrderStatusHistory.objects.bulk_create(rows)

        # Backdate the trail so the timeline reads in order.
        hours = 0
        for row in OrderStatusHistory.objects.filter(order=order).order_by("id"):
            hours += rng.randint(3, 36)
            OrderStatusHistory.objects.filter(pk=row.pk).update(
                created_at=placed_at + timezone.timedelta(hours=hours)
            )

    def _create_shipment(
        self, order: Order, placed_at: Any, rng: random.Random
    ) -> int:
        """Write the dispatched parcel."""
        courier = rng.choice(COURIERS)
        tracking = f"{courier[:3].upper()}{rng.randint(10**9, 10**10 - 1)}"
        dispatched = placed_at + timezone.timedelta(days=rng.randint(1, 3))

        Shipment.objects.create(
            order=order,
            courier_name=courier,
            tracking_number=tracking,
            tracking_url=f"https://track.example/{courier.lower()}/{tracking}",
            dispatched_at=dispatched,
            expected_delivery_date=(dispatched + timezone.timedelta(
                days=rng.randint(2, 6))).date(),
            delivered_at=order.delivered_at,
        )
        return 1

    def _create_refund(
        self, order: Order, status: str, placed_at: Any, rng: random.Random
    ) -> int:
        """Write a refund against a captured payment."""
        payment = order.payments.filter(status=PaymentState.CAPTURED).first()
        if payment is None:
            return 0

        # Partial refunds are common on returns — one item of three goes back.
        amount = (
            payment.amount
            if status == OrderStatus.CANCELLED or rng.random() < 0.55
            else (payment.amount * Decimal("0.4")).quantize(Decimal("0.01"))
        )
        state = rng.choices(
            [RefundState.PROCESSED, RefundState.PROCESSING, RefundState.PENDING],
            weights=[80, 12, 8],
        )[0]

        Refund.objects.create(
            payment=payment,
            amount=amount,
            currency=payment.currency,
            status=state,
            reason=(
                RefundReason.ORDER_CANCELLED
                if status == OrderStatus.CANCELLED
                else RefundReason.ORDER_RETURNED
            ),
            gateway_refund_id=(
                f"rfnd_{rng.getrandbits(48):012x}"
                if state == RefundState.PROCESSED
                else ""
            ),
            reference_number=f"RF{rng.randint(10**7, 10**8 - 1)}",
            processed_at=(
                placed_at + timezone.timedelta(days=rng.randint(3, 12))
                if state == RefundState.PROCESSED
                else None
            ),
        )
        # Keep the payment's own counter consistent with its refunds; a CHECK
        # constraint holds refunded_amount within amount.
        Payment.objects.filter(pk=payment.pk).update(
            refunded_amount=min(amount, payment.amount),
            status=(
                PaymentState.REFUNDED
                if amount >= payment.amount
                else PaymentState.PARTIALLY_REFUNDED
            ),
        )
        return 1

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _coupon_discount(coupon: Coupon, subtotal: Decimal) -> Decimal:
        """Return what a coupon takes off a given subtotal."""
        if coupon.discount_type == "flat":
            return min(coupon.value, subtotal)
        if coupon.discount_type == "percentage":
            raw = (subtotal * coupon.value / Decimal("100")).quantize(Decimal("0.01"))
            return min(raw, coupon.max_discount) if coupon.max_discount else raw
        return ZERO

    @staticmethod
    def _payment_status(status: str, method: str) -> str:
        """Return the settlement state implied by an order's status."""
        if status == OrderStatus.PENDING:
            return PaymentStatus.PENDING
        if status == OrderStatus.CANCELLED:
            # Half of cancellations were paid for and need refunding; the rest
            # never got past the payment step.
            return PaymentStatus.PAID if method != PaymentMethod.COD else PaymentStatus.CANCELLED
        if status == OrderStatus.RETURNED:
            return PaymentStatus.PAID
        if method == PaymentMethod.COD:
            return (
                PaymentStatus.PAID
                if status == OrderStatus.DELIVERED
                else PaymentStatus.PENDING
            )
        return PaymentStatus.PAID

    @staticmethod
    def _delivery_status(status: str) -> str:
        """Return the courier-facing state implied by an order's status."""
        return {
            OrderStatus.SHIPPED: DeliveryStatus.IN_TRANSIT,
            OrderStatus.OUT_FOR_DELIVERY: DeliveryStatus.OUT_FOR_DELIVERY,
            OrderStatus.DELIVERED: DeliveryStatus.DELIVERED,
            # A returned order reached the customer first, so the parcel
            # state stays DELIVERED. RETURNED_TO_ORIGIN means it never
            # arrived at all, which is a different outcome.
            OrderStatus.RETURNED: DeliveryStatus.DELIVERED,
        }.get(status, DeliveryStatus.NOT_DISPATCHED)
