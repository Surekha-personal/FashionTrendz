"""Querysets and managers for the orders module."""

from __future__ import annotations

from django.db import models
from django.db.models import Count, Prefetch, Q, Sum
from django.utils import timezone

from apps.core.choices import (
    CANCELLABLE_ORDER_STATUSES,
    TERMINAL_ORDER_STATUSES,
    OrderStatus,
    PaymentStatus,
)


class OrderQuerySet(models.QuerySet):
    """Queries over orders."""

    def for_user(self, user: models.Model) -> "OrderQuerySet":
        """Restrict to one customer's orders."""
        return self.filter(user=user)

    def open(self) -> "OrderQuerySet":
        """Restrict to orders still moving through fulfilment."""
        return self.exclude(status__in=TERMINAL_ORDER_STATUSES)

    def completed(self) -> "OrderQuerySet":
        """Restrict to delivered orders."""
        return self.filter(status=OrderStatus.DELIVERED)

    def cancellable(self) -> "OrderQuerySet":
        """Restrict to orders a customer may still cancel themselves."""
        return self.filter(status__in=CANCELLABLE_ORDER_STATUSES)

    def paid(self) -> "OrderQuerySet":
        """Restrict to orders whose money has settled."""
        return self.filter(payment_status=PaymentStatus.PAID)

    def awaiting_payment(self) -> "OrderQuerySet":
        """Restrict to orders with money still outstanding."""
        return self.filter(payment_status=PaymentStatus.PENDING)

    def placed_between(self, start: object, end: object) -> "OrderQuerySet":
        """Restrict to orders placed in a date window, for reporting."""
        return self.filter(created_at__gte=start, created_at__lte=end)

    def recent(self, days: int = 30) -> "OrderQuerySet":
        """Restrict to orders placed in the last ``days``."""
        return self.filter(created_at__gte=timezone.now() - timezone.timedelta(days=days))

    def with_items(self) -> "OrderQuerySet":
        """Prefetch the lines an order list or detail page renders.

        Order lines carry their own snapshots, so no join to products is needed
        to render them — which is the point of snapshotting. The optional
        product join exists only for the "buy it again" link, and is left out
        here deliberately.
        """
        from apps.orders.models import OrderItem

        return self.prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.order_by("id"))
        )

    def with_detail(self) -> "OrderQuerySet":
        """Prefetch everything the order detail page renders."""
        from apps.orders.models import OrderItem, OrderStatusHistory

        return self.select_related("user").prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.order_by("id")),
            Prefetch(
                "status_history",
                queryset=OrderStatusHistory.objects.select_related("changed_by").order_by(
                    "created_at"
                ),
            ),
            "shipments",
        )

    def with_totals(self) -> "OrderQuerySet":
        """Annotate line and unit counts."""
        return self.annotate(
            _line_count=Count("items", distinct=True),
            _unit_count=Sum("items__quantity"),
        )


class OrderItemQuerySet(models.QuerySet):
    """Queries over order lines."""

    def for_user(self, user: models.Model) -> "OrderItemQuerySet":
        """Restrict to one customer's purchased lines."""
        return self.filter(order__user=user)

    def sold(self) -> "OrderItemQuerySet":
        """Restrict to lines from orders that were not cancelled or refunded.

        What "units sold" means for a bestseller ranking: a cancelled order is
        not a sale, and counting it inflates every product it touched.
        """
        return self.exclude(
            order__status__in=(
                OrderStatus.CANCELLED,
                OrderStatus.RETURNED,
                OrderStatus.REFUNDED,
            )
        )

    def with_product(self) -> "OrderItemQuerySet":
        """Join the live product and variant, for the reorder path."""
        return self.select_related("product", "variant", "order")


class ShipmentQuerySet(models.QuerySet):
    """Queries over shipments."""

    def in_transit(self) -> "ShipmentQuerySet":
        """Restrict to parcels dispatched but not yet delivered."""
        return self.filter(dispatched_at__isnull=False, delivered_at__isnull=True)

    def delivered(self) -> "ShipmentQuerySet":
        """Restrict to delivered parcels."""
        return self.filter(delivered_at__isnull=False)

    def overdue(self) -> "ShipmentQuerySet":
        """Restrict to parcels past their promised date and still undelivered.

        The operations dashboard's most useful query: these are the customers
        about to email support.
        """
        return self.filter(
            delivered_at__isnull=True,
            expected_delivery_date__lt=timezone.localdate(),
        )


OrderManager = models.Manager.from_queryset(OrderQuerySet)
OrderItemManager = models.Manager.from_queryset(OrderItemQuerySet)
ShipmentManager = models.Manager.from_queryset(ShipmentQuerySet)
