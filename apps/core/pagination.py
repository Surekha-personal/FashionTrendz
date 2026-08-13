"""Pagination classes.

All three emit ``{"pagination": {...}, "results": [...]}``, which
:class:`apps.core.responses.EnvelopeJSONRenderer` reshapes into::

    {
      "success": true,
      "message": "Request successful.",
      "data": [ ... ],
      "pagination": {
        "count": 137, "page": 2, "page_size": 20, "total_pages": 7,
        "next": "https://.../?page=3", "previous": "https://.../?page=1"
      }
    }

``data`` is therefore always the payload and never a wrapper around it, which
is what makes the envelope uniform across list and detail endpoints.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.constants import (
    ADMIN_MAX_PAGE_SIZE,
    ADMIN_PAGE_SIZE,
    LARGE_MAX_PAGE_SIZE,
    LARGE_PAGE_SIZE,
    PAGE_QUERY_PARAM,
    PAGE_SIZE_QUERY_PARAM,
    STANDARD_MAX_PAGE_SIZE,
    STANDARD_PAGE_SIZE,
)


class BasePagination(PageNumberPagination):
    """Page-number pagination with a client-controllable page size.

    ``max_page_size`` is the important attribute. Honouring ``?page_size=``
    without a ceiling hands any anonymous caller a way to request the entire
    table in one query — a denial-of-service that needs no special tooling.
    DRF silently clamps anything above the ceiling rather than erroring, so a
    client asking for too much still gets a usable response.
    """

    page_query_param = PAGE_QUERY_PARAM
    page_size_query_param = PAGE_SIZE_QUERY_PARAM

    def get_paginated_response(self, data: list[Any]) -> Response:
        """Return results alongside pagination metadata."""
        return Response(
            OrderedDict(
                [
                    ("pagination", self.get_pagination_metadata()),
                    ("results", data),
                ]
            )
        )

    def get_pagination_metadata(self) -> dict[str, Any]:
        """Return the metadata block describing the current page.

        Includes ``page``, ``page_size`` and ``total_pages`` on top of DRF's
        defaults. Without ``total_pages`` a frontend cannot render a pager
        without first walking every ``next`` link.
        """
        return {
            "count": self.page.paginator.count,
            "page": self.page.number,
            "page_size": self.get_page_size(self.request) or len(self.page),
            "total_pages": self.page.paginator.num_pages,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
        }

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Describe the enveloped list shape for the OpenAPI document.

        Without this override drf-spectacular documents DRF's default
        ``{count, next, previous, results}``, which is not what this API sends,
        and every generated client would be wrong.
        """
        return {
            "type": "object",
            "required": ["success", "message", "data", "pagination"],
            "properties": {
                "success": {"type": "boolean", "example": True},
                "message": {"type": "string", "example": "Request successful."},
                "data": schema,
                "pagination": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer", "example": 137},
                        "page": {"type": "integer", "example": 2},
                        "page_size": {"type": "integer", "example": 20},
                        "total_pages": {"type": "integer", "example": 7},
                        "next": {
                            "type": "string",
                            "nullable": True,
                            "format": "uri",
                        },
                        "previous": {
                            "type": "string",
                            "nullable": True,
                            "format": "uri",
                        },
                    },
                },
            },
        }


class StandardPagination(BasePagination):
    """Default for customer-facing endpoints: 20 per page, up to 100.

    Installed as ``DEFAULT_PAGINATION_CLASS``, so every list endpoint gets it
    without opting in.

    ``page_size`` is deliberately left unset so DRF falls back to
    ``REST_FRAMEWORK["PAGE_SIZE"]``, which Module 1 sources from the
    ``API_PAGE_SIZE`` environment variable. The default page size is therefore
    tunable per environment without a code change; the other two classes pin
    their sizes because their whole purpose is to differ from the default.
    """

    page_size = None
    max_page_size = STANDARD_MAX_PAGE_SIZE

    def get_page_size(self, request: Any) -> int:
        """Return the effective page size, falling back to the project default."""
        return super().get_page_size(request) or STANDARD_PAGE_SIZE


class LargePagination(BasePagination):
    """For lightweight rows fetched in bulk: 100 per page, up to 500.

    Suited to compact payloads a client needs many of at once — category trees,
    size charts, pincode serviceability. Not for product listings, whose rows
    carry images and nested variants.
    """

    page_size = LARGE_PAGE_SIZE
    max_page_size = LARGE_MAX_PAGE_SIZE


class AdminPagination(BasePagination):
    """For staff dashboards: 50 per page, up to 200.

    Higher than the storefront default because admin tables are scanned, and
    lower than ``LargePagination`` because admin rows are wide.
    """

    page_size = ADMIN_PAGE_SIZE
    max_page_size = ADMIN_MAX_PAGE_SIZE
