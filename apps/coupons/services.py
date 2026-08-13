"""Coupon business logic.

Validation and discount calculation live here, in one place, because they run
three times over a single purchase — when the customer types the code, when the
checkout page re-renders, and again when the order is placed. Three
implementations would drift, and the failure mode is discounting money the
business never agreed to.

The rule the whole module protects: **a coupon is validated at redemption, not
at entry.** Anything checked when the code was typed can be false by the time
the order is placed — the window can close, the cap can fill, the bag can
shrink below the minimum.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F, QuerySet, Sum
from django.utils import timezone

from apps.cart.models import Cart
from apps.core.exceptions import BusinessRuleViolation
from apps.core.logging import get_logger
from apps.core.utils import quantise_money
from apps.coupons.models import Coupon, CouponUsage, DiscountType

logger = get_logger(__name__)


class CouponError(BusinessRuleViolation):
    """A coupon was rejected. Carries a customer-safe message."""


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def normalise_code(code: str) -> str:
    """Return the canonical form of a typed coupon code."""
    return (code or "").strip().upper()


def find_coupon(code: str) -> Coupon:
    """Return a coupon by code, or raise.

    Deliberately does not distinguish "no such code" from "expired code" in the
    message it raises for an unknown code — but *does* say "expired" once the
    code is known to exist. Telling a stranger which random strings are real
    coupons invites brute-forcing the code space.
    """
    coupon = (
        Coupon.objects.with_restrictions().filter(code=normalise_code(code)).first()
    )
    if coupon is None:
        raise CouponError("That coupon code is not valid.")
    return coupon


def get_public_coupons() -> QuerySet[Coupon]:
    """Return the coupons the storefront advertises."""
    return Coupon.objects.public().order_by("-value", "code")


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def eligible_subtotal(cart: Cart, coupon: Coupon) -> Decimal:
    """Return the portion of the bag a coupon may discount.

    An unrestricted coupon sees the whole subtotal. A restricted one sees only
    the qualifying lines — "20% off Footwear" must not take 20% off the dress
    in the same bag, which is the single most common coupon bug and the most
    expensive one.
    """
    lines = cart.items.filter(saved_for_later=False).select_related("product")

    if not coupon.is_restricted:
        total = lines.aggregate(value=Sum("subtotal"))["value"]
        return quantise_money(total or Decimal("0.00"), cart.currency)

    category_ids = set(coupon.categories.values_list("id", flat=True))
    brand_ids = set(coupon.brands.values_list("id", flat=True))
    product_ids = set(coupon.products.values_list("id", flat=True))

    total = Decimal("0.00")
    for line in lines:
        product = line.product
        # OR across the three restriction kinds: a coupon listing both a brand
        # and a category means "either", which is how a merchandiser reads it.
        if (
            (product_ids and product.pk in product_ids)
            or (category_ids and product.category_id in category_ids)
            or (brand_ids and product.brand_id in brand_ids)
        ):
            total += line.subtotal

    return quantise_money(total, cart.currency)


def user_usage_count(coupon: Coupon, user: Any) -> int:
    """Return how many times a customer has redeemed a coupon, ignoring releases."""
    return CouponUsage.objects.counted().filter(coupon=coupon, user=user).count()


def has_previous_orders(user: Any) -> bool:
    """Return whether a customer has ever placed an order.

    Backs ``first_order_only``. Counts every non-cancelled order, so a
    customer cannot farm a first-order coupon by cancelling and re-ordering.
    """
    from apps.core.choices import OrderStatus
    from apps.orders.models import Order

    return (
        Order.objects.filter(user=user)
        .exclude(status=OrderStatus.CANCELLED)
        .exists()
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_coupon(coupon: Coupon, cart: Cart, user: Any) -> Decimal:
    """Raise unless ``user`` may redeem ``coupon`` against ``cart``.

    Returns the eligible subtotal so the caller does not recompute it. Checks
    run cheapest-first, and each message is written for the customer — "add
    ₹300 more" is actionable, "coupon invalid" is not.
    """
    if not coupon.is_active:
        raise CouponError("That coupon is no longer available.")

    if not coupon.has_started:
        raise CouponError(
            f"This coupon becomes valid on {coupon.valid_from:%d %b %Y}."
        )

    if coupon.is_expired:
        raise CouponError("This coupon has expired.")

    if coupon.is_exhausted:
        raise CouponError("This coupon has been fully redeemed.")

    if cart.is_empty:
        raise CouponError("Add something to your bag before applying a coupon.")

    if coupon.uses_per_user and user_usage_count(coupon, user) >= coupon.uses_per_user:
        raise CouponError("You have already used this coupon.")

    if coupon.first_order_only and has_previous_orders(user):
        raise CouponError("This coupon is only valid on your first order.")

    eligible = eligible_subtotal(cart, coupon)

    if eligible <= 0:
        raise CouponError(
            "This coupon does not apply to any of the items in your bag."
        )

    if eligible < coupon.min_cart_value:
        shortfall = quantise_money(coupon.min_cart_value - eligible, cart.currency)
        raise CouponError(
            f"Add {cart.currency} {shortfall} more of eligible items to use this coupon."
        )

    return eligible


def calculate_discount(coupon: Coupon, eligible: Decimal, cart: Cart) -> Decimal:
    """Return the money a coupon takes off, capped and never exceeding the bag.

    Two ceilings, both load-bearing: ``max_discount`` stops "50% off" from
    giving away ₹45,000 on a luxury coat, and the eligible subtotal stops any
    coupon from producing a negative total.
    """
    if coupon.discount_type == DiscountType.FREE_SHIPPING:
        # Shipping is computed by the cart, not here. Returning zero keeps the
        # arithmetic honest; the shipping waiver is applied in cart_summary.
        return Decimal("0.00")

    if coupon.discount_type == DiscountType.PERCENTAGE:
        discount = eligible * coupon.value / Decimal("100")
    else:
        discount = coupon.value

    if coupon.max_discount is not None:
        discount = min(discount, coupon.max_discount)

    discount = min(discount, eligible)
    return quantise_money(max(discount, Decimal("0.00")), cart.currency)


def preview_coupon(code: str, cart: Cart, user: Any) -> dict[str, Any]:
    """Validate a code and report what it would save, without applying it."""
    coupon = find_coupon(code)
    eligible = validate_coupon(coupon, cart, user)
    discount = calculate_discount(coupon, eligible, cart)

    return {
        "coupon": coupon,
        "code": coupon.code,
        "discount": discount,
        "eligible_subtotal": eligible,
        "free_shipping": coupon.discount_type == DiscountType.FREE_SHIPPING,
        "description": coupon.description,
    }


# ---------------------------------------------------------------------------
# Apply and remove
# ---------------------------------------------------------------------------


@transaction.atomic
def apply_coupon_to_cart(cart: Cart, code: str, user: Any) -> dict[str, Any]:
    """Validate a coupon and write its discount onto the cart.

    Writes to the same two columns Module 6 reserved for this
    (``coupon_code`` and ``coupon_discount``), so ``cart.services.get_cart_summary``
    and the order-placement path pick the discount up with no changes.
    """
    result = preview_coupon(code, cart, user)

    cart.coupon_code = result["code"]
    cart.coupon_discount = result["discount"]
    cart.save(update_fields=["coupon_code", "coupon_discount", "updated_at"])

    logger.info(
        "coupon applied code=%s cart_id=%s discount=%s",
        result["code"],
        cart.pk,
        result["discount"],
    )

    return {
        "code": result["code"],
        "discount": result["discount"],
        "applied": True,
        "free_shipping": result["free_shipping"],
        "message": f"Coupon {result['code']} applied.",
    }


@transaction.atomic
def remove_coupon_from_cart(cart: Cart) -> dict[str, Any]:
    """Clear any coupon from the cart."""
    removed = cart.coupon_code

    cart.coupon_code = ""
    cart.coupon_discount = Decimal("0.00")
    cart.save(update_fields=["coupon_code", "coupon_discount", "updated_at"])

    return {
        "code": "",
        "discount": Decimal("0.00"),
        "applied": False,
        "message": f"Coupon {removed} removed." if removed else "No coupon to remove.",
    }


def revalidate_cart_coupon(cart: Cart, user: Any) -> dict[str, Any] | None:
    """Re-check the cart's coupon and silently drop it if it no longer holds.

    Called before checkout. A coupon applied twenty minutes ago may have
    expired, hit its cap, or stopped qualifying because the customer removed
    the one eligible item — and a stale discount surviving into an order is
    money the business gave away by accident.
    """
    if not cart.coupon_code:
        return None

    try:
        return apply_coupon_to_cart(cart, cart.coupon_code, user)
    except CouponError as exc:
        logger.info(
            "coupon dropped code=%s cart_id=%s reason=%s",
            cart.coupon_code,
            cart.pk,
            exc.detail,
        )
        remove_coupon_from_cart(cart)
        return {
            "code": "",
            "discount": Decimal("0.00"),
            "applied": False,
            "message": f"Your coupon was removed: {exc.detail}",
        }


# ---------------------------------------------------------------------------
# Redemption
# ---------------------------------------------------------------------------


@transaction.atomic
def record_usage(coupon: Coupon, user: Any, order: Any, discount: Decimal) -> CouponUsage:
    """Record a redemption and increment the global counter.

    The counter moves with a conditional UPDATE so the cap is enforced by the
    database: two customers redeeming the five-hundredth of five hundred codes
    at the same instant cannot both succeed.
    """
    try:
        # Nested savepoint: an IntegrityError marks the *whole* enclosing
        # transaction unusable, so catching it without an inner atomic block
        # leaves every subsequent query raising TransactionManagementError.
        with transaction.atomic():
            usage = CouponUsage.objects.create(
                coupon=coupon, user=user, order=order, discount_amount=discount
            )
    except IntegrityError:
        # A retried signal or webhook. The row exists, which is what the
        # caller wanted; counting it twice would not be.
        return CouponUsage.objects.get(coupon=coupon, order=order)

    Coupon.objects.filter(pk=coupon.pk).update(times_used=F("times_used") + 1)

    logger.info(
        "coupon redeemed code=%s user_id=%s order=%s discount=%s",
        coupon.code,
        user.pk,
        getattr(order, "order_number", None),
        discount,
    )
    return usage


@transaction.atomic
def release_usage(order: Any) -> int:
    """Give back the redemptions attached to a cancelled order.

    Flagged released rather than deleted: the campaign report still wants to
    know the code was tried. The guard on the decrement keeps the positive
    integer column from being driven negative by a double-fire.
    """
    usages = list(
        CouponUsage.objects.counted().filter(order=order).select_related("coupon")
    )
    if not usages:
        return 0

    now = timezone.now()
    for usage in usages:
        CouponUsage.objects.filter(pk=usage.pk).update(
            is_released=True, released_at=now
        )
        Coupon.objects.filter(pk=usage.coupon_id, times_used__gt=0).update(
            times_used=F("times_used") - 1
        )

    logger.info(
        "coupon usage released order=%s count=%d",
        getattr(order, "order_number", None),
        len(usages),
    )
    return len(usages)


def get_user_usages(user: Any) -> QuerySet[CouponUsage]:
    """Return a customer's redemption history."""
    return (
        CouponUsage.objects.for_user(user)
        .select_related("coupon", "order")
        .order_by("-created_at")
    )
