"""Querysets and managers for the wishlist module."""

from __future__ import annotations

from django.db import models
from django.db.models import Count, Prefetch


class WishlistQuerySet(models.QuerySet):
    """Queries over wishlists."""

    def for_user(self, user: models.Model) -> "WishlistQuerySet":
        """Restrict to one user's wishlist."""
        return self.filter(user=user)

    def with_items(self) -> "WishlistQuerySet":
        """Prefetch items with their products loaded for card rendering.

        The nested prefetch matters: without it, serialising twenty wishlist
        items costs twenty queries for brands and twenty for primary images.
        ``with_card_data()`` is the same loader the product listing uses, so
        the wishlist page and the listing page render identical cards at the
        same query cost.
        """
        from apps.products.models import Product
        from apps.wishlist.models import WishlistItem

        return self.prefetch_related(
            Prefetch(
                "items",
                queryset=WishlistItem.objects.select_related("product").prefetch_related(
                    Prefetch("product", queryset=Product.objects.with_card_data())
                ).order_by("-created_at"),
            )
        )

    def with_counts(self) -> "WishlistQuerySet":
        """Annotate the item count.

        Underscore-prefixed: ``Wishlist.item_count`` is a read-only property,
        and annotating under that name raises ``AttributeError`` while Django
        builds the row.
        """
        return self.annotate(_item_count=Count("items", distinct=True))


class WishlistItemQuerySet(models.QuerySet):
    """Queries over wishlist entries."""

    def for_user(self, user: models.Model) -> "WishlistItemQuerySet":
        """Restrict to one user's entries."""
        return self.filter(wishlist__user=user)

    def visible(self) -> "WishlistItemQuerySet":
        """Restrict to entries whose product is still purchasable.

        A product deactivated or unpublished after being wishlisted must not
        appear on the wishlist page — the row stays so the customer keeps it if
        the product returns, but it is hidden while it cannot be bought.
        """
        from django.utils import timezone

        return self.filter(
            product__is_active=True,
            product__published_at__isnull=False,
            product__published_at__lte=timezone.now(),
            product__category__is_active=True,
        )

    def with_product(self) -> "WishlistItemQuerySet":
        """Load each entry's product ready for card rendering."""
        from apps.products.models import Product

        return self.prefetch_related(
            Prefetch("product", queryset=Product.objects.with_card_data())
        )

    def recent(self) -> "WishlistItemQuerySet":
        """Newest additions first."""
        return self.order_by("-created_at")


WishlistManager = models.Manager.from_queryset(WishlistQuerySet)
WishlistItemManager = models.Manager.from_queryset(WishlistItemQuerySet)
