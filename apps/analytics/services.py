"""Analytics services.

Every figure the admin dashboard and the reports show is computed here, from
the tables the operational modules already own. There are no analytics models,
no snapshot table and no ETL step.

That is a deliberate trade. A snapshot table would make yesterday's revenue a
constant-time read, but it would also create a second definition of "revenue"
that can disagree with the orders table — and reconciling those two numbers is
a support burden that outlives whoever introduced it. At this catalogue size
the aggregates run in well under a second, and the scheduled ``warm_analytics``
job moves even that cost off the first admin to open the page each morning.

Two rules hold throughout:

* **Revenue counts money that was actually collected.** Cancelled and pending
  orders are excluded everywhere. A dashboard that counts abandoned checkouts
  as revenue is worse than no dashboard.
* **Every function takes an optional window** and defaults to "all time", so
  the same function serves a dashboard card, a date-filtered chart and a
  report row.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.db.models import (
    Avg,
    Count,
    DecimalField,
    F,
    Q,
    QuerySet,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone

from apps.core.choices import OrderStatus, PaymentStatus
from apps.orders.models import Order, OrderItem

ZERO = Decimal("0.00")

#: Order states that represent money the business actually earned. Pending and
#: cancelled orders are intent and noise; counting them inflates every figure
#: on the dashboard.
REVENUE_STATUSES: tuple[str, ...] = (
    OrderStatus.CONFIRMED,
    OrderStatus.PROCESSING,
    OrderStatus.PACKED,
    OrderStatus.SHIPPED,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
)

#: How long a dashboard aggregate stays cached.
DASHBOARD_CACHE_TTL: int = 900
DASHBOARD_CACHE_KEY = "analytics:dashboard"

#: Stock level below which a variant is "running low" rather than "in stock".
LOW_STOCK_THRESHOLD: int = 5


def _money(field: str) -> Any:
    """Return a ``Sum`` that yields 0.00 rather than None on an empty set.

    Every caller would otherwise write ``or Decimal("0.00")``, and the one that
    forgets ships a dashboard showing "None".
    """
    return Coalesce(
        Sum(field), Value(ZERO), output_field=DecimalField(max_digits=14, decimal_places=2)
    )


def _window(
    queryset: QuerySet, start: Any = None, end: Any = None, field: str = "created_at"
) -> QuerySet:
    """Apply an optional date window to ``queryset``."""
    if start:
        queryset = queryset.filter(**{f"{field}__gte": start})
    if end:
        queryset = queryset.filter(**{f"{field}__lte": end})
    return queryset


def revenue_orders(start: Any = None, end: Any = None) -> QuerySet[Order]:
    """Return the orders every revenue figure is computed from.

    The single definition of "an order that counts". Every function below
    starts here, so changing what qualifies is a one-line change rather than a
    grep across the module.
    """
    return _window(Order.objects.filter(status__in=REVENUE_STATUSES), start, end)


def period_bounds(days: int) -> tuple[datetime, datetime]:
    """Return the ``(start, end)`` of the last ``days`` days."""
    end = timezone.now()
    return end - timedelta(days=days), end


# ---------------------------------------------------------------------------
# Revenue and sales
# ---------------------------------------------------------------------------


def get_revenue(start: Any = None, end: Any = None) -> dict[str, Any]:
    """Return gross revenue and its components for a window.

    Broken out rather than returned as one number, because "revenue went up"
    and "discounts went down" are different stories and finance needs to tell
    them apart.
    """
    aggregate = revenue_orders(start, end).aggregate(
        gross=_money("grand_total"),
        subtotal=_money("subtotal"),
        discount=_money("discount"),
        coupon_discount=_money("coupon_discount"),
        tax=_money("tax"),
        shipping=_money("shipping_charge"),
        platform_fee=_money("platform_fee"),
        orders=Count("id"),
    )

    refunded = get_refund_total(start, end)
    aggregate["refunded"] = refunded
    # Net is what the business keeps: gross minus everything handed back.
    aggregate["net"] = aggregate["gross"] - refunded
    return aggregate


def get_sales_summary(start: Any = None, end: Any = None) -> dict[str, Any]:
    """Return unit and line counts alongside the money."""
    lines = _window(
        OrderItem.objects.filter(order__status__in=REVENUE_STATUSES),
        start,
        end,
        field="order__created_at",
    )
    aggregate = lines.aggregate(
        units=Coalesce(Sum("quantity"), 0),
        lines=Count("id"),
        products=Count("product_id", distinct=True),
    )
    aggregate["revenue"] = get_revenue(start, end)["gross"]
    return aggregate


def get_average_order_value(start: Any = None, end: Any = None) -> Decimal:
    """Return the mean order total.

    Computed with ``AVG`` rather than revenue divided by count, so an empty
    window returns 0.00 instead of dividing by zero.
    """
    value = revenue_orders(start, end).aggregate(avg=Avg("grand_total"))["avg"]
    return Decimal(value).quantize(Decimal("0.01")) if value else ZERO


def get_revenue_series(days: int = 30) -> list[dict[str, Any]]:
    """Return daily revenue for the last ``days``, for the dashboard chart.

    One ``GROUP BY`` with the gaps filled in Python. Days with no orders must
    still appear, or the chart draws a line straight through a quiet week and
    makes it look busy.
    """
    start, end = period_bounds(days)

    rows = {
        row["day"]: row
        for row in revenue_orders(start, end)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(revenue=_money("grand_total"), orders=Count("id"))
        .order_by("day")
    }

    today = timezone.localdate()
    series = []
    for offset in range(days, -1, -1):
        day = today - timedelta(days=offset)
        row = rows.get(day)
        series.append(
            {
                "date": day.isoformat(),
                "revenue": row["revenue"] if row else ZERO,
                "orders": row["orders"] if row else 0,
            }
        )
    return series


def get_monthly_revenue(months: int = 12) -> list[dict[str, Any]]:
    """Return revenue by calendar month, newest last."""
    start = timezone.now() - timedelta(days=months * 31)
    return list(
        revenue_orders(start)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(revenue=_money("grand_total"), orders=Count("id"))
        .order_by("month")
    )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def get_order_summary(start: Any = None, end: Any = None) -> dict[str, Any]:
    """Return order counts by status, plus the totals that matter."""
    scoped = _window(Order.objects.all(), start, end)

    by_status = {
        row["status"]: row["total"]
        for row in scoped.values("status").annotate(total=Count("id"))
    }
    by_payment = {
        row["payment_status"]: row["total"]
        for row in scoped.values("payment_status").annotate(total=Count("id"))
    }

    total = sum(by_status.values())
    delivered = by_status.get(OrderStatus.DELIVERED, 0)
    cancelled = by_status.get(OrderStatus.CANCELLED, 0)

    return {
        "total": total,
        "delivered": delivered,
        "cancelled": cancelled,
        "pending": by_status.get(OrderStatus.PENDING, 0),
        "in_transit": by_status.get(OrderStatus.SHIPPED, 0)
        + by_status.get(OrderStatus.OUT_FOR_DELIVERY, 0),
        # Read as a share of all orders, so a spike is visible without knowing
        # the absolute numbers.
        "cancellation_rate": round(cancelled * 100 / total, 2) if total else 0.0,
        "fulfilment_rate": round(delivered * 100 / total, 2) if total else 0.0,
        "by_status": by_status,
        "by_payment_status": by_payment,
    }


def get_order_series(days: int = 30) -> list[dict[str, Any]]:
    """Return daily order counts split by outcome."""
    start, _ = period_bounds(days)
    return list(
        _window(Order.objects.all(), start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            total=Count("id"),
            delivered=Count("id", filter=Q(status=OrderStatus.DELIVERED)),
            cancelled=Count("id", filter=Q(status=OrderStatus.CANCELLED)),
        )
        .order_by("day")
    )


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


def get_customer_summary(start: Any = None, end: Any = None) -> dict[str, Any]:
    """Return customer counts, including the returning-customer share.

    "Returning" means two or more revenue orders, ever — not within the window.
    A customer who bought last year and again today is returning, and scoping
    the definition to the window would call them new.
    """
    from apps.users.models import User

    total = User.objects.filter(is_staff=False).count()
    new = _window(User.objects.filter(is_staff=False), start, end).count()

    buyers = (
        Order.objects.filter(status__in=REVENUE_STATUSES)
        .values("user_id")
        .annotate(orders=Count("id"))
    )
    # Counted in SQL, not in Python. Summing a generator over this queryset
    # pulls one row per customer into memory to answer a question the database
    # can answer with a HAVING clause.
    buyer_count = buyers.count()
    returning = buyers.filter(orders__gt=1).count()

    return {
        "total": total,
        "new": new,
        "buyers": buyer_count,
        "returning": returning,
        "returning_rate": round(returning * 100 / buyer_count, 2) if buyer_count else 0.0,
        # What share of registrations ever became a customer. The single most
        # useful number on the page and the one nobody computes.
        "conversion_rate": round(buyer_count * 100 / total, 2) if total else 0.0,
    }


def get_top_customers(limit: int = 10, start: Any = None, end: Any = None) -> list[dict[str, Any]]:
    """Return the highest-spending customers in a window."""
    return list(
        revenue_orders(start, end)
        .values("user_id", "user__email", "user__first_name")
        .annotate(orders=Count("id"), spent=_money("grand_total"))
        .order_by("-spent")[:limit]
    )


# ---------------------------------------------------------------------------
# Products, brands, categories
# ---------------------------------------------------------------------------


def get_top_products(limit: int = 10, start: Any = None, end: Any = None) -> list[dict[str, Any]]:
    """Return the best-selling products by units, with their revenue.

    Grouped on the *snapshot* name held on the order line rather than joining
    ``Product``. Order lines freeze what was sold; a product later renamed or
    deleted still has to appear in last quarter's numbers.
    """
    lines = _window(
        OrderItem.objects.filter(order__status__in=REVENUE_STATUSES),
        start,
        end,
        field="order__created_at",
    )
    return list(
        lines.values("product_id", "product_name", "product_slug", "brand_name")
        .annotate(units=Coalesce(Sum("quantity"), 0), revenue=_money("grand_total"))
        .order_by("-units", "-revenue")[:limit]
    )


def get_top_categories(limit: int = 10, start: Any = None, end: Any = None) -> list[dict[str, Any]]:
    """Return revenue by category.

    Joins ``Product`` because order lines do not snapshot the taxonomy. A
    product moved between categories is therefore reported under its current
    one, which is what merchandising means when they ask.
    """
    lines = _window(
        OrderItem.objects.filter(
            order__status__in=REVENUE_STATUSES, product__isnull=False
        ),
        start,
        end,
        field="order__created_at",
    )
    return list(
        lines.values("product__category__name", "product__category__slug")
        .annotate(units=Coalesce(Sum("quantity"), 0), revenue=_money("grand_total"))
        .order_by("-revenue")[:limit]
    )


def get_top_brands(limit: int = 10, start: Any = None, end: Any = None) -> list[dict[str, Any]]:
    """Return revenue by brand, from the snapshot on the order line."""
    lines = _window(
        OrderItem.objects.filter(order__status__in=REVENUE_STATUSES),
        start,
        end,
        field="order__created_at",
    )
    return list(
        lines.exclude(brand_name="")
        .values("brand_name")
        .annotate(units=Coalesce(Sum("quantity"), 0), revenue=_money("grand_total"))
        .order_by("-revenue")[:limit]
    )


def get_product_summary() -> dict[str, Any]:
    """Return catalogue counts and the health of the listing."""
    from apps.products.models import Product

    total = Product.objects.count()
    return {
        "total": total,
        "active": Product.objects.filter(is_active=True).count(),
        "published": Product.objects.visible().count(),
        "out_of_stock": Product.objects.filter(total_stock__lte=0).count(),
        "unrated": Product.objects.filter(rating_count=0).count(),
        "on_sale": Product.objects.filter(discount_percentage__gt=0).count(),
    }


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def get_inventory_summary(threshold: int = LOW_STOCK_THRESHOLD) -> dict[str, Any]:
    """Return stock health across the catalogue."""
    from apps.products.models import ProductVariant

    variants = ProductVariant.objects.all()
    return {
        "variants": variants.count(),
        "units_in_stock": variants.aggregate(total=Coalesce(Sum("stock"), 0))["total"],
        "low_stock": variants.filter(stock__gt=0, stock__lte=threshold).count(),
        "out_of_stock": variants.filter(stock__lte=0).count(),
        "threshold": threshold,
    }


def get_low_stock(limit: int = 25, threshold: int = LOW_STOCK_THRESHOLD) -> list[dict[str, Any]]:
    """Return variants running low, scarcest first — the reorder list."""
    from apps.products.models import ProductVariant

    return list(
        ProductVariant.objects.filter(stock__gt=0, stock__lte=threshold)
        .select_related("product", "product__brand")
        .values(
            "sku",
            "stock",
            "size",
            "color",
            "product__name",
            "product__slug",
            "product__brand__name",
        )
        .order_by("stock")[:limit]
    )


def get_out_of_stock(limit: int = 25) -> list[dict[str, Any]]:
    """Return variants with nothing left, most recently emptied first."""
    from apps.products.models import ProductVariant

    return list(
        ProductVariant.objects.filter(stock__lte=0)
        .select_related("product")
        .values("sku", "size", "color", "product__name", "product__slug")
        .order_by("-updated_at")[:limit]
    )


# ---------------------------------------------------------------------------
# Payments, refunds, coupons
# ---------------------------------------------------------------------------


def get_payment_summary(start: Any = None, end: Any = None) -> dict[str, Any]:
    """Return payment volume, split by gateway and by outcome."""
    from apps.payments.models import Payment, PaymentState

    scoped = _window(Payment.objects.all(), start, end)
    captured = scoped.filter(status=PaymentState.CAPTURED)

    total = scoped.count()
    succeeded = captured.count()
    failed = scoped.filter(status=PaymentState.FAILED).count()

    return {
        "total": total,
        "captured": succeeded,
        "failed": failed,
        # The number that tells you a gateway is misconfigured before support
        # does.
        "success_rate": round(succeeded * 100 / total, 2) if total else 0.0,
        "captured_value": captured.aggregate(v=_money("amount"))["v"],
        "by_gateway": list(
            captured.values("gateway").annotate(total=Count("id"), value=_money("amount"))
        ),
        "by_method": list(
            captured.values("method").annotate(total=Count("id"), value=_money("amount"))
        ),
    }


def get_refund_total(start: Any = None, end: Any = None) -> Decimal:
    """Return money actually returned to customers in a window."""
    from apps.payments.models import Refund, RefundState

    return _window(
        Refund.objects.filter(status=RefundState.PROCESSED), start, end
    ).aggregate(v=_money("amount"))["v"]


def get_refund_summary(start: Any = None, end: Any = None) -> dict[str, Any]:
    """Return refund counts, value and reasons."""
    from apps.payments.models import Refund, RefundState

    scoped = _window(Refund.objects.all(), start, end)
    processed = scoped.filter(status=RefundState.PROCESSED)
    revenue = get_revenue(start, end)["gross"]
    refunded = processed.aggregate(v=_money("amount"))["v"]

    return {
        "total": scoped.count(),
        "processed": processed.count(),
        "pending": scoped.filter(status=RefundState.PENDING).count(),
        "failed": scoped.filter(status=RefundState.FAILED).count(),
        "value": refunded,
        "refund_rate": round(float(refunded / revenue * 100), 2) if revenue else 0.0,
        "by_reason": list(
            processed.values("reason").annotate(total=Count("id"), value=_money("amount"))
        ),
    }


def get_coupon_summary(start: Any = None, end: Any = None) -> dict[str, Any]:
    """Return coupon usage and what it cost.

    Discount given is a marketing expense, and it is the number that decides
    whether a campaign was worth running.
    """
    from apps.coupons.models import Coupon, CouponUsage

    usages = _window(CouponUsage.objects.all(), start, end)
    discount = usages.aggregate(v=_money("discount_amount"))["v"]

    return {
        "active_coupons": Coupon.objects.filter(is_active=True).count(),
        "total_coupons": Coupon.objects.count(),
        "redemptions": usages.count(),
        "discount_given": discount,
        "top_coupons": list(
            usages.values("coupon__code")
            .annotate(redemptions=Count("id"), discount=_money("discount_amount"))
            .order_by("-redemptions")[:10]
        ),
    }


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


def get_review_summary(start: Any = None, end: Any = None) -> dict[str, Any]:
    """Return review volume, moderation backlog and the rating spread."""
    from apps.reviews.models import ModerationStatus, Review

    scoped = _window(Review.objects.all(), start, end)
    approved = scoped.filter(status=ModerationStatus.APPROVED)

    return {
        "total": scoped.count(),
        "approved": approved.count(),
        "pending": scoped.filter(status=ModerationStatus.PENDING).count(),
        "rejected": scoped.filter(status=ModerationStatus.REJECTED).count(),
        "verified": approved.filter(is_verified_purchase=True).count(),
        "average_rating": round(
            float(approved.aggregate(a=Avg("rating"))["a"] or 0), 2
        ),
        "by_rating": list(
            approved.values("rating").annotate(total=Count("id")).order_by("-rating")
        ),
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def get_dashboard_cards(days: int = 30) -> dict[str, Any]:
    """Return the headline figures, each with a period-on-period change.

    The comparison is against the immediately preceding window of the same
    length, so "+12%" always means "versus the previous 30 days" and never
    "versus an arbitrary baseline".
    """
    start, end = period_bounds(days)
    previous_start = start - timedelta(days=days)

    current = get_revenue(start, end)
    previous = get_revenue(previous_start, start)

    orders = get_order_summary(start, end)
    previous_orders = get_order_summary(previous_start, start)

    customers = get_customer_summary(start, end)

    return {
        "period_days": days,
        "revenue": {
            "value": current["gross"],
            "previous": previous["gross"],
            "change": _percent_change(current["gross"], previous["gross"]),
        },
        "net_revenue": {"value": current["net"]},
        "orders": {
            "value": orders["total"],
            "previous": previous_orders["total"],
            "change": _percent_change(orders["total"], previous_orders["total"]),
        },
        "average_order_value": {"value": get_average_order_value(start, end)},
        "customers": {"value": customers["new"], "total": customers["total"]},
        "returning_rate": {"value": customers["returning_rate"]},
        "cancellation_rate": {"value": orders["cancellation_rate"]},
        "refunds": {"value": current["refunded"]},
    }


def _percent_change(current: Any, previous: Any) -> float:
    """Return the percentage change, treating growth from zero as +100%.

    Dividing by a zero baseline is undefined; reporting it as infinite makes
    the card unreadable, and reporting it as zero hides a launch.
    """
    current_value = float(current or 0)
    previous_value = float(previous or 0)

    if not previous_value:
        return 100.0 if current_value else 0.0
    return round((current_value - previous_value) / previous_value * 100, 2)


def get_dashboard(days: int = 30, *, use_cache: bool = True) -> dict[str, Any]:
    """Return everything the admin dashboard renders, in one payload.

    One endpoint rather than ten, because the dashboard shows all of it at once
    and ten round trips is ten chances for one of them to be slow.
    """
    key = f"{DASHBOARD_CACHE_KEY}:{days}"
    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return cached

    start, end = period_bounds(days)
    payload = {
        "cards": get_dashboard_cards(days),
        "revenue_series": get_revenue_series(days),
        "order_series": get_order_series(days),
        "orders": get_order_summary(start, end),
        "customers": get_customer_summary(start, end),
        "products": get_product_summary(),
        "inventory": get_inventory_summary(),
        "payments": get_payment_summary(start, end),
        "refunds": get_refund_summary(start, end),
        "coupons": get_coupon_summary(start, end),
        "reviews": get_review_summary(start, end),
        "top_products": get_top_products(10, start, end),
        "top_categories": get_top_categories(10, start, end),
        "top_brands": get_top_brands(10, start, end),
    }

    if use_cache:
        cache.set(key, payload, DASHBOARD_CACHE_TTL)
    return payload


def warm_dashboard_cache() -> dict[str, Any]:
    """Recompute the dashboard for the windows the UI offers.

    Called by the scheduled aggregation job. Warming exactly the windows the
    frontend has buttons for means every click is a cache hit.
    """
    warmed = []
    for days in (7, 30, 90):
        cache.delete(f"{DASHBOARD_CACHE_KEY}:{days}")
        get_dashboard(days)
        warmed.append(days)
    return {"warmed": warmed}


def invalidate_dashboard_cache() -> None:
    """Drop every cached dashboard window."""
    cache.delete_many([f"{DASHBOARD_CACHE_KEY}:{days}" for days in (7, 30, 90)])


# ---------------------------------------------------------------------------
# Operational queues
# ---------------------------------------------------------------------------


def get_recent_orders(limit: int = 10) -> QuerySet[Order]:
    """Return the newest orders for the dashboard's activity strip."""
    return Order.objects.select_related("user").order_by("-created_at")[:limit]


def get_pending_reviews(limit: int = 10) -> QuerySet:
    """Return the moderation backlog, oldest first."""
    from apps.reviews.services import get_moderation_queue

    return get_moderation_queue()[:limit]


def get_refund_queue(limit: int = 10) -> QuerySet:
    """Return refunds awaiting action, oldest first.

    Oldest first because a refund is a customer waiting for their own money,
    and the one that has waited longest is the one about to become a complaint.
    """
    from apps.payments.models import Refund, RefundState

    return (
        Refund.objects.filter(status__in=(RefundState.PENDING, RefundState.PROCESSING))
        .select_related("payment", "payment__order", "payment__order__user")
        .order_by("created_at")[:limit]
    )
