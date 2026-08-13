"""Banner API views. Thin by construction."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, F
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.banner.models import Banner, BannerPlacement
from apps.banner.serializers import BannerAdminSerializer, BannerSerializer
from apps.core.pagination import StandardPagination
from apps.core.permissions import IsAdmin
from apps.core.responses import success_response


@extend_schema(tags=["Banners"])
class BannerViewSet(viewsets.GenericViewSet):
    """Public, read-only banner feed for the storefront."""

    permission_classes = [AllowAny]
    serializer_class = BannerSerializer
    pagination_class = None
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    queryset = Banner.objects.none()

    def get_queryset(self) -> Any:
        """Return banners that are live now, optionally for one placement."""
        queryset = Banner.objects.live().ordered()
        placement = self.request.query_params.get("placement")
        if placement in BannerPlacement.values:
            queryset = queryset.for_placement(placement)
        return queryset

    @extend_schema(
        summary="List live banners",
        parameters=[
            OpenApiParameter(
                "placement",
                str,
                description="hero | strip | grid_left | grid_right | category_top | footer",
            )
        ],
        responses={200: BannerSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        """Return every banner currently inside its scheduled window."""
        return success_response(
            self.get_serializer(self.get_queryset(), many=True).data,
            message="Banners retrieved.",
        )

    @extend_schema(
        summary="Banners grouped by placement", responses={200: BannerSerializer(many=True)}
    )
    @action(detail=False, methods=["get"])
    def homepage(self, request: Request) -> Response:
        """Return live banners keyed by placement, in one round trip.

        The homepage renders a hero carousel, a strip and two grid tiles at
        once; four separate requests would be four chances for one to be slow.
        """
        grouped: dict[str, list[Any]] = {value: [] for value in BannerPlacement.values}
        for banner in Banner.objects.live().ordered():
            grouped[banner.placement].append(
                BannerSerializer(banner, context={"request": request}).data
            )
        return success_response(grouped, message="Homepage banners retrieved.")

    @extend_schema(summary="Record an impression", responses={200: None})
    @action(detail=True, methods=["post"])
    def impression(self, request: Request, uuid: str) -> Response:
        """Count a banner being shown.

        ``F()`` rather than read-modify-write: impressions arrive concurrently
        from every visitor, and loading the value into Python would lose most
        of them under exactly the traffic that makes the number interesting.
        """
        Banner.objects.filter(uuid=uuid).update(
            impression_count=F("impression_count") + 1
        )
        return success_response(None, message="Impression recorded.")

    @extend_schema(summary="Record a click", responses={200: None})
    @action(detail=True, methods=["post"])
    def click(self, request: Request, uuid: str) -> Response:
        """Count a banner being clicked."""
        Banner.objects.filter(uuid=uuid).update(click_count=F("click_count") + 1)
        return success_response(None, message="Click recorded.")


@extend_schema(tags=["Banners — Admin"])
class BannerAdminViewSet(viewsets.ModelViewSet):
    """Full CRUD over banners, for staff.

    A ``ModelViewSet`` here rather than the project's usual thin
    ``GenericViewSet``: a banner has no business rules beyond its schedule,
    which the serializer and a CHECK constraint already enforce. There is no
    service layer to keep the view out of.
    """

    permission_classes = [IsAdmin]
    serializer_class = BannerAdminSerializer
    pagination_class = StandardPagination
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    def get_queryset(self) -> Any:
        """Return all banners, filtered by ``?placement=`` and ``?active=``."""
        queryset = Banner.objects.all()

        placement = self.request.query_params.get("placement")
        if placement in BannerPlacement.values:
            queryset = queryset.for_placement(placement)

        active = self.request.query_params.get("active")
        if active is not None:
            queryset = queryset.filter(
                is_active=str(active).lower() in {"1", "true", "yes"}
            )
        return queryset.ordered()

    @extend_schema(
        summary="Placements and their live counts", responses={200: None}
    )
    @action(detail=False, methods=["get"])
    def placements(self, request: Request) -> Response:
        """Return every placement with how many banners are live in it.

        Lets the admin UI show "hero (3 live)" without a request per slot.
        """
        live = {
            row["placement"]: row["total"]
            for row in Banner.objects.live()
            .values("placement")
            .annotate(total=Count("id"))
        }
        return success_response(
            [
                {"value": value, "label": label, "live": live.get(value, 0)}
                for value, label in BannerPlacement.choices
            ],
            message="Placements retrieved.",
        )
