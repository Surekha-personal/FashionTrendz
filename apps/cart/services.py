"""Cart business logic.

Everything that mutates a cart is here, wrapped in a transaction, and every
mutation re-derives the totals afterwards so the stored money is never stale.

Two rules this module exists to keep honest:

* **stock is never reserved by the cart.** Adding to a bag holds nothing;
  reservation happens at checkout. Otherwise anyone can empty the store by
  filling a bag and walking away.
* **availability is checked at write time and again at read time.** Between the
  two, someone else may have bought the last unit — so the cart page reports
  per-line availability rather than pretending the earlier check still holds.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from apps.cart.models import (
    MAX_LINES_PER_CART,
    MAX_QUANTITY_PER_LINE,
    Cart,
    CartItem,
)
from apps.core.constants import DEFAULT_CURRENCY
from apps.core.exceptions import BusinessRuleViolation, InsufficientStock
from apps.core.utils import quantise_money
from apps.products.models import Product, ProductVariant


# ---------------------------------------------------------------------------
# Money settings
# ---------------------------------------------------------------------------


def _money_setting(name: str, default: str) -> Decimal:
    """Return a Decimal money setting."""
    return Decimal(str(getattr(settings, name, default)))


def free_shipping_threshold() -> Decimal:
    """Order value at or above which shipping is free."""
    return _money_setting("CART_FREE_SHIPPING_THRESHOLD", "999.00")


def shipping_charge() -> Decimal:
    """Flat shipping charge applied below the free-shipping threshold."""
    return _money_setting("CART_SHIPPING_CHARGE", "79.00")


def platform_fee() -> Decimal:
    """Flat platform fee applied to any non-empty cart."""
    return _money_setting("CART_PLATFORM_FEE", "20.00")


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


@transaction.atomic
def get_or_create_cart(
    *, user: Any = None, session_key: str = "", currency: str = DEFAULT_CURRENCY
) -> Cart:
    """Return the caller's active cart, creating one if needed.

    Exactly one of ``user`` and ``session_key`` must identify the owner, which
    mirrors the check constraint on the model.
    """
    if user is not None and getattr(user, "is_authenticated", False):
        cart, _created = Cart.objects.get_or_create(
            user=user,
            is_active=True,
            defaults={"session_key": "", "currency": currency},
        )
        return cart

    if not session_key:
        raise BusinessRuleViolation(
            "A session is required to hold a guest cart."
        )

    cart, _created = Cart.objects.get_or_create(
        session_key=session_key,
        user__isnull=True,
        is_active=True,
        defaults={"user": None, "currency": currency},
    )
    return cart


def get_cart(*, user: Any = None, session_key: str = "") -> Cart | None:
    """Return the caller's active cart without creating one.

    Used by the badge endpoint, which must not write a row on every anonymous
    page view — that is how a carts table grows to millions of empty rows.
    """
    if user is not None and getattr(user, "is_authenticated", False):
        return Cart.objects.active().for_user(user).with_totals().first()
    if session_key:
        return Cart.objects.active().for_session(session_key).with_totals().first()
    return None


def load_cart(cart: Cart) -> Cart:
    """Return the cart with every row the cart page renders prefetched."""
    return (
        Cart.objects.filter(pk=cart.pk).with_items().with_totals().first() or cart
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def resolve_variant(product_slug: str, variant_sku: str) -> tuple[Product, ProductVariant]:
    """Return the product and variant for a slug/SKU pair, or raise.

    Checks the full chain the storefront implies — the product is visible, the
    variant belongs to *that* product, and the variant is active. Skipping the
    ownership check would let a caller pair any SKU with any slug and buy a
    ₹90,000 coat at a ₹499 tee's price.
    """
    product = Product.objects.visible().filter(slug=product_slug).first()
    if product is None:
        raise BusinessRuleViolation("This product is not available.")

    variant = ProductVariant.objects.filter(
        sku=variant_sku, product=product, is_active=True
    ).first()
    if variant is None:
        raise BusinessRuleViolation(
            "That size or colour is not available for this product."
        )

    return product, variant


def assert_stock(variant: ProductVariant, quantity: int) -> None:
    """Raise unless ``quantity`` units of ``variant`` can be bought."""
    available = variant.available_stock
    if available <= 0:
        raise InsufficientStock(f"{variant.color} / {variant.size} is out of stock.")
    if quantity > available:
        raise InsufficientStock(
            f"Only {available} left in {variant.color} / {variant.size}."
        )


def assert_quantity(quantity: int) -> None:
    """Raise unless ``quantity`` is within the per-line purchase limit."""
    if quantity < 1:
        raise BusinessRuleViolation("Quantity must be at least 1.")
    if quantity > MAX_QUANTITY_PER_LINE:
        raise BusinessRuleViolation(
            f"You can buy at most {MAX_QUANTITY_PER_LINE} units of one item."
        )


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


@transaction.atomic
def add_to_cart(
    cart: Cart, product_slug: str, variant_sku: str, quantity: int = 1
) -> CartItem:
    """Add units of a variant, merging into an existing line if present.

    Adding a variant already in the bag increases that line rather than
    creating a second one — two "Navy / M" rows on a cart page is a bug report.
    The merged total is validated against stock and the purchase limit, so
    "add 6" twice cannot smuggle 12 units past a limit of 10.
    """
    assert_quantity(quantity)
    product, variant = resolve_variant(product_slug, variant_sku)

    existing = CartItem.objects.select_for_update().filter(
        cart=cart, variant=variant
    ).first()

    if existing is not None:
        merged = existing.quantity + quantity
        assert_quantity(merged)
        assert_stock(variant, merged)

        existing.quantity = merged
        # Re-adding a saved-for-later line puts it back in the bag, which is
        # what tapping "Add to bag" from the saved section means.
        existing.saved_for_later = False
        existing.save()
        _touch(cart)
        return existing

    if cart.items.count() >= MAX_LINES_PER_CART:
        raise BusinessRuleViolation(
            f"A cart can hold at most {MAX_LINES_PER_CART} different items."
        )

    assert_stock(variant, quantity)

    try:
        item = CartItem.objects.create(
            cart=cart, product=product, variant=variant, quantity=quantity
        )
    except IntegrityError:
        # Lost a race against a concurrent add of the same variant. The row
        # exists; merge into it rather than failing the shopper's tap.
        item = CartItem.objects.get(cart=cart, variant=variant)
        item.quantity = min(item.quantity + quantity, MAX_QUANTITY_PER_LINE)
        item.save()

    _touch(cart)
    return item


@transaction.atomic
def update_quantity(cart: Cart, variant_sku: str, quantity: int) -> CartItem | None:
    """Set a line's quantity outright.

    A quantity of zero removes the line, so the stepper control needs no
    special case at its lower bound.
    """
    if quantity <= 0:
        remove_from_cart(cart, variant_sku)
        return None

    assert_quantity(quantity)
    item = _get_line(cart, variant_sku)
    assert_stock(item.variant, quantity)

    item.quantity = quantity
    item.save()
    _touch(cart)
    return item


@transaction.atomic
def change_quantity(cart: Cart, variant_sku: str, delta: int) -> CartItem | None:
    """Move a line's quantity by ``delta``, for the +/- stepper buttons."""
    item = _get_line(cart, variant_sku)
    return update_quantity(cart, variant_sku, item.quantity + delta)


