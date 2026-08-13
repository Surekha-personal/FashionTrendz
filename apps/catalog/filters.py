"""Filtersets for the catalog endpoints.

Each one composes :class:`apps.core.filters.BaseFilterSet`, so every catalog
endpoint accepts the same ``created_after`` / ``created_before`` parameters as
the rest of the API without restating them.

``is_active`` is a filter only for staff. The public viewsets restrict their
queryset to active rows before the filter backend runs, so a customer passing
``?is_active=false`` gets an empty list rather than a preview of unreleased
categories.
"""

from __future__ import annotations

from django_filters import rest_framework as filters

from apps.catalog.models import Brand, Category, Collection, CollectionType, SubCategory
from apps.core.filters import BaseFilterSet, CharInFilter


class CategoryFilter(BaseFilterSet):
    """Filters for ``/categories/``."""

    name = filters.CharFilter(lookup_expr="icontains")
    slug = filters.CharFilter(lookup_expr="iexact")
    slug__in = CharInFilter(field_name="slug", lookup_expr="in")

    class Meta:
        model = Category
        fields = ["is_active", "is_featured", "is_trending", "is_luxury"]


class SubCategoryFilter(BaseFilterSet):
    """Filters for ``/subcategories/``."""

    name = filters.CharFilter(lookup_expr="icontains")
    slug = filters.CharFilter(lookup_expr="iexact")
    # Addressed by the parent's slug rather than its integer id: the frontend
    # routes on slugs and has no reason to know internal primary keys.
    category = filters.CharFilter(field_name="category__slug", lookup_expr="iexact")
    category__in = CharInFilter(field_name="category__slug", lookup_expr="in")

    class Meta:
        model = SubCategory
        fields = ["is_active"]


class BrandFilter(BaseFilterSet):
    """Filters for ``/brands/``."""

    name = filters.CharFilter(lookup_expr="icontains")
    slug = filters.CharFilter(lookup_expr="iexact")
    country = filters.CharFilter(lookup_expr="iexact")
    category = filters.CharFilter(field_name="categories__slug", lookup_expr="iexact")

    founded_after = filters.NumberFilter(field_name="founded_year", lookup_expr="gte")
    founded_before = filters.NumberFilter(field_name="founded_year", lookup_expr="lte")

    #: Single-letter brand index, as used by the "Shop by brand" A-Z page.
    starts_with = filters.CharFilter(field_name="name", lookup_expr="istartswith")

    class Meta:
        model = Brand
        fields = ["is_active", "is_featured", "is_luxury"]


class CollectionFilter(BaseFilterSet):
    """Filters for ``/collections/``."""

    title = filters.CharFilter(lookup_expr="icontains")
    slug = filters.CharFilter(lookup_expr="iexact")
    category = filters.CharFilter(field_name="categories__slug", lookup_expr="iexact")
    type = filters.ChoiceFilter(choices=CollectionType.choices)
    type__in = CharInFilter(field_name="type", lookup_expr="in")

    class Meta:
        model = Collection
        fields = ["is_active", "is_featured"]
