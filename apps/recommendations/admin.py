"""Django admin for recommendations."""

from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.recommendations import services
from apps.recommendations.models import ProductAffinity, RecentlyViewed


@admin.register(RecentlyViewed)
class RecentlyViewedAdmin(admin.ModelAdmin):
    """Browsing trails, for support and for the retention job.

    Read-only apart from deletion. Nothing good comes of an admin editing a
    shopper's browsing history, and a support agent honouring an erasure
    request needs exactly the delete action and nothing else.
    """

    list_display = ("id", "owner", "product", "view_count", "viewed_at")
    list_filter = ("viewed_at",)
    search_fields = ("user__email", "session_key", "product__name", "product__slug")
    raw_id_fields = ("user", "product")
    readonly_fields = (
        "uuid",
        "user",
        "session_key",
        "product",
        "view_count",
        "viewed_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "viewed_at"
    ordering = ("-viewed_at",)
    list_per_page = 50
    actions = ("purge_stale",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Trails are written by the storefront, never typed in by hand."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[RecentlyViewed]:
        """Join the columns the changelist renders."""
        return super().get_queryset(request).select_related("user", "product")

    @admin.display(description=_("shopper"), ordering="user__email")
    def owner(self, obj: RecentlyViewed) -> str:
        """Render the owner, whichever kind it is."""
        return obj.user.email if obj.user_id else f"guest:{obj.session_key[:12]}"

    @admin.action(description=_("Purge trails older than 90 days"))
    def purge_stale(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Run the retention job from the admin.

        Ignores the selection deliberately: retention is a policy applied to
        the whole table, and applying it to fifty hand-picked rows would give a
        misleading sense that the job had run.
        """
        removed = services.purge_stale_trails()
        self.message_user(
            request, f"{removed} stale trail row(s) removed.", messages.SUCCESS
        )


@admin.register(ProductAffinity)
class ProductAffinityAdmin(admin.ModelAdmin):
    """The co-purchase graph, for inspecting why a bundle is suggested."""

    list_display = (
        "product",
        "related_product",
        "co_purchase_count",
        "confidence",
        "computed_at",
    )
    list_filter = ("computed_at",)
    search_fields = (
        "product__name",
        "product__slug",
        "related_product__name",
        "related_product__slug",
    )
    raw_id_fields = ("product", "related_product")
    readonly_fields = (
        "uuid",
        "product",
        "related_product",
        "co_purchase_count",
        "score",
        "computed_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-score", "-co_purchase_count")
    list_per_page = 50
    actions = ("rebuild_graph",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Edges are derived from orders; a hand-typed one would be a lie."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[ProductAffinity]:
        """Join both ends of the edge."""
        return super().get_queryset(request).select_related("product", "related_product")

    @admin.display(description=_("confidence"), ordering="score")
    def confidence(self, obj: ProductAffinity) -> str:
        """Render the score as a percentage — the unit it actually means."""
        return f"{obj.score * 100:.1f}%"

    @admin.action(description=_("Rebuild the co-purchase graph"))
    def rebuild_graph(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Recompute every edge from order history.

        Whole-graph, ignoring the selection: an edge's confidence is a share of
        a product's total orders, so it cannot be recomputed for a subset
        without reading everything anyway.
        """
        result = services.rebuild_affinities()
        self.message_user(
            request,
            f"{result['edges']} edge(s) built from {result['baskets']} order(s).",
            messages.SUCCESS,
        )