@transaction.atomic
def remove_from_cart(cart: Cart, variant_sku: str) -> bool:
    """Remove a line, returning whether anything was removed."""
    deleted, _ = CartItem.objects.filter(cart=cart, variant__sku=variant_sku).delete()
    if deleted:
        _touch(cart)
    return bool(deleted)


@transaction.atomic
def clear_cart(cart: Cart, *, include_saved: bool = False) -> int:
    """Empty the cart, optionally including saved-for-later lines.

    Saved items survive by default: "empty bag" means the bag, not the things
    the shopper deliberately set aside.
    """
    queryset = cart.items.all() if include_saved else cart.items.filter(
        saved_for_later=False
    )
    removed, _ = queryset.delete()
    _touch(cart)
    return removed


@transaction.atomic
def save_for_later(cart: Cart, variant_sku: str) -> CartItem:
    """Move a line out of the bag without discarding it."""
    item = _get_line(cart, variant_sku)
    item.saved_for_later = True
    item.save(update_fields=["saved_for_later", "updated_at"])
    _touch(cart)
    return item


@transaction.atomic
def move_to_bag(cart: Cart, variant_sku: str) -> CartItem:
    """Move a saved line back into the bag, re-checking stock first."""
    item = _get_line(cart, variant_sku)
    assert_stock(item.variant, item.quantity)

    item.saved_for_later = False
    item.save(update_fields=["saved_for_later", "updated_at"])
    _touch(cart)
    return item


