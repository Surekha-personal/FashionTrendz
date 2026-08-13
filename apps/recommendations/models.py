"""Recommendation models.

Two tables only. :class:`RecentlyViewed` is the browsing trail, and
:class:`ProductAffinity` is the materialised "bought together" graph.

Everything else the module serves — related, similar, trending, popular — is
computed from data other modules already store. A table per rail would be four
more things to keep fresh and to explain when one goes stale.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.mixins import BaseModel
from apps.products.models import Product
from apps.recommendations.managers import (
    ProductAffinityManager,
    RecentlyViewedManager,
)

#: Longest trail kept per shopper. Beyond this the rail is scrolled past, and
#: the row is just storage that has to be cleaned up eventually.
MAX_RECENTLY_VIEWED: int = 30


class RecentlyViewed(BaseModel):
    """One product a shopper looked at, owned by an account or a session.

    Server-side rather than in ``localStorage`` so the trail follows the
    shopper from phone to laptop, and so "customers also viewed" has anything
    to read. The guest/user split mirrors :class:`apps.cart.models.Cart`
    exactly, which is what lets the two merge on the same login hook.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recently_viewed",
        null=True,
        blank=True,
        verbose_name=_("customer"),
    )
    session_key = models.CharField(
        _("session key"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("Identifies a guest's trail before they sign in."),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="recent_views",
        verbose_name=_("product"),
    )

    # Ordering key. Distinct from ``updated_at`` on purpose: re-viewing a
    # product moves it to the top of the rail, and that is a business fact the
    # rail sorts on, not an audit timestamp.
    viewed_at = models.DateTimeField(_("viewed at"), auto_now=True, db_index=True)
    view_count = models.PositiveIntegerField(
        _("times viewed"),
        default=1,
        help_text=_("How often this shopper returned to the product."),
    )

    objects = RecentlyViewedManager()

    class Meta:
        verbose_name = _("recently viewed product")
        verbose_name_plural = _("recently viewed products")
        ordering = ["-viewed_at"]
        constraints = [
            # Owned by exactly one of the two, never both and never neither —
            # the same invariant Cart enforces.
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, session_key="")
                    | models.Q(user__isnull=True, session_key__gt="")
                ),
                name="recentlyviewed_owned_by_user_xor_session",
            ),
            # One row per shopper per product. Re-viewing bumps the existing
            # row rather than appending, which is what keeps the trail a set of
            # thirty products and not thirty visits to the same one.
            models.UniqueConstraint(
                fields=["user", "product"],
                condition=models.Q(user__isnull=False),
                name="unique_recent_view_per_user",
            ),
            models.UniqueConstraint(
                fields=["session_key", "product"],
                condition=models.Q(user__isnull=True),
                name="unique_recent_view_per_session",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-viewed_at"], name="recentview_user_idx"),
            models.Index(
                fields=["session_key", "-viewed_at"], name="recentview_session_idx"
            ),
            # The cleanup job's read.
            models.Index(fields=["viewed_at"], name="recentview_cleanup_idx"),
        ]

    def __str__(self) -> str:
        owner = self.user.email if self.user_id else f"guest:{self.session_key[:8]}"
        return f"{owner} viewed {self.product_id}"

    @property
    def is_guest(self) -> bool:
        """Return whether this row belongs to an anonymous session."""
        return self.user_id is None


class ProductAffinity(BaseModel):
    """How often two products were bought in the same order.

    A materialised co-purchase edge. Computing "frequently bought together" on
    demand means self-joining every order line against every other line in the
    same order — fine on a seed database, a table scan on a real one. This is
    that join, run once by a management command and read by an index.

    Directed: A→B and B→A are separate rows, because a phone case sold with
    every phone is a strong recommendation on the phone's page and a weak one
    on the case's.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="affinities",
        verbose_name=_("product"),
    )
    related_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reverse_affinities",
        verbose_name=_("bought together with"),
    )

    co_purchase_count = models.PositiveIntegerField(
        _("orders containing both"), default=0, db_index=True
    )
    score = models.FloatField(
        _("confidence"),
        default=0.0,
        db_index=True,
        help_text=_(
            "Share of this product's orders that also contained the other one."
        ),
    )
    computed_at = models.DateTimeField(_("computed at"), auto_now=True)

    objects = ProductAffinityManager()

    class Meta:
        verbose_name = _("product affinity")
        verbose_name_plural = _("product affinities")
        ordering = ["-score", "-co_purchase_count"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "related_product"], name="unique_product_affinity"
            ),
            # A product is trivially bought with itself in every order it
            # appears in; that edge would top every ranking.
            models.CheckConstraint(
                condition=~models.Q(product=models.F("related_product")),
                name="affinity_not_self_referential",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "-score"], name="affinity_lookup_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} → {self.related_product_id} ({self.score:.2f})"
