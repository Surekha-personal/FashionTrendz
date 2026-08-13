"""Signal receivers for the orders module.

Two jobs, both of them bookkeeping that must happen whatever wrote the row:

1. keep ``Product.purchase_count`` in step with real sales;
2. keep an order's ``delivery_status`` in step with its parcels.

The order state machine itself deliberately stays out of signals — it lives in
:func:`apps.orders.services.transition_order`, where the legal moves are
declared and the audit entry is written. A status change fired from a signal
would bypass both.
"""

from __future__ import annotations

from typing import Any

from django.db.models import F
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.core.logging import get_logger
from apps.orders.models import DeliveryStatus, Order, OrderItem, Shipment
from apps.products.models import Product

logger = get_logger(__name__)


@receiver(post_save, sender=OrderItem, dispatch_uid="orders.count_purchase")
def increment_purchase_count(
    sender: type, instance: OrderItem, created: bool, **kwargs: Any
) -> None:
    """Credit a sale to the product's purchase counter.

    Applied with ``F()`` so concurrent orders each count. Increments by the
    line quantity, not by one: three units of a shirt is three sales, and the
    bestseller ranking is meaningless if it counts baskets instead.

    Order lines are created with ``bulk_create``, which does **not** send
    ``post_save`` — so this fires only for lines written individually. The
    checkout path therefore credits counts explicitly; see
    ``apps.orders.services.place_order``.
    """
    if not created or not instance.product_id:
        return

    Product.objects.filter(pk=instance.product_id).update(
        purchase_count=F("purchase_count") + instance.quantity
    )


@receiver(post_save, sender=Shipment, dispatch_uid="orders.sync_delivery_status")
def sync_delivery_status(sender: type, instance: Shipment, **kwargs: Any) -> None:
    """Mirror a parcel's state onto its order's delivery status.

    Only ``delivery_status`` — never ``status``. Where the parcel is and where
    the order is are different questions, and a courier scan must not silently
    move an order through the fulfilment state machine.
    """
    if instance.delivered_at:
        target = DeliveryStatus.DELIVERED
    elif instance.dispatched_at:
        target = DeliveryStatus.DISPATCHED
    else:
        target = DeliveryStatus.NOT_DISPATCHED

    Order.objects.filter(pk=instance.order_id).exclude(
        delivery_status=target
    ).update(delivery_status=target, updated_at=timezone.now())


@receiver(post_save, sender=Order, dispatch_uid="orders.log_placement")
def log_order_placement(
    sender: type, instance: Order, created: bool, **kwargs: Any
) -> None:
    """Record every new order at INFO, for revenue reconciliation."""
    if not created:
        return

    logger.info(
        "order created number=%s user_id=%s total=%s %s",
        instance.order_number,
        instance.user_id,
        instance.grand_total,
        instance.currency,
    )