@transaction.atomic
def move_to_wishlist(cart: Cart, variant_sku: str) -> dict[str, Any]:
    """Move a cart line into the wishlist.

    Requires a signed-in owner, because a wishlist belongs to an account. The
    cart line is removed only after the wishlist write succeeds — one
    transaction, so a failure cannot lose the item from both places.
    """
    from apps.wishlist.services import add_to_wishlist, get_wishlist_count

    if cart.is_guest:
        raise BusinessRuleViolation("Sign in to move items to your wishlist.")

    item = _get_line(cart, variant_sku)
    product_slug = item.product.slug

    add_to_wishlist(cart.user, product_slug)
    item.delete()
    _touch(cart)

    return {
        "product": product_slug,
        "wishlist_count": get_wishlist_count(cart.user),
        "cart_count": get_cart_count(cart),
    }


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


@transaction.atomic
def merge_carts(user: Any, session_key: str) -> Cart:
    """Fold a guest cart into the signed-in customer's cart.

    Called on the first authenticated cart request that carries a guest session
    key. Quantities are merged rather than replaced — a shopper who added two
    shirts as a guest and one after signing in expects three, not one.

    The guest cart is deactivated rather than deleted, so a merge that later
    turns out wrong can still be reconstructed from the data.
    """
    user_cart = get_or_create_cart(user=user)

    guest_cart = (
        Cart.objects.active()
        .for_session(session_key)
        .prefetch_related("items__variant")
        .first()
    )
    if guest_cart is None or guest_cart.pk == user_cart.pk:
        return user_cart

    existing = {item.variant_id: item for item in user_cart.items.all()}

    for guest_item in guest_cart.items.all():
        target = existing.get(guest_item.variant_id)

        if target is None:
            guest_item.cart = user_cart
            # Quantity may exceed the limit only if the limit changed since;
            # clamp rather than reject, because rejecting loses the shopper's
            # item at the exact moment they signed in to buy it.
            guest_item.quantity = min(guest_item.quantity, MAX_QUANTITY_PER_LINE)
            guest_item.save()
            existing[guest_item.variant_id] = guest_item
            continue

        target.quantity = min(
            target.quantity + guest_item.quantity, MAX_QUANTITY_PER_LINE
        )
        target.save()
        guest_item.delete()

    guest_cart.is_active = False
    guest_cart.save(update_fields=["is_active", "updated_at"])

    return user_cart


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------


