"""Cross-cutting scheduled jobs.

Tasks that span more than one module live here rather than in whichever app
they happen to touch first. "Send review reminders" reads orders, reviews and
notifications; filing it under any one of those would be arbitrary, and the
next person looking for the schedule would have to grep three apps.

Each task is a thin wrapper: it calls existing services, logs what it did, and
returns a summary dict that Celery stores as the task result. No task
implements business rules of its own — the rules already exist in the modules
that own them.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


@shared_task(name="core.rebuild_recommendations")
def rebuild_recommendations() -> dict[str, int]:
    """Recompute the co-purchase graph from order history. Nightly."""
    from apps.recommendations.services import rebuild_affinities

    result = rebuild_affinities()
    logger.info("affinity graph rebuilt: %s", result)
    return result


@shared_task(name="core.purge_browsing_history")
def purge_browsing_history(days: int = 90) -> int:
    """Delete browsing trails past their retention window. Weekly."""
    from apps.recommendations.services import purge_stale_trails

    removed = purge_stale_trails(days)
    logger.info("purged %d browsing-trail row(s) older than %d days", removed, days)
    return removed


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@shared_task(name="core.warm_analytics")
def warm_analytics() -> dict[str, Any]:
    """Recompute and cache the dashboard aggregates.

    The aggregation job. It stores nothing new — the numbers are derived from
    orders, which are already the source of truth — it just moves the cost of
    the aggregation off the first admin to open the dashboard each morning.

    A snapshot table was the alternative. It would have added a model, a
    backfill and a second definition of "revenue" that can disagree with the
    live one, in exchange for a query that already runs in well under a second.
    """
    from apps.analytics.services import warm_dashboard_cache

    result = warm_dashboard_cache()
    logger.info("analytics cache warmed: %s", result)
    return result


# ---------------------------------------------------------------------------
# Coupons
# ---------------------------------------------------------------------------


@shared_task(name="core.expire_coupons")
def expire_coupons() -> int:
    """Deactivate coupons past their validity window. Hourly.

    ``Coupon.is_expired`` already answers this at read time, so nothing is
    broken without this job. What it buys is that the admin list, the analytics
    counts and any future export all agree with the storefront instead of each
    re-deriving expiry.
    """
    from apps.coupons.models import Coupon

    expired = Coupon.objects.filter(
        is_active=True, valid_until__isnull=False, valid_until__lt=timezone.now()
    ).update(is_active=False, updated_at=timezone.now())

    if expired:
        logger.info("deactivated %d expired coupon(s)", expired)
    return expired


@shared_task(name="core.send_coupon_expiry_reminders")
def send_coupon_expiry_reminders(days_ahead: int = 3) -> int:
    """Warn customers about coupons about to expire.

    Only coupons the customer has actually held — a usage row, or a coupon
    assigned to them. Mailing every customer about every public coupon is not a
    reminder, it is a broadcast, and it is what makes people switch marketing
    off.
    """
    from apps.coupons.models import Coupon, CouponUsage
    from apps.notifications import services as notifications

    now = timezone.now()
    horizon = now + timedelta(days=days_ahead)

    expiring = Coupon.objects.filter(
        is_active=True, valid_until__gt=now, valid_until__lte=horizon
    )

    sent = 0
    for coupon in expiring:
        # Customers who have used this coupon before and may reuse it.
        holders = {
            usage.user
            for usage in CouponUsage.objects.filter(coupon=coupon).select_related("user")
            if usage.user_id
        }
        if not holders:
            continue

        days_left = max((coupon.valid_until - now).days, 1)
        sent += notifications.notify_many(
            holders,
            "coupon_expiring",
            {
                "code": coupon.code,
                "days_left": days_left,
                "expires_on": coupon.valid_until.date().isoformat(),
                "discount_display": str(coupon),
                "minimum": coupon.minimum_order_value,
                "currency": "INR",
            },
        )

    logger.info("sent %d coupon-expiry reminder(s)", sent)
    return sent


# ---------------------------------------------------------------------------
# Orders and carts
# ---------------------------------------------------------------------------


@shared_task(name="core.send_order_reminders")
def send_order_reminders(hours: int = 24) -> int:
    """Remind customers about orders still awaiting payment.

    One reminder per order, not a drip campaign: the suppression check in the
    notification signals covers repeats, and an order that is still unpaid a
    week later is a support case rather than a nudge.
    """
    from apps.core.choices import OrderStatus, PaymentStatus
    from apps.notifications import services as notifications
    from apps.orders.models import Order

    cutoff = timezone.now() - timedelta(hours=hours)
    stale = Order.objects.filter(
        status=OrderStatus.PENDING,
        payment_status=PaymentStatus.PENDING,
        created_at__lt=cutoff,
    ).select_related("user")[:500]

    sent = 0
    for order in stale:
        sent += len(
            notifications.notify(
                order.user,
                "order_reminder",
                {
                    "order_number": order.order_number,
                    "total": order.grand_total,
                    "currency": order.currency,
                },
            )
        )

    logger.info("sent %d order payment reminder(s)", sent)
    return sent


@shared_task(name="core.send_abandoned_cart_reminders")
def send_abandoned_cart_reminders(hours: int = 24, days: int = 7) -> int:
    """Nudge signed-in customers who left something in their bag.

    Guest carts are skipped: there is nobody to email. The window has both ends
    — younger than ``hours`` is still an active session, older than ``days`` is
    not abandonment, it is a change of mind.
    """
    from apps.cart.models import Cart
    from apps.notifications import services as notifications

    now = timezone.now()
    carts = (
        Cart.objects.filter(
            is_active=True,
            user__isnull=False,
            updated_at__lt=now - timedelta(hours=hours),
            updated_at__gt=now - timedelta(days=days),
        )
        .select_related("user")
        .prefetch_related("items")[:500]
    )

    sent = 0
    for cart in carts:
        item_count = cart.items.count()
        if not item_count:
            continue
        sent += len(
            notifications.notify(
                cart.user, "abandoned_cart", {"item_count": item_count}
            )
        )

    logger.info("sent %d abandoned-cart reminder(s)", sent)
    return sent


@shared_task(name="core.clean_abandoned_carts")
def clean_abandoned_carts(days: int = 30) -> int:
    """Deactivate carts nobody has touched in ``days``.

    Deactivated, not deleted. The rows are the only record of what a customer
    nearly bought, which is the single most useful input to merchandising that
    a store throws away.
    """
    from apps.cart.models import Cart

    cutoff = timezone.now() - timedelta(days=days)
    closed = Cart.objects.filter(is_active=True, updated_at__lt=cutoff).update(
        is_active=False, updated_at=timezone.now()
    )

    if closed:
        logger.info("deactivated %d abandoned cart(s)", closed)
    return closed


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


@shared_task(name="core.release_stale_payments")
def release_stale_payments(minutes: int = 30) -> int:
    """Cancel payment intents the customer never completed. Hourly.

    A payment left open holds reserved stock. Half an hour is well past any
    real checkout, and the customer can always start a new one.
    """
    from apps.payments.models import Payment, PaymentState

    stale = Payment.objects.stale(minutes)
    cancelled = stale.update(
        status=PaymentState.CANCELLED,
        failure_reason="Abandoned at checkout.",
        updated_at=timezone.now(),
    )

    if cancelled:
        logger.info("cancelled %d stale payment intent(s)", cancelled)
    return cancelled


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


@shared_task(name="core.send_review_reminders")
def send_review_reminders(days_after: int = 5, window: int = 2) -> int:
    """Ask customers to review what they received.

    A window rather than "everything older than N days", because this runs
    daily: an open-ended filter would re-ask about the same purchase every
    morning until they reviewed it or died.
    """
    from apps.notifications import services as notifications
    from apps.orders.models import OrderItem
    from apps.reviews.services import REVIEWABLE_ORDER_STATUSES

    now = timezone.now()
    items = (
        OrderItem.objects.filter(
            order__status__in=REVIEWABLE_ORDER_STATUSES,
            order__delivered_at__lte=now - timedelta(days=days_after),
            order__delivered_at__gt=now - timedelta(days=days_after + window),
            review__isnull=True,
        )
        .select_related("order", "order__user")[:500]
    )

    sent = 0
    for item in items:
        sent += len(
            notifications.notify(
                item.order.user,
                "review_reminder",
                {
                    "product_name": item.product_name,
                    "product_slug": item.product_slug,
                    "order_number": item.order.order_number,
                },
            )
        )

    logger.info("sent %d review reminder(s)", sent)
    return sent
