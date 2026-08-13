"""Querysets and managers for the cart module."""

from __future__ import annotations

from django.db import models
from django.db.models import Count, Prefetch, Q, Sum
from django.utils import timezone


class CartQuerySet(models.QuerySet):
    """Queries over carts."""

    def active(self) -> "CartQuerySet":
        """Restrict to carts that have not been converted into an order."""
        return self.filter(is_active=True)

    def for_user(self, user: models.Model) -> "CartQuerySet":
        """Restrict to one signed-in customer's cart."""
        return self.filter(user=user)

    def for_session(self, session_key: str) -> "CartQuerySet":
        """Restrict to one guest session's cart."""
        return self.filter(session_key=session_key, user__isnull=True)

    def guest(self) -> "CartQuerySet":
        """Restrict to carts with no owner."""
        return self.filter(user__isnull=True)

    def abandoned(self, days: int = 30) -> "CartQuerySet":
        """Carts untouched for ``days``, for cleanup and recovery emails."""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        return self.active().filter(updated_at__lt=cutoff)

    def with_items(self) -> "CartQuerySet":
        """Prefetch every row the cart page renders.

        Four queries total regardless of cart size. Without it, a ten-line cart
        costs ten queries for products, ten for variants, ten for brands and
        ten for images — and the cart page is on the critical path to revenue.
        """
        from apps.cart.models import CartItem
        from apps.products.models import Product

        return self.prefetch_related(
            Prefetch(
                "items",
                queryset=CartItem.objects.select_related("variant")
                .prefetch_related(
                    Prefetch("product", queryset=Product.objects.with_card_data())
                )
                .order_by("saved_for_later", "-created_at"),
            )
        )

    def with_totals(self) -> "CartQuerySet":
        """Annotate line and unit counts, excluding saved-for-later rows.

        Underscore-prefixed because ``Cart.line_count`` and ``Cart.unit_count``
        are read-only properties: annotating under those names makes Django
        raise ``AttributeError: can't set attribute`` while building the row.
        The properties read these aliases when present.
        """
        return self.annotate(
            _line_count=Count("items", filter=Q(items__saved_for_later=False), distinct=True),
            _unit_count=Sum("items__quantity", filter=Q(items__saved_for_later=False)),
        )


class CartItemQuerySet(models.QuerySet):
    """Queries over cart lines."""

    def active(self) -> "CartItemQuerySet":
        """Restrict to lines that count towards the total.

        Saved-for-later rows live in the same table but are explicitly *not*
        part of the order — including them in a total is the classic
        "why is my bag ₹4,000 more than it looks" bug.
        """
        return self.filter(saved_for_later=False)

    def saved(self) -> "CartItemQuerySet":
        """Restrict to saved-for-later lines."""
        return self.filter(saved_for_later=True)

    def purchasable(self) -> "CartItemQuerySet":
        """Restrict to lines whose product and variant can still be bought."""
        return self.active().filter(
            product__is_active=True,
            variant__is_active=True,
            product__published_at__isnull=False,
            product__published_at__lte=timezone.now(),
        )

    def with_product(self) -> "CartItemQuerySet":
        """Load each line's product and variant."""
        from apps.products.models import Product

        return self.select_related("variant").prefetch_related(
            Prefetch("product", queryset=Product.objects.with_card_data())
        )


CartManager = models.Manager.from_queryset(CartQuerySet)
CartItemManager = models.Manager.from_queryset(CartItemQuerySet)
