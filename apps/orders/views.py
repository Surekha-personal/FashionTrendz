"""Checkout and order API views. Thin by construction.

Two viewsets: one for the checkout flow (which owns no rows of its own), one
for orders. Orders are addressed by ``order_number`` — the string the customer
sees in their email — and every queryset is scoped to ``request.user``, so a
guessed number returns 404 rather than a stranger's home address.
"""

from __future__ import annotations

from typing import Any

from django.http import FileResponse, Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.cart.serializers import CartSerializer, CartSummarySerializer
from apps.core.exceptions import BusinessRuleViolation
from apps.core.pagination import StandardPagination
from apps.core.responses import success_response
from apps.core.throttling import CheckoutThrottle
from apps.orders import services
from apps.orders.models import Order
from apps.orders.permissions import CanManageOrders
from apps.orders.serializers import (
    CancelOrderSerializer,
    CheckoutContextSerializer,
    InvoiceSerializer,
    OrderDetailSerializer,
    OrderReviewSerializer,
    OrderStatusUpdateSerializer,
    OrderSummarySerializer,
    PlaceOrderSerializer,
    ReorderResultSerializer,
    ReturnRequestSerializer,
    ReviewOrderSerializer,
    ShipmentCreateSerializer,
    ShipmentSerializer,
    TrackingSerializer,
)


