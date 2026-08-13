"""Wishlist API views. Thin by construction."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.pagination import StandardPagination
from apps.core.responses import success_response
from apps.wishlist import services
from apps.wishlist.serializers import (
    MoveToCartSerializer,
    WishlistActionSerializer,
    WishlistCountSerializer,
    WishlistItemSerializer,
    WishlistToggleResultSerializer,
)


@extend_schema(tags=["Wishlist"])
class WishlistViewSet(viewsets.GenericViewSet):
    """A customer's saved products.

    A ``GenericViewSet`` rather than a ``ModelViewSet``: the wishlist is a
    singleton per user, so there is no id in any URL and no list of wishlists
    to page through. Every route acts on "my wishlist".
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    serializer_class = WishlistItemSerializer

    def get_queryset(self) -> Any:
        """Return the requesting user's saved products."""
        return services.get_wishlist_items(self.request.user)

    @extend_schema(
        summary="List saved products",
        responses={200: WishlistItemSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        """Return the wishlist page payload."""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(
            page if page is not None else queryset, many=True
        )
        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Wishlist retrieved."
            return response
        return success_response(serializer.data, message="Wishlist retrieved.")

    @extend_schema(
        summary="Add a product",
        request=WishlistActionSerializer,
        responses={201: WishlistItemSerializer},
    )
    @action(detail=False, methods=["post"])
    def add(self, request: Request) -> Response:
        """Save a product. Adding twice is a no-op, not an error."""
        payload = WishlistActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        item, created = services.add_to_wishlist(
            request.user, payload.validated_data["product"]
        )
        return success_response(
            WishlistItemSerializer(item, context=self.get_serializer_context()).data,
            message="Added to wishlist." if created else "Already in your wishlist.",
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Remove a product",
        request=WishlistActionSerializer,
        responses={200: WishlistCountSerializer},
    )
    @action(detail=False, methods=["post"])
    def remove(self, request: Request) -> Response:
        """Remove a saved product."""
        payload = WishlistActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        removed = services.remove_from_wishlist(
            request.user, payload.validated_data["product"]
        )
        return success_response(
            {"count": services.get_wishlist_count(request.user)},
            message="Removed from wishlist." if removed else "It was not in your wishlist.",
        )

    @extend_schema(
        summary="Toggle a product",
        description="Adds when absent, removes when present. One call per heart tap.",
        request=WishlistActionSerializer,
        responses={200: WishlistToggleResultSerializer},
    )
    @action(detail=False, methods=["post"])
    def toggle(self, request: Request) -> Response:
        """Flip a product's saved state."""
        payload = WishlistActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        result = services.toggle_wishlist(
            request.user, payload.validated_data["product"]
        )
        return success_response(
            result,
            message="Added to wishlist." if result["in_wishlist"] else "Removed from wishlist.",
        )

    @extend_schema(
        summary="Wishlist badge count",
        responses={200: WishlistCountSerializer},
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def count(self, request: Request) -> Response:
        """Return the navbar badge count."""
        return success_response(
            {"count": services.get_wishlist_count(request.user)},
            message="Wishlist count.",
        )

    @extend_schema(
        summary="Clear the wishlist",
        responses={200: OpenApiResponse(description="Wishlist emptied.")},
    )
    @action(detail=False, methods=["post"])
    def clear(self, request: Request) -> Response:
        """Remove every saved product."""
        removed = services.clear_wishlist(request.user)
        return success_response(
            {"removed": removed, "count": 0},
            message=f"Removed {removed} item(s) from your wishlist.",
        )

    @extend_schema(
        summary="Move a saved product to the cart",
        description="Requires a variant SKU — a wishlist entry carries no size or colour.",
        request=MoveToCartSerializer,
    )
    @action(detail=False, methods=["post"], url_path="move-to-cart")
    def move_to_cart(self, request: Request) -> Response:
        """Move one saved product into the cart."""
        from apps.cart.serializers import CartItemSerializer

        payload = MoveToCartSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        result = services.move_to_cart(
            request.user,
            payload.validated_data["product"],
            payload.validated_data["variant"],
            payload.validated_data["quantity"],
        )
        return success_response(
            {
                "cart_item": CartItemSerializer(
                    result["cart_item"], context=self.get_serializer_context()
                ).data,
                "wishlist_count": result["wishlist_count"],
            },
            message="Moved to your bag.",
        )

    @extend_schema(
        summary="Saved product slugs",
        description=(
            "Every saved slug in one call, so a listing page can render heart "
            "states without asking per card."
        ),
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def slugs(self, request: Request) -> Response:
        """Return the set of saved product slugs."""
        return success_response(
            {"slugs": sorted(services.wishlist_product_slugs(request.user))},
            message="Wishlist slugs.",
        )
