"""Recommendation API views. Thin by construction."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.responses import success_response
from apps.core.throttling import ProductViewThrottle
from apps.products.models import Product
from apps.products.serializers import ProductCardSerializer
from apps.recommendations import services
from apps.recommendations.models import RecentlyViewed
from apps.recommendations.permissions import IsRecommendationAdmin
from apps.recommendations.serializers import (
    BundleItemSerializer,
    DiagnosticsSerializer,
    RecordViewSerializer,
    TrendingRowSerializer,
)
from apps.recommendations.validators import clamp_days, clamp_limit

#: Same header the cart uses, so the Next.js client carries one guest identity
#: for its bag and its browsing trail rather than two that can disagree.
TRAIL_SESSION_HEADER = "HTTP_X_CART_SESSION"

SESSION_PARAM = OpenApiParameter(
    name="X-Cart-Session",
    location=OpenApiParameter.HEADER,
    description="Guest session key. Merged into the account on first authenticated call.",
    required=False,
    type=str,
)

LIMIT_PARAM = OpenApiParameter(
    "limit", int, description="Rail size, clamped to 50."
)


class TrailOwnerMixin:
    """Resolves whose browsing trail a request is about.

    Shared by both viewsets so the guest-versus-account decision — and the
    one-time merge that follows a sign-in — is written once.
    """

    request: Request

    def guest_session_key(self) -> str:
        """Return the guest session key, creating a Django session if needed."""
        supplied = self.request.META.get(TRAIL_SESSION_HEADER, "").strip()
        if supplied:
            return supplied[:64]

        session = self.request.session
        if not session.session_key:
            session.create()
        return session.session_key or ""

    def trail_owner(self) -> dict[str, Any]:
        """Return the owner kwargs for this request, merging a guest trail.

        The merge happens here rather than on a login signal because Module 2
        authenticates with JWT, which never fires ``user_logged_in``. Doing it
        at resolution time also means it works whichever endpoint the client
        happens to call first after signing in.
        """
        user = getattr(self.request, "user", None)

        if user is not None and user.is_authenticated:
            supplied = self.request.META.get(TRAIL_SESSION_HEADER, "").strip()
            if supplied:
                services.merge_recently_viewed(user, supplied[:64])
            return {"user": user, "session_key": ""}

        return {"user": None, "session_key": self.guest_session_key()}


@extend_schema(tags=["Recommendations"], parameters=[SESSION_PARAM])
class RecentlyViewedViewSet(TrailOwnerMixin, viewsets.GenericViewSet):
    """A shopper's browsing trail — guest or signed-in, same routes."""

    permission_classes = [AllowAny]
    serializer_class = ProductCardSerializer
    pagination_class = None
    # Never queried — the rails build their own querysets. Present so
    # drf-spectacular can introspect the viewset instead of warning.
    queryset = RecentlyViewed.objects.none()

    @extend_schema(
        summary="My recently viewed products",
        parameters=[LIMIT_PARAM],
        responses={200: ProductCardSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        """Return the trail, most recent first."""
        owner = self.trail_owner()
        products = services.get_recently_viewed(
            **owner, limit=clamp_limit(request.query_params.get("limit"), 30)
        )
        return success_response(
            ProductCardSerializer(products, many=True, context={"request": request}).data,
            message="Recently viewed retrieved.",
        )

    @extend_schema(
        summary="Record a product view",
        request=RecordViewSerializer,
        responses={201: None},
    )
    def get_throttles(self) -> list[Any]:
        """Throttle only the write.

        The reads are cheap and the rails are cached; the write is the one that
        fires on every product-page navigation.
        """
        if self.action == "create":
            return [ProductViewThrottle()]
        return super().get_throttles()

    def create(self, request: Request) -> Response:
        """Add a product to the trail, or move it back to the top.

        Fire-and-forget from the client's point of view: the product page calls
        this and does not wait on it, so the response carries no payload.
        """
        payload = RecordViewSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        product = get_object_or_404(
            Product.objects.visible(), slug=payload.validated_data["product"]
        )
        services.record_view(product, **self.trail_owner())
        return success_response(
            None, message="View recorded.", status=status.HTTP_201_CREATED
        )

    @extend_schema(summary="Remove one product from my trail", responses={200: None})
    @action(detail=False, methods=["delete"], url_path="item/(?P<slug>[^/.]+)")
    def remove(self, request: Request, slug: str) -> Response:
        """Drop one product from the trail."""
        removed = services.remove_from_recently_viewed(slug, **self.trail_owner())
        return success_response({"removed": removed}, message="Removed from history.")

    @extend_schema(summary="Clear my trail", responses={200: None})
    @action(detail=False, methods=["delete"])
    def clear(self, request: Request) -> Response:
        """Erase the whole browsing trail."""
        removed = services.clear_recently_viewed(**self.trail_owner())
        return success_response({"removed": removed}, message="Browsing history cleared.")


@extend_schema(tags=["Recommendations"], parameters=[SESSION_PARAM, LIMIT_PARAM])
class RecommendationViewSet(TrailOwnerMixin, viewsets.GenericViewSet):
    """The eight recommendation rails.

    Product-scoped rails take the slug as a path segment; shopper-scoped rails
    take nothing and read the caller's identity. Both live on one viewset
    because they share the owner resolution and the limit clamping.
    """

    permission_classes = [AllowAny]
    serializer_class = ProductCardSerializer
    pagination_class = None
    queryset = Product.objects.none()

    # -- Helpers ------------------------------------------------------------

    def limit(self, default: int = 12) -> int:
        """Return the requested rail size, clamped."""
        return clamp_limit(self.request.query_params.get("limit"), default)

    def product(self, slug: str) -> Product:
        """Return the product named in the URL, or 404."""
        return get_object_or_404(Product.objects.visible(), slug=slug)

    def cards(self, products: Any, message: str) -> Response:
        """Serialise any rail as product cards."""
        return success_response(
            ProductCardSerializer(
                products, many=True, context={"request": self.request}
            ).data,
            message=message,
        )

    # -- Product-scoped rails ------------------------------------------------

    @extend_schema(
        summary="Related products",
        responses={200: ProductCardSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path=r"products/(?P<slug>[^/.]+)/related")
    def related(self, request: Request, slug: str) -> Response:
        """Rail 1 — same subcategory, ranked by popularity."""
        return self.cards(
            services.get_related(self.product(slug), limit=self.limit()),
            "Related products retrieved.",
        )

    @extend_schema(
        summary="Similar products",
        responses={200: ProductCardSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path=r"products/(?P<slug>[^/.]+)/similar")
    def similar(self, request: Request, slug: str) -> Response:
        """Rail 2 — matching on brand, material, occasion and price band."""
        return self.cards(
            services.get_similar(self.product(slug), limit=self.limit()),
            "Similar products retrieved.",
        )

    @extend_schema(
        summary="Frequently bought together",
        responses={200: BundleItemSerializer(many=True)},
    )
    @action(
        detail=False,
        methods=["get"],
        url_path=r"products/(?P<slug>[^/.]+)/frequently-bought-together",
    )
    def frequently_bought_together(self, request: Request, slug: str) -> Response:
        """Rail 3 — ranked bundles from real order history."""
        bundles = services.get_frequently_bought_together(
            self.product(slug), limit=self.limit(4)
        )
        return success_response(
            BundleItemSerializer(
                bundles, many=True, context={"request": request}
            ).data,
            message="Bundles retrieved.",
        )

    @extend_schema(
        summary="Customers also viewed",
        responses={200: ProductCardSerializer(many=True)},
    )
    @action(
        detail=False, methods=["get"], url_path=r"products/(?P<slug>[^/.]+)/also-viewed"
    )
    def also_viewed(self, request: Request, slug: str) -> Response:
        """Rail 6 — what other shoppers looked at in the same session."""
        return self.cards(
            services.get_customers_also_viewed(self.product(slug), limit=self.limit()),
            "Also viewed retrieved.",
        )

    # -- Catalogue-wide rails ------------------------------------------------

    @extend_schema(
        summary="Trending now", responses={200: ProductCardSerializer(many=True)}
    )
    @action(detail=False, methods=["get"])
    def trending(self, request: Request) -> Response:
        """Rail 4 — highest trending score across the catalogue."""
        return self.cards(services.get_trending(self.limit()), "Trending retrieved.")

    @extend_schema(
        summary="Recently popular",
        parameters=[OpenApiParameter("days", int, description="Window, default 30.")],
        responses={200: ProductCardSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="recently-popular")
    def recently_popular(self, request: Request) -> Response:
        """Rail 5 — most units actually sold in the window."""
        days = clamp_days(request.query_params.get("days"), 30)
        return self.cards(
            services.get_recently_popular(self.limit(), days=days),
            "Recently popular retrieved.",
        )

    # -- Shopper-scoped rails ------------------------------------------------

    @extend_schema(
        summary="New arrivals for you",
        responses={200: ProductCardSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="new-for-you")
    def new_for_you(self, request: Request) -> Response:
        """Rail 7 — recent arrivals in the categories this shopper browses."""
        return self.cards(
            services.get_new_for_you(request.user, limit=self.limit()),
            "New arrivals retrieved.",
        )

    @extend_schema(
        summary="Recommended for you",
        responses={200: ProductCardSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="for-you")
    def for_you(self, request: Request) -> Response:
        """Rail 8 — the personalised catch-all, trending when unpersonalised."""
        return self.cards(
            services.get_recommended_for_you(request.user, limit=self.limit()),
            "Recommendations retrieved.",
        )


@extend_schema(tags=["Recommendations — Admin"])
class RecommendationAdminViewSet(viewsets.GenericViewSet):
    """Trending dashboard and per-product diagnostics for staff."""

    permission_classes = [IsRecommendationAdmin]
    serializer_class = TrendingRowSerializer
    pagination_class = None
    queryset = Product.objects.none()

    @extend_schema(
        summary="Trending leaderboard",
        parameters=[OpenApiParameter("limit", int, description="Rows, default 25.")],
        responses={200: TrendingRowSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def trending(self, request: Request) -> Response:
        """Return the ranking with every score broken into its terms."""
        rows = services.get_trending_dashboard(
            limit=clamp_limit(request.query_params.get("limit"), 25)
        )
        return success_response(
            TrendingRowSerializer(rows, many=True).data,
            message="Trending dashboard retrieved.",
        )

    @extend_schema(
        summary="Explain one product's recommendations",
        responses={200: DiagnosticsSerializer},
    )
    @action(detail=False, methods=["get"], url_path=r"diagnose/(?P<slug>[^/.]+)")
    def diagnose(self, request: Request, slug: str) -> Response:
        """Report what each rail would produce for a product, and why."""
        product = get_object_or_404(Product, slug=slug)
        return success_response(
            DiagnosticsSerializer(services.diagnose(product)).data,
            message="Diagnostics retrieved.",
        )

    @extend_schema(summary="Rebuild the co-purchase graph", responses={200: None})
    @action(detail=False, methods=["post"], url_path="rebuild-affinities")
    def rebuild_affinities(self, request: Request) -> Response:
        """Recompute "frequently bought together" from order history.

        Exposed so a merchandiser can refresh the graph after a campaign
        without waiting for the nightly command or asking for a shell.
        """
        return success_response(
            services.rebuild_affinities(), message="Affinity graph rebuilt."
        )
