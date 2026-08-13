"""Filtersets for the product endpoints.

Composes :class:`apps.core.filters.BaseFilterSet`, so products accept the same
``created_after`` / ``created_before`` parameters as every other list endpoint.

Everything is addressed by slug or by human-readable value — ``?brand=nordwyn``,
``?color=Navy`` — never by integer primary key. The frontend routes on slugs
and the filter chips display the values verbatim.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django_filters import rest_framework as filters

from apps.core.filters import BaseFilterSet, CharInFilter
from apps.products.models import (
    Fit,
    Material,
    Occasion,
    Pattern,
    Product,
    ProductVariant,
    Season,
    Size,
)


class ProductFilter(BaseFilterSet):
    """Every filter the listing sidebar offers."""

    # -- Taxonomy -----------------------------------------------------------

    category = CharInFilter(field_name="category__slug", lookup_expr="in")
    subcategory = CharInFilter(field_name="subcategory__slug", lookup_expr="in")
    brand = CharInFilter(field_name="brand__slug", lookup_expr="in")
    collection = filters.CharFilter(field_name="collection__slug", lookup_expr="iexact")
    tag = CharInFilter(field_name="tags__slug", lookup_expr="in", distinct=True)

    # -- Price --------------------------------------------------------------

    min_price = filters.NumberFilter(field_name="selling_price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="selling_price", lookup_expr="lte")

    # -- Variant attributes -------------------------------------------------
    # Colour and size live on the variant table, so both need distinct(): a
    # product with four sizes in Navy would otherwise appear four times in a
    # ?color=Navy result.

    color = CharInFilter(
        field_name="variants__color", lookup_expr="in", distinct=True
    )
    size = CharInFilter(field_name="variants__size", lookup_expr="in", distinct=True)

    # -- Product attributes -------------------------------------------------

    material = filters.MultipleChoiceFilter(choices=Material.choices)
    fit = filters.MultipleChoiceFilter(choices=Fit.choices)
    occasion = filters.MultipleChoiceFilter(choices=Occasion.choices)
    pattern = filters.MultipleChoiceFilter(choices=Pattern.choices)
    season = filters.MultipleChoiceFilter(choices=Season.choices)

    # -- Quality and value --------------------------------------------------

    min_rating = filters.NumberFilter(field_name="rating_average", lookup_expr="gte")
    min_discount = filters.NumberFilter(
        field_name="discount_percentage", lookup_expr="gte"
    )

    # -- Availability -------------------------------------------------------

    in_stock = filters.BooleanFilter(method="filter_in_stock")
    availability = filters.CharFilter(field_name="stock_status", lookup_expr="iexact")

    # -- Merchandising flags ------------------------------------------------

    is_on_sale = filters.BooleanFilter(method="filter_on_sale")

    # -- Free text ----------------------------------------------------------

    q = filters.CharFilter(method="filter_search", label="Search")

    class Meta:
        model = Product
        fields = [
            "gender",
            "is_featured",
            "is_trending",
            "is_new_arrival",
            "is_best_seller",
            "is_luxury",
            "is_recommended",
            "is_returnable",
        ]

    def filter_in_stock(
        self, queryset: QuerySet[Product], name: str, value: bool
    ) -> QuerySet[Product]:
        """Restrict to products with, or without, available stock."""
        if value is None:
            return queryset
        return queryset.filter(total_stock__gt=0) if value else queryset.filter(
            total_stock__lte=0
        )

    def filter_on_sale(
        self, queryset: QuerySet[Product], name: str, value: bool
    ) -> QuerySet[Product]:
        """Restrict to discounted, or undiscounted, products."""
        if value is None:
            return queryset
        return (
            queryset.filter(discount_percentage__gt=0)
            if value
            else queryset.filter(discount_percentage=0)
        )

    def filter_search(
        self, queryset: QuerySet[Product], name: str, value: str
    ) -> QuerySet[Product]:
        """Narrow the current result set by a free-text term.

        Distinct from the ``/search/`` endpoint: this composes with the other
        sidebar filters, so it is a plain narrowing rather than a ranked search.
        """
        term = (value or "").strip()
        if not term:
            return queryset

        return queryset.filter(
            Q(name__icontains=term)
            | Q(short_description__icontains=term)
            | Q(brand__name__icontains=term)
        ).distinct()


class ProductVariantFilter(BaseFilterSet):
    """Filters for the staff-facing variant endpoint."""

    product = filters.CharFilter(field_name="product__slug", lookup_expr="iexact")
    color = CharInFilter(field_name="color", lookup_expr="in")
    size = filters.MultipleChoiceFilter(choices=Size.choices)
    min_stock = filters.NumberFilter(field_name="stock", lookup_expr="gte")
    low_stock = filters.BooleanFilter(method="filter_low_stock")

    class Meta:
        model = ProductVariant
        fields = ["is_active"]

    def filter_low_stock(
        self, queryset: QuerySet, name: str, value: bool
    ) -> QuerySet:
        """Restrict to variants at or below the reorder threshold."""
        from apps.products.models import LOW_STOCK_THRESHOLD

        if not value:
            return queryset
        return queryset.low_stock(LOW_STOCK_THRESHOLD)
