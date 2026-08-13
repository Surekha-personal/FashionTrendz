"""Catalog API views.

Views stay thin by design: resolve permissions, pick a serializer, call
:mod:`apps.catalog.services`, return. No querysets are assembled here and no
business rule is expressed here — both live in the service and manager layers,
where they are shared and directly testable.

Objects are addressed by ``slug`` rather than by id. The storefront routes on
slugs, and a slug URL is the one the search engine indexes.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.catalog import services
from apps.catalog.filters import (
    BrandFilter,
    CategoryFilter,
    CollectionFilter,
    SubCategoryFilter,
)
from apps.catalog.models import Brand, Category, Collection, SubCategory
from apps.catalog.permissions import CatalogPermission
from apps.catalog.serializers import (
    BrandAdminSerializer,
    BrandLiteSerializer,
    BrandSerializer,
    CategoryAdminSerializer,
    CategoryDetailSerializer,
    CategoryLiteSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
    CollectionAdminSerializer,
    CollectionLiteSerializer,
    CollectionSerializer,
    HomepageSerializer,
    MegaMenuSerializer,
    SubCategoryAdminSerializer,
    SubCategorySerializer,
)
from apps.core.mixins import SerializerActionMixin
from apps.core.pagination import LargePagination
from apps.core.responses import success_response


class CatalogViewSetMixin(SerializerActionMixin):
    """Shared wiring for the four catalog viewsets.

    Centralises three things every catalog endpoint needs identically: staff
    see inactive rows and customers do not, writes use the admin serializer,
    and lookups happen by slug.
    """

    permission_classes = [CatalogPermission]
    lookup_field = "slug"
    #: Slugs contain hyphens and digits; the default regex excludes dots, which
    #: is what we want, but be explicit so a slug is never read as a format
    #: suffix by the URL resolver.
    lookup_value_regex = "[-a-zA-Z0-9_]+"

    #: Serializer used for create/update, and for reads by staff.
    admin_serializer_class: Any = None

    @property
    def include_inactive(self) -> bool:
        """Return whether the caller may see deactivated rows."""
        user = getattr(self.request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)

    def get_serializer_class(self) -> Any:
        """Use the admin serializer for writes, the mapped one otherwise."""
        if self.action in {"create", "update", "partial_update"}:
            return self.admin_serializer_class or super().get_serializer_class()
        return super().get_serializer_class()

    def paginated(self, queryset: QuerySet, serializer_class: Any) -> Response:
        """Serialise ``queryset`` through the configured paginator.

        Extra actions that return a list still have to page: "featured
        categories" is small today, but an endpoint that returns an unbounded
        list is a latent problem the first time an editor features two hundred
        rows.
        """
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializer_class(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)

        serializer = serializer_class(
            queryset, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(summary="List categories", tags=["Catalog: Categories"]),
    retrieve=extend_schema(summary="Retrieve a category", tags=["Catalog: Categories"]),
    create=extend_schema(summary="Create a category (staff)", tags=["Catalog: Categories"]),
    update=extend_schema(summary="Replace a category (staff)", tags=["Catalog: Categories"]),
    partial_update=extend_schema(
        summary="Update a category (staff)", tags=["Catalog: Categories"]
    ),
    destroy=extend_schema(summary="Delete a category (staff)", tags=["Catalog: Categories"]),
)
class CategoryViewSet(CatalogViewSetMixin, viewsets.ModelViewSet):
    """Top-level departments, plus the navigation and homepage payloads."""

    serializer_class = CategorySerializer
    admin_serializer_class = CategoryAdminSerializer
    serializer_action_classes = {
        "retrieve": CategoryDetailSerializer,
    }
    filterset_class = CategoryFilter
    search_fields = ["name", "slug", "description"]
    ordering_fields = ["display_order", "name", "created_at"]
    ordering = ["display_order", "name"]

    def get_queryset(self) -> QuerySet[Category]:
        """Return categories visible to the caller, with children prefetched."""
        queryset = services.get_categories(include_inactive=self.include_inactive)
        if self.action == "retrieve":
            return queryset.with_subcategories()
        return queryset.with_counts()

    # -- Navigation ---------------------------------------------------------

    @extend_schema(
        summary="Category tree",
        description="Every active category with its active subcategories nested.",
        responses={200: CategoryTreeSerializer(many=True)},
        tags=["Catalog: Navigation"],
    )
    @action(detail=False, methods=["get"], url_path="tree", pagination_class=None)
    def tree(self, request: Request) -> Response:
        """Return the full navigation tree."""
        return success_response(
            services.get_category_tree(),
            message="Category tree retrieved.",
        )

    @extend_schema(
        summary="Mega menu",
        description=(
            "Nested header navigation: each category with its subcategories, "
            "featured collections and most popular brands."
        ),
        responses={200: MegaMenuSerializer(many=True)},
        tags=["Catalog: Navigation"],
    )
    @action(detail=False, methods=["get"], url_path="mega-menu", pagination_class=None)
    def mega_menu(self, request: Request) -> Response:
        """Return the header mega-menu payload."""
        return success_response(
            services.get_mega_menu(),
            message="Mega menu retrieved.",
        )

    # -- Homepage rails -----------------------------------------------------

    @extend_schema(
        summary="Featured categories",
        responses={200: CategorySerializer(many=True)},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"])
    def featured(self, request: Request) -> Response:
        """Return categories promoted into the featured strip."""
        return self.paginated(services.get_featured_categories(), CategorySerializer)

    @extend_schema(
        summary="Trending categories",
        responses={200: CategorySerializer(many=True)},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"])
    def trending(self, request: Request) -> Response:
        """Return categories marked as trending."""
        return self.paginated(services.get_trending_categories(), CategorySerializer)

    @extend_schema(
        summary="Luxury categories",
        responses={200: CategorySerializer(many=True)},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"])
    def luxury(self, request: Request) -> Response:
        """Return categories in the luxury edit."""
        return self.paginated(services.get_luxury_categories(), CategorySerializer)

    @extend_schema(
        summary="Homepage payload",
        description=(
            "Every catalog rail the homepage needs in one response: featured, "
            "trending and luxury categories; top, featured and luxury brands; "
            "featured, editor's-pick and seasonal collections."
        ),
        responses={200: HomepageSerializer},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"], url_path="homepage", pagination_class=None)
    def homepage(self, request: Request) -> Response:
        """Return every homepage rail in a single round-trip."""
        payload = services.get_homepage_payload()
        serializer = HomepageSerializer(payload, context=self.get_serializer_context())
        return success_response(serializer.data, message="Homepage catalog retrieved.")

    # -- Children -----------------------------------------------------------

    @extend_schema(
        summary="Subcategories of a category",
        responses={200: SubCategorySerializer(many=True)},
        tags=["Catalog: Categories"],
    )
    @action(detail=True, methods=["get"], url_path="subcategories")
    def subcategories(self, request: Request, slug: str | None = None) -> Response:
        """Return the active subcategories of one category."""
        self.get_object()  # 404s for an unknown or hidden category.
        queryset = services.get_subcategories(
            category_slug=slug, include_inactive=self.include_inactive
        )
        return self.paginated(queryset, SubCategorySerializer)

    @extend_schema(
        summary="Brands merchandised under a category",
        responses={200: BrandLiteSerializer(many=True)},
        tags=["Catalog: Categories"],
    )
    @action(detail=True, methods=["get"], url_path="brands")
    def brands(self, request: Request, slug: str | None = None) -> Response:
        """Return the brands linked to one category, most popular first."""
        self.get_object()
        queryset = Brand.objects.active().for_category(slug).popular()
        return self.paginated(queryset, BrandLiteSerializer)

    @extend_schema(
        summary="Collections merchandised under a category",
        responses={200: CollectionLiteSerializer(many=True)},
        tags=["Catalog: Categories"],
    )
    @action(detail=True, methods=["get"], url_path="collections")
    def collections(self, request: Request, slug: str | None = None) -> Response:
        """Return the collections linked to one category."""
        self.get_object()
        queryset = Collection.objects.active().for_category(slug).ordered()
        return self.paginated(queryset, CollectionLiteSerializer)


@extend_schema_view(
    list=extend_schema(summary="List subcategories", tags=["Catalog: Subcategories"]),
    retrieve=extend_schema(
        summary="Retrieve a subcategory", tags=["Catalog: Subcategories"]
    ),
    create=extend_schema(
        summary="Create a subcategory (staff)", tags=["Catalog: Subcategories"]
    ),
    update=extend_schema(
        summary="Replace a subcategory (staff)", tags=["Catalog: Subcategories"]
    ),
    partial_update=extend_schema(
        summary="Update a subcategory (staff)", tags=["Catalog: Subcategories"]
    ),
    destroy=extend_schema(
        summary="Delete a subcategory (staff)", tags=["Catalog: Subcategories"]
    ),
)
class SubCategoryViewSet(CatalogViewSetMixin, viewsets.ModelViewSet):
    """Second-level groupings, filterable by parent category."""

    serializer_class = SubCategorySerializer
    admin_serializer_class = SubCategoryAdminSerializer
    filterset_class = SubCategoryFilter
    search_fields = ["name", "slug", "description", "category__name"]
    ordering_fields = ["display_order", "name", "created_at"]
    ordering = ["display_order", "name"]
    pagination_class = LargePagination

    def get_queryset(self) -> QuerySet[SubCategory]:
        """Return subcategories visible to the caller, with the parent joined."""
        return services.get_subcategories(include_inactive=self.include_inactive)


@extend_schema_view(
    list=extend_schema(summary="List brands", tags=["Catalog: Brands"]),
    retrieve=extend_schema(summary="Retrieve a brand", tags=["Catalog: Brands"]),
    create=extend_schema(summary="Create a brand (staff)", tags=["Catalog: Brands"]),
    update=extend_schema(summary="Replace a brand (staff)", tags=["Catalog: Brands"]),
    partial_update=extend_schema(summary="Update a brand (staff)", tags=["Catalog: Brands"]),
    destroy=extend_schema(summary="Delete a brand (staff)", tags=["Catalog: Brands"]),
)
class BrandViewSet(CatalogViewSetMixin, viewsets.ModelViewSet):
    """Brands, with the homepage rails the storefront renders."""

    serializer_class = BrandSerializer
    admin_serializer_class = BrandAdminSerializer
    filterset_class = BrandFilter
    search_fields = ["name", "slug", "description", "country"]
    ordering_fields = ["display_order", "name", "founded_year", "popularity_score"]
    ordering = ["display_order", "name"]

    def get_queryset(self) -> QuerySet[Brand]:
        """Return brands visible to the caller, with categories prefetched."""
        return services.get_brands(
            include_inactive=self.include_inactive
        ).prefetch_related("categories")

    @extend_schema(
        summary="Featured brands",
        responses={200: BrandSerializer(many=True)},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"])
    def featured(self, request: Request) -> Response:
        """Return brands promoted on the homepage."""
        return self.paginated(services.get_featured_brands(), BrandSerializer)

    @extend_schema(
        summary="Luxury brands",
        responses={200: BrandSerializer(many=True)},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"])
    def luxury(self, request: Request) -> Response:
        """Return brands in the luxury edit."""
        return self.paginated(services.get_luxury_brands(), BrandSerializer)

    @extend_schema(
        summary="Popular brands",
        description="Ranked by popularity score, highest first.",
        responses={200: BrandSerializer(many=True)},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"])
    def popular(self, request: Request) -> Response:
        """Return brands ranked by popularity."""
        return self.paginated(services.get_popular_brands(), BrandSerializer)

    @extend_schema(
        summary="Top brands",
        description="Featured brands, falling back to the most popular.",
        responses={200: BrandLiteSerializer(many=True)},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"], url_path="top")
    def top(self, request: Request) -> Response:
        """Return the homepage's Top Brands rail."""
        return self.paginated(services.get_top_brands(), BrandLiteSerializer)