@transaction.atomic
def recalculate_cart(cart: Cart) -> Cart:
    """Refresh every line's money snapshot from the live catalogue.

    Called at the start of every cart read. A product repriced after being
    added must show its new price — a bag quoting yesterday's number and a
    checkout charging today's is the worst possible order of events.

    Only rows whose numbers actually changed are written, so the common case
    (nothing changed) costs one select and no updates.
    """
    changed: list[CartItem] = []

    for item in cart.items.select_related("product", "variant", "cart").all():
        before = (item.unit_price, item.subtotal, item.discount, item.tax, item.total)
        item.compute_money()
        after = (item.unit_price, item.subtotal, item.discount, item.tax, item.total)
        if before != after:
            changed.append(item)

    if changed:
        CartItem.objects.bulk_update(
            changed,
            ["unit_price", "unit_mrp", "discount", "tax", "subtotal", "total"],
        )

    return cart


def get_cart_count(cart: Cart | None) -> int:
    """Return the navbar badge count, in units."""
    if cart is None:
        return 0
    return cart.unit_count


def apply_coupon(cart: Cart, code: str) -> dict[str, Any]:
    """Capture a coupon code. **Placeholder — no discount is applied yet.**

    The contract the future coupon module implements, unchanged from here:

    * validate ``code`` against the coupon table (exists, active, in date, not
      already used by this customer, cart meets its minimum);
    * compute the discount against ``cart_subtotal(cart)``;
    * write it to ``cart.coupon_discount``;
    * raise :class:`apps.core.exceptions.BusinessRuleViolation` on rejection.

    Until then the code is stored so the cart page can echo what was typed, and
    the discount stays at zero. Nothing else in the summary needs to change
    when the real implementation lands — ``get_cart_summary`` already subtracts
    ``coupon_discount``.
    """
    cart.coupon_code = (code or "").strip().upper()
    cart.coupon_discount = Decimal("0.00")
    cart.save(update_fields=["coupon_code", "coupon_discount", "updated_at"])

    return {
        "code": cart.coupon_code,
        "discount": cart.coupon_discount,
        "applied": False,
        "message": "Coupon codes are not active yet.",
    }


@transaction.atomic
def remove_coupon(cart: Cart) -> Cart:
    """Clear any captured coupon code."""
    cart.coupon_code = ""
    cart.coupon_discount = Decimal("0.00")
    cart.save(update_fields=["coupon_code", "coupon_discount", "updated_at"])
    return cart


def cart_subtotal(cart: Cart) -> Decimal:
    """Return the sum of purchasable line subtotals."""
    from django.db.models import Sum

    total = cart.items.filter(saved_for_later=False).aggregate(
        value=Sum("subtotal")
    )["value"]
    return quantise_money(total or Decimal("0.00"), cart.currency)


def get_cart_summary(cart: Cart) -> dict[str, Any]:
    """Return the price breakdown the cart and checkout pages render.

    The arithmetic, in order:

        subtotal        sum of line subtotals (already discounted prices)
        - discount      MRP minus selling price, summed — the "you saved" line
        - coupon        placeholder, always zero today
        + shipping      free at or above the threshold
        + platform fee  waived on an empty cart
        = grand total
        (tax shown separately; storefront prices are tax-inclusive)
    """
    from django.db.models import Sum

    currency = cart.currency
    lines = cart.items.filter(saved_for_later=False)

    aggregate = lines.aggregate(
        subtotal=Sum("subtotal"), discount=Sum("discount"), tax=Sum("tax")
    )
    subtotal = quantise_money(aggregate["subtotal"] or Decimal("0.00"), currency)
    discount = quantise_money(aggregate["discount"] or Decimal("0.00"), currency)
    tax = quantise_money(aggregate["tax"] or Decimal("0.00"), currency)
    coupon = quantise_money(cart.coupon_discount or Decimal("0.00"), currency)

    is_empty = subtotal <= 0
    shipping = (
        Decimal("0.00")
        if is_empty or subtotal >= free_shipping_threshold()
        else shipping_charge()
    )
    fee = Decimal("0.00") if is_empty else platform_fee()

    grand_total = quantise_money(
        max(subtotal - coupon, Decimal("0.00")) + shipping + fee, currency
    )

    return {
        "currency": currency,
        "item_count": cart.line_count,
        "unit_count": cart.unit_count,
        "subtotal": subtotal,
        "discount": discount,
        "coupon_code": cart.coupon_code,
        "coupon_discount": coupon,
        "tax": tax,
        "shipping": quantise_money(shipping, currency),
        "free_shipping_threshold": free_shipping_threshold(),
        "amount_to_free_shipping": quantise_money(
            max(free_shipping_threshold() - subtotal, Decimal("0.00")), currency
        ),
        "platform_fee": quantise_money(fee, currency),
        "grand_total": grand_total,
        "total_savings": quantise_money(discount + coupon, currency),
        "estimated_delivery_days": estimated_delivery_days(cart),
    }


