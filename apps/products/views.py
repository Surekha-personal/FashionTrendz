"""Product API views.

Thin by construction: resolve permissions, choose a serializer, call
:mod:`apps.products.services`, return. No queryset is assembled here and no
business rule is expressed here.

Products are addressed by ``slug``; the storefront routes on slugs and those
are the URLs search engines index.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.responses import success_response
from apps.products import services
from apps.products.filters import ProductFilter
from apps.products.models import Product, ProductTag
from apps.products.pagination import (
    ProductGridPagination,
    ProductRailPagination,
    ProductSearchPagination,
)
from apps.products.permissions import ProductPermission
from apps.products.serializers import (
    HomepageProductsSerializer,
    ProductAdminSerializer,
    ProductCardSerializer,
    ProductDetailSerializer,
    ProductFacetsSerializer,
    ProductQuickViewSerializer,
    ProductTagSerializer,
    SearchSuggestionsSerializer,
)

SLUG_LIST_PARAM = OpenApiParameter(
    name="slugs",
    description="Comma-separated product slugs, most recent first.",
    required=True,
    type=str,
)


@extend_schema_view(
    list=extend_schema(summary="List products", tags=["Products"]),
    retrieve=extend_schema(summary="Retrieve a product", tags=["Products"]),
    create=extend_schema(summary="Create a product (staff)", tags=["Products"]),
    update=extend_schema(summary="Replace a product (staff)", tags=["Products"]),
    partial_update=extend_schema(summary="Update a product (staff)", tags=["Products"]),
    destroy=extend_schema(summary="Delete a product (staff)", tags=["Products"]),
)
class ProductViewSet(viewsets.ModelViewSet):
    """The product catalogue, its homepage rails, search and filters."""

    permission_classes = [ProductPermission]
    pagination_class = ProductGridPagination
    lookup_field = "slug"
    lookup_value_regex = "[-a-zA-Z0-9_]+"

    serializer_class = ProductCardSerializer
    filterset_class = ProductFilter
    search_fields = ["name", "short_description", "brand__name", "sku"]
    ordering_fields = [
        "selling_price",
        "discount_percentage",
        "rating_average",
        "purchase_count",
        "view_count",
        "created_at",
        "published_at",
    ]

    @property
    def include_hidden(self) -> bool:
        """Return whether the caller may see unpublished or inactive products."""
        user = getattr(self.request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)

    def get_serializer_class(self) -> Any:
        """Card for lists, detail for retrieve, admin for writes."""
        if self.action in {"create", "update", "partial_update"}:
            return ProductAdminSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        if self.action == "quick_view":
            return ProductQuickViewSerializer
        return ProductCardSerializer

    def get_queryset(self) -> QuerySet[Product]:
        """Return products visible to the caller, loaded for the current action."""
        base = (
            Product.objects.all() if self.include_hidden else services.visible_products()
        )

        if self.action in {"retrieve", "quick_view"}:
            return base.with_detail_data()
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return base
        return base.with_card_data()

    def filter_queryset(self, queryset: QuerySet[Product]) -> QuerySet[Product]:
        """Apply the standard backends, then the named ``?sort=`` option.

        ``?sort=`` is a curated alias over the eight orderings the storefront
        offers; ``?ordering=`` remains available for raw column sorts. Applying
        the alias last means it wins, which is what a shopper clicking "Price:
        low to high" expects.
        """
        queryset = super().filter_queryset(queryset)

        sort = self.request.query_params.get("sort")
        if sort:
            queryset = services.apply_sort(queryset, sort)
        elif not self.request.query_params.get("ordering"):
            queryset = services.apply_sort(queryset, None)

        return queryset

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return one product and record the view."""
        instance = self.get_object()
        services.record_product_view(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    # -- Shared helper ------------------------------------------------------

    def _rail(self, queryset: QuerySet[Product], message: str) -> Response:
        """Serialise a homepage rail through the rail paginator."""
        paginator = ProductRailPagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        serializer = ProductCardSerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            response = paginator.get_paginated_response(serializer.data)
            response.message = message
            return response
        return success_response(serializer.data, message=message)

    # -- Homepage rails -----------------------------------------------------

    @extend_schema(summary="Featured products", tags=["Products: Homepage"])
    @action(detail=False, methods=["get"])
    def featured(self, request: Request) -> Response:
        """Products promoted on the homepage."""
        return self._rail(services.get_featured_products(), "Featured products.")

    @extend_schema(summary="Trending products", tags=["Products: Homepage"])
    @action(detail=False, methods=["get"])
    def trending(self, request: Request) -> Response:
        """Products marked as trending."""
        return self._rail(services.get_trending_products(), "Trending products.")

    @extend_schema(summary="New arrivals", tags=["Products: Homepage"])
    @action(detail=False, methods=["get"], url_path="new-arrivals")
    def new_arrivals(self, request: Request) -> Response:
        """Newest published products."""
        return self._rail(services.get_new_arrivals(), "New arrivals.")

    @extend_schema(summary="Best sellers", tags=["Products: Homepage"])
    @action(detail=False, methods=["get"], url_path="best-sellers")
    def best_sellers(self, request: Request) -> Response:
        """Most purchased products."""
        return self._rail(services.get_best_sellers(), "Best sellers.")

    @extend_schema(summary="Luxury products", tags=["Products: Homepage"])
    @action(detail=False, methods=["get"])
    def luxury(self, request: Request) -> Response:
        """Products in the luxury edit."""
        return self._rail(services.get_luxury_products(), "Luxury products.")

    @extend_schema(
        summary="Flash sale",
        description="In-stock products discounted by 40% or more.",
        tags=["Products: Homepage"],
    )
    @action(detail=False, methods=["get"], url_path="flash-sale")
    def flash_sale(self, request: Request) -> Response:
        """Heavily discounted products that can actually be bought."""
        return self._rail(services.get_flash_sale_products(), "Flash sale.")

    @extend_schema(summary="Editor's picks", tags=["Products: Homepage"])
    @action(detail=False, methods=["get"], url_path="editors-picks")
    def editors_picks(self, request: Request) -> Response:
        """Products in an Editor's Picks collection."""
        return self._rail(services.get_editors_picks(), "Editor's picks.")

    @extend_schema(summary="Trending this week", tags=["Products: Homepage"])
    @action(detail=False, methods=["get"], url_path="trending-this-week")
    def trending_this_week(self, request: Request) -> Response:
        """Recently published products ranked by views."""
        return self._rail(services.get_trending_this_week(), "Trending this week.")

    @extend_schema(summary="Recommended products", tags=["Products: Homepage"])
    @action(detail=False, methods=["get"])
    def recommended(self, request: Request) -> Response:
        """Products flagged for the recommendation rail."""
        return self._rail(services.get_recommended_products(), "Recommended for you.")

    @extend_schema(summary="Recently added products", tags=["Products: Homepage"])
    @action(detail=False, methods=["get"], url_path="recently-added")
    def recently_added(self, request: Request) -> Response:
        """Most recently created products."""
        return self._rail(services.get_recently_added(), "Recently added.")

    @extend_schema(
        summary="Homepage payload",
        description="Every product rail the homepage renders, in one response.",
        responses={200: HomepageProductsSerializer},
        tags=["Products: Homepage"],
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def homepage(self, request: Request) -> Response:
        """Return all ten rails in a single round-trip."""
        serializer = HomepageProductsSerializer(
            services.get_homepage_payload(), context=self.get_serializer_context()
        )
        return success_response(serializer.data, message="Homepage products retrieved.")

    # -- Detail-page rails --------------------------------------------------

    @extend_schema(summary="Related products", tags=["Products: Detail"])
    @action(detail=True, methods=["get"])
    def related(self, request: Request, slug: str | None = None) -> Response:
        """Products from the same subcategory."""
        return self._rail(
            services.get_related_products(self.get_object()), "Related products."
        )

    @extend_schema(summary="Similar products", tags=["Products: Detail"])
    @action(detail=True, methods=["get"])
    def similar(self, request: Request, slug: str | None = None) -> Response:
        """Products resembling this one on brand, material, occasion or price."""
        return self._rail(
            services.get_similar_products(self.get_object()), "Similar products."
        )

    @extend_schema(
        summary="Quick view",
        responses={200: ProductQuickViewSerializer},
        tags=["Products: Detail"],
    )
    @action(detail=True, methods=["get"], url_path="quick-view")
    def quick_view(self, request: Request, slug: str | None = None) -> Response:
        """Return the compact payload the quick-view modal renders."""
        serializer = self.get_serializer(self.get_object())
        return success_response(serializer.data, message="Quick view retrieved.")

    @extend_schema(
        summary="Variant availability",
        description="Colour to size availability matrix for the product page.",
        tags=["Products: Detail"],
    )
    @action(detail=True, methods=["get"])
    def availability(self, request: Request, slug: str | None = None) -> Response:
        """Return live colour/size availability."""
        return success_response(
            services.get_variant_availability(self.get_object()),
            message="Availability retrieved.",
        )

    @extend_schema(
        summary="Recently viewed products",
        description=(
            "Resolves client-supplied slugs to products, preserving the given "
            "order. The list lives in the browser, so this works signed out."
        ),
        parameters=[SLUG_LIST_PARAM],
        tags=["Products: Detail"],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="recently-viewed",
        pagination_class=None,
    )
    def recently_viewed(self, request: Request) -> Response:
        """Return products for the supplied slugs, in the supplied order."""
        raw = request.query_params.get("slugs", "")
        slugs = [part.strip() for part in raw.split(",") if part.strip()]
        products = services.get_recently_viewed(slugs)
        serializer = ProductCardSerializer(
            products, many=True, context=self.get_serializer_context()
        )
        return success_response(serializer.data, message="Recently viewed products.")

    # -- Search -------------------------------------------------------------

    @extend_schema(
        summary="Search products",
        parameters=[
            OpenApiParameter(name="q", description="Search term.", required=True, type=str)
        ],
        tags=["Products: Search"],
    )
    @action(
        detail=False,
        methods=["get"],
        pagination_class=ProductSearchPagination,
    )
    def search(self, request: Request) -> Response:
        """Return ranked search results."""
        query = request.query_params.get("q", "")
        results = services.search_products(query)

        paginator = ProductSearchPagination()
        page = paginator.paginate_queryset(results, request, view=self)
        serializer = ProductCardSerializer(
            page if page is not None else results,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            response = paginator.get_paginated_response(serializer.data)
            response.message = f"Search results for '{query}'."
            return response
        return success_response(serializer.data, message="Search results.")

    @extend_schema(
        summary="Search suggestions",
        description="Autocomplete rows grouped into products, brands and categories.",
        parameters=[
            OpenApiParameter(name="q", description="Partial term.", required=True, type=str)
        ],
        responses={200: SearchSuggestionsSerializer},
        tags=["Products: Search"],
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def suggestions(self, request: Request) -> Response:
        """Return autocomplete suggestions."""
        return success_response(
            services.get_search_suggestions(request.query_params.get("q", "")),
            message="Search suggestions.",
        )

    @extend_schema(
        summary="Popular products and trending searches",
        description="What an empty search box shows before the shopper types.",
        tags=["Products: Search"],
    )
    @action(detail=False, methods=["get"], url_path="search-defaults", pagination_class=None)
    def search_defaults(self, request: Request) -> Response:
        """Return popular products and suggested search terms."""
        popular = ProductCardSerializer(
            services.get_popular_products(),
            many=True,
            context=self.get_serializer_context(),
        )
        return success_response(
            {
                "popular_products": popular.data,
                "trending_searches": services.get_trending_searches(),
            },
            message="Search defaults.",
        )

    # -- Facets -------------------------------------------------------------

    @extend_schema(
        summary="Available filters",
        description=(
            "Filter options for the current result set. Accepts the same query "
            "parameters as the list endpoint, so the sidebar never offers a "
            "filter that would return nothing."
        ),
        responses={200: ProductFacetsSerializer},
        tags=["Products: Filters"],
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def filters(self, request: Request) -> Response:
        """Return the facets for the currently filtered result set."""
        queryset = self.filter_queryset(self.get_queryset())
        return success_response(
            services.get_filter_facets(queryset), message="Filter options."
        )

    # -- Inventory ----------------------------------------------------------

    @extend_schema(
        summary="Low-stock variants (staff)",
        tags=["Products: Inventory"],
    )
    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request: Request) -> Response:
        """Return variants at or below the reorder threshold."""
        if not self.include_hidden:
            return Response(
                {"success": False, "message": "Staff access required.", "errors": {}},
                status=status.HTTP_403_FORBIDDEN,
            )

        from apps.products.serializers import ProductVariantAdminSerializer

        variants = services.get_low_stock_variants()
        page = self.paginate_queryset(variants)
        serializer = ProductVariantAdminSerializer(
            page if page is not None else variants,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(summary="List product tags", tags=["Products: Tags"]),
    retrieve=extend_schema(summary="Retrieve a product tag", tags=["Products: Tags"]),
)
class ProductTagViewSet(viewsets.ReadOnlyModelViewSet):
    """Merchandising tags, for filter chips and campaign pages."""

    serializer_class = ProductTagSerializer
    permission_classes = [ProductPermission]
    lookup_field = "slug"
    lookup_value_regex = "[-a-zA-Z0-9_]+"
    search_fields = ["name", "slug"]
    ordering_fields = ["name"]
    ordering = ["name"]

    def get_queryset(self) -> QuerySet[ProductTag]:
        """Return active tags."""
        return services.get_tags()

    @extend_schema(summary="Products carrying this tag", tags=["Products: Tags"])
    @action(detail=True, methods=["get"])
    def products(self, request: Request, slug: str | None = None) -> Response:
        """Return the products carrying one tag."""
        self.get_object()
        queryset = services.visible_products().for_tag(slug).with_card_data()

        paginator = ProductGridPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = ProductCardSerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return paginator.get_paginated_response(serializer.data)
        return Response(serializer.data)