@extend_schema_view(
    list=extend_schema(summary="List collections", tags=["Catalog: Collections"]),
    retrieve=extend_schema(
        summary="Retrieve a collection", tags=["Catalog: Collections"]
    ),
    create=extend_schema(
        summary="Create a collection (staff)", tags=["Catalog: Collections"]
    ),
    update=extend_schema(
        summary="Replace a collection (staff)", tags=["Catalog: Collections"]
    ),
    partial_update=extend_schema(
        summary="Update a collection (staff)", tags=["Catalog: Collections"]
    ),
    destroy=extend_schema(
        summary="Delete a collection (staff)", tags=["Catalog: Collections"]
    ),
)
class CollectionViewSet(CatalogViewSetMixin, viewsets.ModelViewSet):
    """Editorial collections and the homepage rails built from them."""

    serializer_class = CollectionSerializer
    admin_serializer_class = CollectionAdminSerializer
    filterset_class = CollectionFilter
    search_fields = ["title", "slug", "description"]
    ordering_fields = ["display_order", "title", "created_at"]
    ordering = ["display_order", "title"]

    def get_queryset(self) -> QuerySet[Collection]:
        """Return collections visible to the caller, with categories prefetched."""
        return services.get_collections(
            include_inactive=self.include_inactive
        ).prefetch_related("categories")

    @extend_schema(
        summary="Featured collections",
        responses={200: CollectionSerializer(many=True)},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"])
    def featured(self, request: Request) -> Response:
        """Return collections promoted on the homepage."""
        return self.paginated(services.get_featured_collections(), CollectionSerializer)

    @extend_schema(
        summary="Seasonal collections",
        description="Festival, wedding, summer and winter collections.",
        responses={200: CollectionSerializer(many=True)},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"])
    def seasonal(self, request: Request) -> Response:
        """Return the season- and festival-driven collections."""
        return self.paginated(services.get_seasonal_collections(), CollectionSerializer)

    @extend_schema(
        summary="Editor's picks",
        responses={200: CollectionSerializer(many=True)},
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"], url_path="editors-picks")
    def editors_picks(self, request: Request) -> Response:
        """Return the Editor's Picks collections."""
        return self.paginated(services.get_editors_picks(), CollectionSerializer)

    @extend_schema(
        summary="Homepage collection rails",
        description="Every collection rail the homepage renders, keyed by rail name.",
        parameters=[
            OpenApiParameter(
                name="limit",
                description="Maximum items per rail.",
                required=False,
                type=int,
            )
        ],
        tags=["Catalog: Homepage"],
    )
    @action(detail=False, methods=["get"], url_path="homepage", pagination_class=None)
    def homepage(self, request: Request) -> Response:
        """Return the collection rails grouped by name."""
        try:
            limit = int(request.query_params.get("limit", 8))
        except (TypeError, ValueError):
            limit = 8
        limit = max(1, min(limit, 50))

        context = self.get_serializer_context()
        payload = {
            rail: CollectionLiteSerializer(
                queryset[:limit], many=True, context=context
            ).data
            for rail, queryset in services.get_homepage_collections().items()
        }
        return success_response(payload, message="Homepage collections retrieved.")
