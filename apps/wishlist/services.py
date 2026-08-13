"""Wishlist business logic.

Views resolve permissions, call a function here, and serialise the result.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F, QuerySet

from apps.core.exceptions import BusinessRuleViolation
from apps.products.models import Product
from apps.wishlist.models import Wishlist, WishlistItem


def get_or_create_wishlist(user: Any) -> Wishlist:
    """Return the user's wishlist, creating it on first use.

    Lazily rather than on registration: most accounts never save anything, and
    a row per signup is a table full of empty containers.
    """
    wishlist, _created = Wishlist.objects.get_or_create(user=user)
    return wishlist


def get_wishlist_items(user: Any, *, visible_only: bool = True) -> QuerySet[WishlistItem]:
    """Return a user's saved products, newest first."""
    queryset = WishlistItem.objects.for_user(user)
    if visible_only:
        queryset = queryset.visible()
    return queryset.with_product().select_related("product").recent()


def get_wishlist_count(user: Any) -> int:
    """Return the navbar badge count.

    Counts only purchasable products, so the badge matches what the wishlist
    page actually renders. A badge showing 7 above a page listing 5 is a bug
    report.
    """
    return WishlistItem.objects.for_user(user).visible().count()


def _resolve_product(slug: str) -> Product:
    """Return a visible product by slug, or raise a domain error."""
    product = Product.objects.visible().filter(slug=slug).first()
    if product is None:
        raise BusinessRuleViolation("This product is not available.")
    return product


@transaction.atomic
def add_to_wishlist(user: Any, product_slug: str) -> tuple[WishlistItem, bool]:
    """Save a product, returning ``(item, created)``.

    Adding something already saved is a no-op rather than an error: the
    frontend fires this from a heart icon, and a double tap must not produce a
    red toast.
    """
    wishlist = get_or_create_wishlist(user)
    product = _resolve_product(product_slug)

    try:
        item, created = WishlistItem.objects.get_or_create(
            wishlist=wishlist, product=product
        )
    except IntegrityError:
        # Two concurrent taps: the unique constraint rejected the loser. The
        # row exists either way, which is what the caller asked for.
        item = WishlistItem.objects.get(wishlist=wishlist, product=product)
        created = False

    if created:
        _adjust_wishlist_counter(product, 1)

    return item, created


@transaction.atomic
def remove_from_wishlist(user: Any, product_slug: str) -> bool:
    """Remove a product, returning whether anything was removed."""
    wishlist = get_or_create_wishlist(user)
    deleted, _ = WishlistItem.objects.filter(
        wishlist=wishlist, product__slug=product_slug
    ).delete()

    if deleted:
        product = Product.objects.filter(slug=product_slug).first()
        if product is not None:
            _adjust_wishlist_counter(product, -1)

    return bool(deleted)


@transaction.atomic
def toggle_wishlist(user: Any, product_slug: str) -> dict[str, Any]:
    """Add the product if absent, remove it if present.

    One endpoint for the heart icon, so the client needs no local state to
    decide which call to make — it just reports the tap.
    """
    wishlist = get_or_create_wishlist(user)
    existing = WishlistItem.objects.filter(
        wishlist=wishlist, product__slug=product_slug
    ).first()

    if existing is not None:
        product = existing.product
        existing.delete()
        _adjust_wishlist_counter(product, -1)
        return {"in_wishlist": False, "count": get_wishlist_count(user)}

    add_to_wishlist(user, product_slug)
    return {"in_wishlist": True, "count": get_wishlist_count(user)}


@transaction.atomic
def clear_wishlist(user: Any) -> int:
    """Remove everything, returning how many entries were removed."""
    wishlist = get_or_create_wishlist(user)
    product_ids = list(wishlist.items.values_list("product_id", flat=True))
    deleted, _ = wishlist.items.all().delete()

    if product_ids:
        Product.objects.filter(pk__in=product_ids, wishlist_count__gt=0).update(
            wishlist_count=F("wishlist_count") - 1
        )

    return deleted


def is_in_wishlist(user: Any, product_slug: str) -> bool:
    """Return whether a product is saved, for the product page's heart state."""
    if not (user and user.is_authenticated):
        return False
    return WishlistItem.objects.for_user(user).filter(product__slug=product_slug).exists()


def wishlist_product_slugs(user: Any) -> set[str]:
    """Return every saved slug in one query.

    Lets a listing page mark hearts without asking per card, which would be one
    query per product.
    """
    if not (user and user.is_authenticated):
        return set()
    return set(
        WishlistItem.objects.for_user(user).values_list("product__slug", flat=True)
    )


@transaction.atomic
def move_to_cart(
    user: Any,
    product_slug: str,
    variant_sku: str,
    quantity: int = 1,
) -> dict[str, Any]:
    """Move a saved product into the cart.

    A variant is required because a wishlist entry has no size or colour — the
    picker in the "move to bag" modal is what supplies it.

    Removing from the wishlist happens only after the cart write succeeds, and
    the whole thing is one transaction: a stock failure must not leave the
    customer with the item gone from both places.
    """
    from apps.cart.services import add_to_cart, get_or_create_cart

    wishlist = get_or_create_wishlist(user)
    item = WishlistItem.objects.filter(
        wishlist=wishlist, product__slug=product_slug
    ).first()
    if item is None:
        raise BusinessRuleViolation("This product is not in your wishlist.")

    cart = get_or_create_cart(user=user)
    cart_item = add_to_cart(cart, product_slug, variant_sku, quantity)

    product = item.product
    item.delete()
    _adjust_wishlist_counter(product, -1)

    return {
        "cart_item": cart_item,
        "wishlist_count": get_wishlist_count(user),
    }


def _adjust_wishlist_counter(product: Product, delta: int) -> None:
    """Move the product's denormalised wishlist counter by ``delta``.

    Applied with ``F()`` so concurrent saves each count. The guard on the
    decrement keeps the ``PositiveIntegerField`` from being driven negative by
    a double-fire, which would raise at the database level.
    """
    queryset = Product.objects.filter(pk=product.pk)
    if delta < 0:
        queryset = queryset.filter(wishlist_count__gt=0)
    queryset.update(wishlist_count=F("wishlist_count") + delta)
