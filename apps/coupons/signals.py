"""Signal receivers for the coupons module.

These are what make coupons work without editing the orders module. Module 7
writes ``Order.coupon_code`` and ``Order.coupon_discount`` from the cart
snapshot and knows nothing about coupons; these receivers watch for that and
record — or release — the redemption.

Signals are right here specifically because the trigger belongs to another
app's model. Putting the call inside ``orders.services.place_order`` would mean
the orders module importing the coupons module, which inverts the dependency:
coupons needs orders, orders must not need coupons.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.choices import OrderStatus
from apps.core.logging import get_logger
from apps.orders.models import Order, OrderStatusHistory

logger = get_logger(__name__)

#: Statuses that hand a redemption back to the customer.
_RELEASING_STATUSES = frozenset({OrderStatus.CANCELLED, OrderStatus.REFUNDED})


@receiver(post_save, sender=Order, dispatch_uid="coupons.record_on_order")
def record_usage_on_order(
    sender: type, instance: Order, created: bool, **kwargs: Any
) -> None:
    """Record a redemption when an order carrying a coupon is placed."""
    if not created or not instance.coupon_code:
        return

    from apps.coupons.models import Coupon
    from apps.coupons.services import record_usage

    coupon = Coupon.objects.filter(code=instance.coupon_code).first()
    if coupon is None:
        # The order carries a code that no longer resolves — a coupon deleted
        # between checkout and placement. The order is already valid and paid
        # for; log it rather than failing the customer's purchase.
        logger.warning(
            "order %s carries unknown coupon code %s",
            instance.order_number,
            instance.coupon_code,
        )
        return

    record_usage(coupon, instance.user, instance, instance.coupon_discount)


@receiver(
    post_save,
    sender=OrderStatusHistory,
    dispatch_uid="coupons.release_on_cancellation",
)
def release_usage_on_cancellation(
    sender: type, instance: OrderStatusHistory, created: bool, **kwargs: Any
) -> None:
    """Return a redemption when its order is cancelled or refunded.

    Listens on the timeline rather than on ``Order`` itself because the
    timeline entry is written by ``transition_order`` — the single writer of
    order status — so this fires for every cancellation path: the customer
    endpoint, an admin bulk action, and the future payment-failure sweeper.
    """
    if not created or instance.status not in _RELEASING_STATUSES:
        return

    from apps.coupons.services import release_usage

    release_usage(instance.order)
