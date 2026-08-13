"""Reusable filtering building blocks.

Two kinds of thing live here:

* ``FilterSet`` mixins that a concrete filterset composes and points at its own
  field names, so date-range and price-range query parameters look identical on
  every endpoint;
* small ``BaseInFilter`` subclasses, because django-filter ships the halves
  (``BaseInFilter`` and the typed filters) but not the combinations everyone ends
  up writing.

None of these declare ``Meta``. A ``FilterSet`` without ``Meta`` binds to no
model and is treated as a pure mixin, which is what lets the same range filter
serve products, orders and coupons.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django_filters import rest_framework as filters
from rest_framework.filters import OrderingFilter
from rest_framework.request import Request
from rest_framework.views import APIView

# ---------------------------------------------------------------------------
# Typed "in" filters
# ---------------------------------------------------------------------------


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    """Comma-separated numbers: ``?category_id__in=3,7,12``."""


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Comma-separated strings: ``?status__in=pending,confirmed``."""


class UUIDInFilter(filters.BaseInFilter, filters.UUIDFilter):
    """Comma-separated UUIDs, for bulk lookups by public id."""


# ---------------------------------------------------------------------------
# FilterSet mixins
# ---------------------------------------------------------------------------


class TimestampFilterMixin(filters.FilterSet):
    """Adds ``created_after``, ``created_before`` and ``created_on``.

    Requires a ``created_at`` field on the model, which
    :class:`apps.core.mixins.TimestampMixin` provides.

    ``created_before`` uses ``lte`` on the date part rather than the datetime,
    so ``?created_before=2026-08-04`` includes everything from that day. Naive
    ``lte`` against a datetime would silently exclude every row after midnight
    — the classic off-by-one-day report bug.
    """

    created_after = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_before = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    created_on = filters.DateFilter(field_name="created_at", lookup_expr="date")
    updated_after = filters.DateFilter(field_name="updated_at", lookup_expr="date__gte")


class PriceRangeFilterMixin(filters.FilterSet):
    """Adds ``min_price`` and ``max_price``.

    Defaults to a ``price`` field. Point it elsewhere by redeclaring on the
    concrete filterset::

        class ProductFilter(PriceRangeFilterMixin):
            min_price = filters.NumberFilter(
                field_name="sale_price", lookup_expr="gte"
            )
    """

    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")


class SoftDeleteFilterMixin(filters.FilterSet):
    """Adds an opt-in ``include_deleted`` flag for staff-facing endpoints.

    The default manager on :class:`apps.core.mixins.SoftDeleteMixin` already
    hides deleted rows, so this filter only matters on a view whose queryset
    was built from ``all_objects``. Guard it with an admin permission — a
    customer must not be able to page through deleted records.
    """

    include_deleted = filters.BooleanFilter(
        method="filter_include_deleted",
        label="Include soft-deleted records",
    )

    def filter_include_deleted(
        self,
        queryset: QuerySet,
        name: str,
        value: bool,
    ) -> QuerySet:
        """Keep deleted rows when ``value`` is true, otherwise exclude them."""
        return queryset if value else queryset.filter(is_deleted=False)


class PublishStatusFilterMixin(filters.FilterSet):
    """Adds ``status`` and a convenience ``published`` boolean."""

    published = filters.BooleanFilter(
        method="filter_published",
        label="Only published records",
    )

    def filter_published(
        self,
        queryset: QuerySet,
        name: str,
        value: bool,
    ) -> QuerySet:
        """Restrict to published rows when ``value`` is true."""
        from apps.core.choices import PublishStatus

        if value is None:
            return queryset
        if value:
            return queryset.filter(status=PublishStatus.PUBLISHED)
        return queryset.exclude(status=PublishStatus.PUBLISHED)


class BaseFilterSet(TimestampFilterMixin):
    """Recommended base for concrete filtersets.

    Gives every endpoint the same date-range parameters. Subclasses add their
    own fields and a ``Meta``::

        class ProductFilter(BaseFilterSet, PriceRangeFilterMixin):
            class Meta:
                model = Product
                fields = ["category", "brand", "gender"]
    """


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


class NullsLastOrderingFilter(OrderingFilter):
    """Ordering filter that always sorts NULLs to the end.

    PostgreSQL treats NULL as larger than any value, so ``ORDER BY discount
    DESC`` puts every undiscounted product *first* — the exact opposite of what
    "sort by biggest discount" should show. ``nulls_last`` fixes it for
    descending order, and ``nulls_first`` is wrong for ascending for the mirror
    reason, so both directions are handled explicitly.
    """

    def filter_queryset(
        self,
        request: Request,
        queryset: QuerySet,
        view: APIView,
    ) -> QuerySet:
        """Apply the requested ordering with NULLs pushed to the end."""
        ordering = self.get_ordering(request, queryset, view)
        if not ordering:
            return queryset

        expressions: list[Any] = []
        for term in ordering:
            descending = term.startswith("-")
            field_name = term.lstrip("-")
            field = queryset.model._meta.get_field(field_name.split("__")[0])
            column = getattr(queryset.model, "_meta", None) and field_name

            if getattr(field, "null", False):
                from django.db.models import F

                expression = F(column).desc(nulls_last=True) if descending else F(
                    column
                ).asc(nulls_last=True)
                expressions.append(expression)
            else:
                expressions.append(term)

        return queryset.order_by(*expressions)