@extend_schema(tags=["Checkout"])
class CheckoutViewSet(viewsets.GenericViewSet):
    """The checkout flow: context, review, place order.

    Owns no model of its own — it reads the cart and writes an order — so a
    plain ``GenericViewSet`` rather than a ``ModelViewSet``.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CheckoutContextSerializer
    pagination_class = None

    @extend_schema(
        summary="Checkout context",
        description=(
            "Cart, totals, saved addresses and the available payment and "
            "delivery methods. Read-only — nothing is reserved by loading it."
        ),
        responses={200: CheckoutContextSerializer},
    )
    def list(self, request: Request) -> Response:
        """Return everything the checkout page needs."""
        context = services.get_checkout_context(request.user)
        serializer = CheckoutContextSerializer(
            context, context=self.get_serializer_context()
        )
        return success_response(serializer.data, message="Checkout ready.")

    @extend_schema(
        summary="Review the order",
        description=(
            "Runs every validation that placing an order runs, and returns the "
            "exact order that would be created — without creating it."
        ),
        request=ReviewOrderSerializer,
        responses={200: OrderReviewSerializer},
    )
    @action(detail=False, methods=["post"])
    def review(self, request: Request) -> Response:
        """Return the order that would be created."""
        payload = ReviewOrderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        review = services.review_order(
            request.user,
            shipping_address_id=payload.validated_data["shipping_address"],
            billing_address_id=payload.validated_data.get("billing_address"),
            payment_method=payload.validated_data["payment_method"],
            delivery_method=payload.validated_data["delivery_method"],
        )
        return success_response(
            OrderReviewSerializer(review, context=self.get_serializer_context()).data,
            message="Review your order.",
        )

    @extend_schema(
        summary="Place the order",
        description=(
            "Converts the cart into an order in one transaction: reserves and "
            "commits stock, freezes prices and addresses, and empties the bag."
        ),
        request=PlaceOrderSerializer,
        responses={201: OrderDetailSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="place-order",
        throttle_classes=[CheckoutThrottle],
    )
    def place_order(self, request: Request) -> Response:
        """Turn the cart into an order."""
        payload = PlaceOrderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        order = services.place_order(
            request.user,
            shipping_address_id=payload.validated_data["shipping_address"],
            billing_address_id=payload.validated_data.get("billing_address"),
            payment_method=payload.validated_data["payment_method"],
            delivery_method=payload.validated_data["delivery_method"],
            notes=payload.validated_data.get("notes", ""),
        )

        order = services.get_order(request.user, order.order_number)
        return success_response(
            OrderDetailSerializer(order, context=self.get_serializer_context()).data,
            message=f"Order {order.order_number} placed.",
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    list=extend_schema(summary="Order history", tags=["Orders"]),
    retrieve=extend_schema(summary="Order detail", tags=["Orders"]),
)
class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """A customer's orders.

    Read-only by design: an order is never edited through this API. It changes
    state through the explicit actions below, each of which routes into the
    service layer's state machine.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    lookup_field = "order_number"
    lookup_value_regex = "FT-ORD-[0-9]{8}-[A-Z0-9]{6}"
    serializer_class = OrderSummarySerializer

    @property
    def is_staff(self) -> bool:
        """Return whether the caller may see other customers' orders."""
        user = getattr(self.request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)

    def get_serializer_class(self) -> Any:
        """Summary for the list, detail for a single order."""
        return OrderDetailSerializer if self.action == "retrieve" else OrderSummarySerializer

    def get_queryset(self) -> Any:
        """Return the caller's orders, loaded for the current action."""
        if self.action == "list":
            return services.get_orders(self.request.user)

        queryset = Order.objects.with_detail()
        if not self.is_staff:
            queryset = queryset.for_user(self.request.user)
        return queryset

    def _order(self) -> Order:
        """Return the addressed order, scoped to its owner unless staff."""
        return services.get_order(
            self.request.user,
            self.kwargs[self.lookup_field],
            staff=self.is_staff,
        )

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return the order-history page."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)

        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Your orders."
            return response
        return success_response(serializer.data, message="Your orders.")

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return one order in full."""
        serializer = OrderDetailSerializer(
            self._order(), context=self.get_serializer_context()
        )
        return success_response(serializer.data, message="Order details.")

    # -- Customer actions ---------------------------------------------------

    @extend_schema(
        summary="Cancel an order",
        description=(
            "Allowed until the parcel is handed to the courier. Returns the "
            "reserved or committed stock to circulation in the same transaction."
        ),
        request=CancelOrderSerializer,
        responses={200: OrderDetailSerializer},
        tags=["Orders"],
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, order_number: str | None = None) -> Response:
        """Cancel an order and release its inventory."""
        payload = CancelOrderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        order = self._order()
        if not self.is_staff and order.user_id != request.user.pk:
            raise Http404

        services.cancel_order(
            order, reason=payload.validated_data["reason"], cancelled_by=request.user
        )

        refreshed = services.get_order(request.user, order.order_number, staff=self.is_staff)
        return success_response(
            OrderDetailSerializer(refreshed, context=self.get_serializer_context()).data,
            message="Order cancelled.",
        )

    @extend_schema(
        summary="Order tracking",
        responses={200: TrackingSerializer},
        tags=["Orders"],
    )
    @action(detail=True, methods=["get"])
    def tracking(self, request: Request, order_number: str | None = None) -> Response:
        """Return the tracking timeline."""
        return success_response(
            TrackingSerializer(services.get_tracking(self._order())).data,
            message="Tracking details.",
        )

    @extend_schema(
        summary="Invoice data",
        description="JSON invoice. Add ?download=1 for the PDF.",
        responses={200: InvoiceSerializer},
        tags=["Orders"],
    )
    @action(detail=True, methods=["get"])
    def invoice(self, request: Request, order_number: str | None = None) -> Response:
        """Return the invoice, as JSON or as a PDF download."""
        order = self._order()

        if str(request.query_params.get("download", "")).lower() in {"1", "true", "yes"}:
            handle = services.generate_invoice_pdf(order)
            handle.open("rb")
            return FileResponse(
                handle,
                as_attachment=True,
                filename=f"{order.invoice_number}.pdf",
                content_type="application/pdf",
            )

        context = services.get_invoice_context(order)
        return success_response(
            InvoiceSerializer(context, context=self.get_serializer_context()).data,
            message="Invoice.",
        )

    @extend_schema(
        summary="Reorder",
        description=(
            "Adds the still-available items back to the bag. Reports which "
            "lines were skipped rather than refusing the whole reorder."
        ),
        responses={200: ReorderResultSerializer},
        tags=["Orders"],
    )
    @action(detail=True, methods=["post"])
    def reorder(self, request: Request, order_number: str | None = None) -> Response:
        """Put a past order's items back in the bag."""
        result = services.reorder(self._order(), request.user)

        from apps.cart.services import load_cart

        return success_response(
            {
                "added": result["added"],
                "skipped": result["skipped"],
                "cart": CartSerializer(
                    load_cart(result["cart"]), context=self.get_serializer_context()
                ).data,
            },
            message=f"{len(result['added'])} item(s) added back to your bag.",
        )

    @extend_schema(
        summary="Request a return (placeholder)",
        description="Records the request and moves the order. No reverse pickup yet.",
        request=ReturnRequestSerializer,
        tags=["Orders"],
    )
    @action(detail=True, methods=["post"], url_path="request-return")
    def request_return(self, request: Request, order_number: str | None = None) -> Response:
        """Record a return request."""
        payload = ReturnRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        order = services.request_return(
            self._order(),
            reason=payload.validated_data["reason"],
            requested_by=request.user,
        )
        refreshed = services.get_order(request.user, order.order_number, staff=self.is_staff)
        return success_response(
            OrderDetailSerializer(refreshed, context=self.get_serializer_context()).data,
            message="Return requested.",
        )

    # -- Staff actions ------------------------------------------------------

    @extend_schema(
        summary="Update order status (staff)",
        request=OrderStatusUpdateSerializer,
        responses={200: OrderDetailSerializer},
        tags=["Orders: Fulfilment"],
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="update-status",
        permission_classes=[CanManageOrders],
    )
    def update_status(self, request: Request, order_number: str | None = None) -> Response:
        """Move an order through the fulfilment state machine."""
        payload = OrderStatusUpdateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        order = services.get_order(request.user, order_number, staff=True)
        services.transition_order(
            order,
            payload.validated_data["status"],
            changed_by=request.user,
            remarks=payload.validated_data.get("remarks", ""),
        )

        refreshed = services.get_order(request.user, order_number, staff=True)
        return success_response(
            OrderDetailSerializer(refreshed, context=self.get_serializer_context()).data,
            message=f"Order moved to {payload.validated_data['status']}.",
        )

    @extend_schema(
        summary="Record a shipment (staff)",
        request=ShipmentCreateSerializer,
        responses={201: ShipmentSerializer},
        tags=["Orders: Fulfilment"],
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="shipments",
        permission_classes=[CanManageOrders],
    )
    def create_shipment(self, request: Request, order_number: str | None = None) -> Response:
        """Record a dispatched parcel against an order."""
        payload = ShipmentCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        order = services.get_order(request.user, order_number, staff=True)
        shipment = services.create_shipment(order, **payload.validated_data)

        return success_response(
            ShipmentSerializer(shipment, context=self.get_serializer_context()).data,
            message="Shipment recorded.",
            status=status.HTTP_201_CREATED,
        )
