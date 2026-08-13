"""Querysets and managers for the catalog models.

Every recurring filter and every prefetch the API needs lives here rather than
in a view. Two reasons: a filter written once cannot drift between the list
endpoint, the mega menu and the admin; and the ``with_*`` methods keep N+1
prevention next to the query instead of relying on each view to remember it.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Count, Prefetch, Q


class ActiveQuerySetMixin:
    """Shared ``active`` / ``inactive`` helpers for models with ``is_active``.

    Annotated as returning a plain ``QuerySet`` rather than ``typing.Self``:
    ``Self`` needs Python 3.11+, and the precision buys nothing here.
    """

    def active(self) -> models.QuerySet:
        """Restrict to rows visible on the storefront."""
        return self.filter(is_active=True)

    def inactive(self) -> models.QuerySet:
        """Restrict to rows hidden from the storefront."""
        return self.filter(is_active=False)


class CategoryQuerySet(ActiveQuerySetMixin, models.QuerySet):
    """Queries over top-level categories."""

    def featured(self) -> "CategoryQuerySet":
        """Categories promoted into the homepage's featured strip."""
        return self.filter(is_featured=True)

    def trending(self) -> "CategoryQuerySet":
        """Categories editorially marked as trending right now."""
        return self.filter(is_trending=True)

    def luxury(self) -> "CategoryQuerySet":
        """Categories belonging to the luxury edit."""
        return self.filter(is_luxury=True)

    def with_subcategories(self) -> "CategoryQuerySet":
        """Prefetch active subcategories in display order.

        A plain ``prefetch_related("subcategories")`` would pull inactive rows
        and then filter them in Python, which both over-fetches and silently
        breaks any count taken from the prefetched list. The explicit
        ``Prefetch`` pushes both the filter and the ordering into SQL.
        """
        from apps.catalog.models import SubCategory

        return self.prefetch_related(
            Prefetch(
                "subcategories",
                queryset=SubCategory.objects.active().order_by("display_order", "name"),
                to_attr="active_subcategories",
            )
        )

    def with_menu_relations(self) -> "CategoryQuerySet":
        """Prefetch everything the mega menu renders, in three extra queries.

        Without this the menu costs one query per category for subcategories,
        one per category for collections and one per category for brands — on a
        nine-category menu that is 28 queries on every page load.
        """
        from apps.catalog.models import Brand, Collection, SubCategory

        return self.prefetch_related(
            Prefetch(
                "subcategories",
                queryset=SubCategory.objects.active().order_by("display_order", "name"),
                to_attr="active_subcategories",
            ),
            Prefetch(
                "collections",
                queryset=Collection.objects.active()
                .featured()
                .order_by("display_order", "title"),
                to_attr="menu_collections",
            ),
            Prefetch(
                "brands",
                queryset=Brand.objects.active().order_by("-popularity_score", "name"),
                to_attr="menu_brands",
            ),
        )

    def with_counts(self) -> "CategoryQuerySet":
        """Annotate ``subcategory_count`` using only active children."""
        return self.annotate(
            subcategory_count=Count(
                "subcategories",
                filter=Q(subcategories__is_active=True),
                distinct=True,
            )
        )

    def ordered(self) -> "CategoryQuerySet":
        """Apply the canonical merchandising order."""
        return self.order_by("display_order", "name")


class SubCategoryQuerySet(ActiveQuerySetMixin, models.QuerySet):
    """Queries over second-level categories."""

    def for_category(self, category_slug: str) -> "SubCategoryQuerySet":
        """Restrict to the children of one category, addressed by slug."""
        return self.filter(category__slug=category_slug)

    def visible(self) -> "SubCategoryQuerySet":
        """Active subcategories whose parent category is also active.

        An active subcategory under a deactivated category must not appear on
        the storefront — hiding a category has to hide everything beneath it,
        or "Women" disappears from the menu while "Women's Dresses" keeps
        showing up in listings.
        """
        return self.filter(is_active=True, category__is_active=True)

    def with_category(self) -> "SubCategoryQuerySet":
        """Join the parent row so serialising it costs no extra query."""
        return self.select_related("category")

    def ordered(self) -> "SubCategoryQuerySet":
        """Apply the canonical merchandising order."""
        return self.order_by("category__display_order", "display_order", "name")


class BrandQuerySet(ActiveQuerySetMixin, models.QuerySet):
    """Queries over brands."""

    def featured(self) -> "BrandQuerySet":
        """Brands promoted on the homepage."""
        return self.filter(is_featured=True)

    def luxury(self) -> "BrandQuerySet":
        """Brands in the luxury edit."""
        return self.filter(is_luxury=True)

    def popular(self) -> "BrandQuerySet":
        """Brands ordered by popularity score, highest first."""
        return self.order_by("-popularity_score", "display_order", "name")

    def for_category(self, category_slug: str) -> "BrandQuerySet":
        """Restrict to brands merchandised under one category."""
        return self.filter(categories__slug=category_slug).distinct()

    def ordered(self) -> "BrandQuerySet":
        """Apply the canonical merchandising order."""
        return self.order_by("display_order", "name")


class CollectionQuerySet(ActiveQuerySetMixin, models.QuerySet):
    """Queries over editorial collections."""

    def featured(self) -> "CollectionQuerySet":
        """Collections promoted on the homepage."""
        return self.filter(is_featured=True)

    def of_type(self, collection_type: str) -> "CollectionQuerySet":
        """Restrict to one collection type."""
        return self.filter(type=collection_type)

    def seasonal(self) -> "CollectionQuerySet":
        """Restrict to the season- and festival-driven collections."""
        from apps.catalog.models import SEASONAL_COLLECTION_TYPES

        return self.filter(type__in=SEASONAL_COLLECTION_TYPES)

    def for_category(self, category_slug: str) -> "CollectionQuerySet":
        """Restrict to collections merchandised under one category."""
        return self.filter(categories__slug=category_slug).distinct()

    def ordered(self) -> "CollectionQuerySet":
        """Apply the canonical merchandising order."""
        return self.order_by("display_order", "title")


CategoryManager = models.Manager.from_queryset(CategoryQuerySet)
SubCategoryManager = models.Manager.from_queryset(SubCategoryQuerySet)
BrandManager = models.Manager.from_queryset(BrandQuerySet)
CollectionManager = models.Manager.from_queryset(CollectionQuerySet)
