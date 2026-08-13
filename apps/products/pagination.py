"""Pagination tuned for product surfaces.

All three extend :class:`apps.core.pagination.BasePagination`, so they emit the
same enveloped ``{"pagination": ..., "results": ...}`` shape as every other
list endpoint. Only the page sizes differ.
"""

from __future__ import annotations

from apps.core.pagination import BasePagination


class ProductGridPagination(BasePagination):
    """Default for product listings: 24 per page, up to 96.

    24 rather than the project-wide 20 because product grids render 2, 3, 4 or
    6 columns depending on viewport, and 24 divides evenly by all of them. A
    page of 20 leaves a ragged final row on every layout except 2- and 4-column.

    The 96 ceiling is four full pages — enough for an "infinite scroll" client
    to batch aggressively, low enough that no anonymous caller can pull the
    catalogue in one request.
    """

    page_size = 24
    max_page_size = 96


class ProductSearchPagination(BasePagination):
    """Search results: 20 per page, up to 60.

    Smaller than the grid because relevance decays fast — a shopper who has not
    found it in the first twenty results refines the query rather than paging.
    """

    page_size = 20
    max_page_size = 60


class ProductRailPagination(BasePagination):
    """Homepage rails and related-product strips: 12 per page, up to 48.

    A rail is a horizontal carousel, not a grid; twelve is more than any
    viewport shows before the customer scrolls it.
    """

    page_size = 12
    max_page_size = 48
