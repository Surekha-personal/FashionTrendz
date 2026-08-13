"""Coupon API views. Thin by construction."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.cart.services import get_or_create_cart, recalculate_cart
from apps.core.pagination import StandardPagination
from apps.core.responses import success_response
from apps.coupons import services
from apps.coupons.models import Coupon
from apps.coupons.permissions import CouponPermission
from apps.coupons.serializers import (
    ApplyCouponSerializer,
    CouponAdminSerializer,
    CouponResultSerializer,
    CouponSerializer,
    CouponUsageSerializer,
)


@extend_schema_view(
    list=extend_schema(summary="Available offers", tags=["Coupons"]),
    retrieve=extend_schema(summary="Coupon detail", tags=["Coupons"]),
    create=extend_schema(summary="Create a coupon (staff)", tags=["Coupons"]),
    update=extend_schema(summary="Replace a coupon (staff)", tags=["Coupons"]),
    partial_update=extend_schema(summary="Update a coupon (staff)", tags=["Coupons"]),
    destroy=extend_schema(summary="Delete a coupon (staff)", tags=["Coupons"]),
)
class CouponViewSet(viewsets.ModelViewSet):
    """Offers the storefront advertises, plus staff management.

    The public queryset is ``Coupon.objects.public()`` — redeemable *and*
    flagged public — so private influencer and goodwill codes never appear in
    the list even though anyone may read it.
    """

    permission_classes = [CouponPermission]
    pagination_class = StandardPagination
    lookup_field = "code"
    lookup_value_regex = "[A-Z0-9-]+"
    serializer_class = CouponSerializer

    @property
    def is_staff(self) -> bool:
        """Return whether the caller may see private and expired coupons."""
        user = getattr(self.request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)

    def get_serializer_class(self) -> Any:
        """Admin serializer for staff and for writes; public one otherwise."""
        if self.is_staff or self.action in {"create", "update", "partial_update"}:
            return CouponAdminSerializer
        return CouponSerializer

    def get_queryset(self) -> Any:
        """Return coupons visible to the caller."""
        if self.is_staff:
            return Coupon.objects.with_restrictions().order_by("-created_at")
        return services.get_public_coupons()

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return the offers list."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)

        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Available offers."
            return response
        return success_response(serializer.data, message="Available offers.")

    # -- Cart integration ---------------------------------------------------

    def _cart(self) -> Any:
        """Return the caller's cart with its money refreshed."""
        cart = get_or_create_cart(user=self.request.user)
        recalculate_cart(cart)
        return cart

    @extend_schema(
        summary="Check a coupon without applying it",
        description="Reports what the code would save. Used by the checkout preview.",
        request=ApplyCouponSerializer,
        responses={200: CouponResultSerializer},
        tags=["Coupons"],
    )
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated],
        pagination_class=None,
    )
    def validate(self, request: Request) -> Response:
        """Return what a coupon would save, without applying it."""
        payload = ApplyCouponSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        result = services.preview_coupon(
            payload.validated_data["code"], self._cart(), request.user
        )
        # Through the serializer, not raw: DRF renders a bare Decimal as a JSON
        # float, and 200.0 for money is how rounding errors reach a client.
        return success_response(
            CouponResultSerializer(
                {
                    "code": result["code"],
                    "discount": result["discount"],
                    "applied": False,
                    "free_shipping": result["free_shipping"],
                    "message": f"{result['code']} would save you {result['discount']}.",
                }
            ).data,
            message="Coupon is valid.",
        )

    @extend_schema(
        summary="Apply a coupon to the cart",
        request=ApplyCouponSerializer,
        responses={200: CouponResultSerializer},
        tags=["Coupons"],
    )
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated],
        pagination_class=None,
    )
    def apply(self, request: Request) -> Response:
        """Validate a coupon and write its discount onto the cart."""
        payload = ApplyCouponSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        result = services.apply_coupon_to_cart(
            self._cart(), payload.validated_data["code"], request.user
        )
        return success_response(
            CouponResultSerializer(result).data, message=result["message"]
        )

    @extend_schema(
        summary="Remove the cart's coupon",
        responses={200: CouponResultSerializer},
        tags=["Coupons"],
    )
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated],
        pagination_class=None,
    )
    def remove(self, request: Request) -> Response:
        """Clear any coupon from the cart."""
        result = services.remove_coupon_from_cart(self._cart())
        return success_response(
            CouponResultSerializer(result).data, message=result["message"]
        )

    @extend_schema(
        summary="My coupon history",
        responses={200: CouponUsageSerializer(many=True)},
        tags=["Coupons"],
    )
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def usages(self, request: Request) -> Response:
        """Return the customer's redemption history."""
        queryset = services.get_user_usages(request.user)
        page = self.paginate_queryset(queryset)
        serializer = CouponUsageSerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Your coupon history."
            return response
        return success_response(serializer.data, message="Your coupon history.")
