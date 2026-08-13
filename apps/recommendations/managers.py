"""Querysets and managers for the recommendations module."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import models
from django.utils import timezone


class RecentlyViewedQuerySet(models.QuerySet):
    """Queries over browsing trails."""

    def owned_by(self, *, user: Any = None, session_key: str = "") -> "RecentlyViewedQuerySet":
        """Restrict to one shopper's trail, account or guest.

        A signed-in user always wins over a session key. After a merge both
        identifiers exist on the same request, and reading the session trail
        would show the shopper a stale list they already had migrated.
        """
        if user is not None and getattr(user, "is_authenticated", False):
            return self.filter(user=user)
        if session_key:
            return self.filter(user__isnull=True, session_key=session_key)
        return self.none()

    def newest(self) -> "RecentlyViewedQuerySet":
        """Most recently viewed first — the order the rail renders in."""
        return self.order_by("-viewed_at")

    def for_product(self, product: Any) -> "RecentlyViewedQuerySet":
        """Restrict to views of one product."""
        return self.filter(product=product)

    def guests(self) -> "RecentlyViewedQuerySet":
        """Restrict to anonymous trails — what the cleanup job prunes first."""
        return self.filter(user__isnull=True)

    def stale(self, days: int = 90) -> "RecentlyViewedQuerySet":
        """Rows older than ``days``.

        The trail is a convenience, not a record. Keeping a shopper's browsing
        history indefinitely is a data-retention liability with no product
        benefit — nobody scrolls to what they looked at last spring.
        """
        return self.filter(viewed_at__lt=timezone.now() - timedelta(days=days))

    def product_ids(self) -> list[int]:
        """Return the trail as product ids, newest first.

        The rail renders product *cards*, and ``ProductQuerySet.with_card_data``
        already knows how to load one without N+1. Rather than reimplement that
        prefetch against this table, the trail hands over ids and the products
        module builds the cards.
        """
        return list(self.newest().values_list("product_id", flat=True))


class ProductAffinityQuerySet(models.QuerySet):
    """Queries over the co-purchase graph."""

    def for_product(self, product: Any) -> "ProductAffinityQuerySet":
        """Edges leading away from one product."""
        return self.filter(product=product)

    def strong(self, minimum: int = 2) -> "ProductAffinityQuerySet":
        """Edges seen in at least ``minimum`` orders.

        A single shared order is coincidence, and surfacing it as "frequently
        bought together" is how a store recommends a raincoat with a wedding
        lehenga because one customer bought both in March.
        """
        return self.filter(co_purchase_count__gte=minimum)

    def ranked(self) -> "ProductAffinityQuerySet":
        """Best edges first: confidence, then raw volume as the tiebreak."""
        return self.order_by("-score", "-co_purchase_count")

    def visible(self) -> "ProductAffinityQuerySet":
        """Drop edges pointing at products a shopper cannot buy.

        The graph is computed from historical orders, which include products
        since unpublished or discontinued. Recommending those is a dead link.

        Reuses ``Product.objects.visible()`` rather than restating its rules —
        visibility also depends on the category tree, and a second definition
        here would drift the first time a rule changes.
        """
        from apps.products.models import Product

        return self.filter(related_product__in=Product.objects.visible())


RecentlyViewedManager = models.Manager.from_queryset(RecentlyViewedQuerySet)
ProductAffinityManager = models.Manager.from_queryset(ProductAffinityQuerySet)
