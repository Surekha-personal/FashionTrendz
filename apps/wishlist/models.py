"""Wishlist models.

One wishlist per user, holding at most one entry per product.

Both invariants are enforced by the database — a ``OneToOneField`` and a
``UniqueConstraint`` — rather than by application code alone. Two rapid taps on
a heart icon are two concurrent requests, and application-level "check then
insert" loses that race every time.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.mixins import BaseModel
from apps.products.models import Product
from apps.wishlist.managers import WishlistItemManager, WishlistManager


class Wishlist(BaseModel):
    """A customer's saved-for-consideration list.

    A container model rather than putting a plain FK from item to user, because
    it gives the future "share my wishlist" and "multiple named lists" features
    somewhere to attach without a data migration on every saved item.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist",
        verbose_name=_("user"),
    )

    objects = WishlistManager()

    class Meta:
        verbose_name = _("wishlist")
        verbose_name_plural = _("wishlists")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Wishlist of {self.user.email}"

    @property
    def item_count(self) -> int:
        """Return how many products are saved.

        Prefers the ``with_counts()`` annotation when the caller supplied one,
        so rendering a list of wishlists costs no query per row.
        """
        annotated = getattr(self, "_item_count", None)
        if annotated is not None:
            return annotated
        return self.items.count()

    def has_product(self, product: Product) -> bool:
        """Return whether a product is already saved."""
        return self.items.filter(product=product).exists()


class WishlistItem(BaseModel):
    """One product saved to a wishlist.

    Deliberately holds no variant. A shopper hearts "this dress", not "this
    dress in Navy, size M" — the size decision happens when they move it to the
    cart, which is exactly where the variant picker belongs.
    """

    wishlist = models.ForeignKey(
        Wishlist,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("wishlist"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        verbose_name=_("product"),
    )

    objects = WishlistItemManager()

    class Meta:
        verbose_name = _("wishlist item")
        verbose_name_plural = _("wishlist items")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["wishlist", "product"],
                name="unique_product_per_wishlist",
            ),
        ]
        indexes = [
            models.Index(
                fields=["wishlist", "-created_at"], name="wishlistitem_recent_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} in {self.wishlist}"

    @property
    def added_at(self) -> Any:
        """Alias for ``created_at``, matching the storefront's vocabulary."""
        return self.created_at