def estimated_delivery_days(cart: Cart) -> int:
    """Return the delivery estimate for the whole bag.

    The slowest line governs: a bag ships together, so quoting the fastest item
    promises a date the order cannot meet.

    ponytail: reads each product's static ``estimated_delivery_days``. A real
    estimate is pincode- and courier-dependent; when a serviceability module
    exists, only this function changes.
    """
    from django.db.models import Max

    slowest = cart.items.filter(saved_for_later=False).aggregate(
        days=Max("product__estimated_delivery_days")
    )["days"]
    return slowest or 0


def get_cart_issues(cart: Cart) -> list[dict[str, Any]]:
    """Return per-line problems that would block checkout.

    Re-checked on every read because the world moves between the add and the
    checkout: a product can be deactivated, a variant retired, or the last unit
    sold to someone else. Surfacing this on the cart page is far kinder than
    failing at payment.
    """
    issues: list[dict[str, Any]] = []

    for item in cart.items.filter(saved_for_later=False).select_related(
        "product", "variant"
    ):
        if not item.product.is_visible:
            reason, available = "unavailable", 0
        elif not item.variant.is_active:
            reason, available = "variant_unavailable", 0
        elif item.variant.available_stock <= 0:
            reason, available = "out_of_stock", 0
        elif item.variant.available_stock < item.quantity:
            reason, available = "insufficient_stock", item.variant.available_stock
        else:
            continue

        issues.append(
            {
                "variant_sku": item.variant.sku,
                "product": item.product.name,
                "reason": reason,
                "requested": item.quantity,
                "available": available,
            }
        )

    return issues


def get_checkout_payload(cart: Cart) -> dict[str, Any]:
    """Return everything the checkout page needs in one call.

    Recalculates first, then reports blocking issues alongside the totals, so
    the checkout button's enabled state is a property of the response rather
    than something the client has to derive.
    """
    recalculate_cart(cart)
    issues = get_cart_issues(cart)

    return {
        "cart": load_cart(cart),
        "summary": get_cart_summary(cart),
        "issues": issues,
        "is_checkout_ready": not issues and not cart.is_empty,
    }


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _get_line(cart: Cart, variant_sku: str) -> CartItem:
    """Return a cart line by variant SKU, or raise a domain error."""
    item = (
        CartItem.objects.select_related("product", "variant")
        .filter(cart=cart, variant__sku=variant_sku)
        .first()
    )
    if item is None:
        raise BusinessRuleViolation("That item is not in your bag.")
    return item


def _touch(cart: Cart) -> None:
    """Bump the cart's ``updated_at``.

    Item writes do not update the parent row on their own, so without this an
    actively edited cart looks abandoned to the recovery job. ``update()``
    rather than ``save()`` avoids re-firing the cart's post_save signal on
    every line change.
    """
    from django.utils import timezone

    Cart.objects.filter(pk=cart.pk).update(updated_at=timezone.now())


def get_abandoned_carts(days: int = 30) -> QuerySet[Cart]:
    """Return carts untouched for ``days``, for cleanup or recovery emails."""
    return Cart.objects.abandoned(days).select_related("user")
