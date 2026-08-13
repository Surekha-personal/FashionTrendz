"""Payment API views. Thin by construction.

The webhook endpoint is the one that needs care: it is unauthenticated, CSRF
exempt, and must read ``request.body`` raw. Re-serialising the parsed JSON
changes byte order and whitespace, and the HMAC then never matches — which
looks exactly like a wrong secret and wastes an afternoon.
"""

from __future__ import annotations

from typing import Any

from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleViolation
from apps.core.pagination import StandardPagination
from apps.core.responses import success_response
from apps.core.throttling import CheckoutThrottle
from apps.orders.services import get_order
from apps.payments import services
from apps.payments.gateways import available_gateways, get_gateway
from apps.payments.models import Payment, Refund
from apps.payments.permissions import IsAdmin, WebhookPermission
from apps.payments.serializers import (
    CreatePaymentResultSerializer,
    CreatePaymentSerializer,
    CreateRefundSerializer,
    PaymentAdminSerializer,
    PaymentSerializer,
    RefundSerializer,
    VerifyPaymentSerializer,
)


@extend_schema(tags=["Payments"])
class PaymentViewSet(viewsets.GenericViewSet):
    """Creating, verifying and listing payments."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    serializer_class = PaymentSerializer

    @property
    def is_staff(self) -> bool:
        """Return whether the caller may see other customers' payments."""
        user = getattr(self.request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)

    def get_queryset(self) -> Any:
        """Return payments visible to the caller."""
        if self.is_staff:
            return Payment.objects.with_detail().order_by("-created_at")
        return services.get_payments(self.request.user)

    @extend_schema(summary="My payments", responses={200: PaymentSerializer(many=True)})
    def list(self, request: Request) -> Response:
        """Return the caller's payment history."""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer_class = PaymentAdminSerializer if self.is_staff else PaymentSerializer
        serializer = serializer_class(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Your payments."
            return response
        return success_response(serializer.data, message="Your payments.")

    @extend_schema(
        summary="Open a payment",
        description=(
            "Creates a payment intent for an order and returns the payload the "
            "gateway's browser SDK needs. Offline methods return an empty "
            "checkout object, which tells the client to skip the widget."
        ),
        request=CreatePaymentSerializer,
        responses={201: CreatePaymentResultSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="create",
        url_name="create",
        throttle_classes=[CheckoutThrottle],
        pagination_class=None,
    )
    # Named ``create_payment`` rather than ``create``: ``create`` is a route
    # method name the router reserves. The URL and reverse name are pinned so
    # the route still reads /api/v1/payments/create/ as specified.
    def create_payment(self, request: Request) -> Response:
        """Open a payment intent for an order."""
        payload = CreatePaymentSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        order = get_order(
            request.user, payload.validated_data["order_number"], staff=self.is_staff
        )
        payment = services.create_payment(
            order, payload.validated_data.get("gateway") or None
        )
        gateway = get_gateway(payment.gateway)

        return success_response(
            {
                "payment": PaymentSerializer(
                    payment, context=self.get_serializer_context()
                ).data,
                "gateway": payment.gateway,
                "is_offline": gateway.is_offline,
                "checkout": services.get_checkout_payload(payment),
            },
            message="Payment initiated.",
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Verify a payment",
        description=(
            "Verifies the gateway's signature, confirms the payment with the "
            "provider and checks the amount against the order before marking "
            "anything paid."
        ),
        request=VerifyPaymentSerializer,
        responses={200: PaymentSerializer},
    )
    @action(detail=False, methods=["post"], pagination_class=None)
    def verify(self, request: Request) -> Response:
        """Verify a completed payment."""
        payload = VerifyPaymentSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        payment = services.verify_payment(payload.validated_data, user=request.user)
        data = PaymentSerializer(payment, context=self.get_serializer_context()).data

        if payment.status != "captured":
            # A 402 rather than a 400: the request was well-formed, the payment
            # simply did not go through, and the client should offer a retry.
            return Response(
                {
                    "success": False,
                    "message": payment.failure_reason or "Payment could not be verified.",
                    "errors": {"payment": [payment.failure_reason or "Payment failed."]},
                    "data": data,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        return success_response(data, message="Payment successful.")

    @extend_schema(
        summary="Available gateways",
        description="Which providers are configured and which are placeholders.",
    )
    @action(detail=False, methods=["get"], permission_classes=[AllowAny], pagination_class=None)
    def gateways(self, request: Request) -> Response:
        """Return the gateways the checkout page may offer."""
        return success_response(
            {"gateways": available_gateways()}, message="Payment gateways."
        )

    @extend_schema(
        summary="Issue a refund (staff)",
        request=CreateRefundSerializer,
        responses={201: RefundSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAdmin],
        pagination_class=None,
    )
    def refund(self, request: Request) -> Response:
        """Refund all or part of an order's payment."""
        payload = CreateRefundSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        order = get_order(request.user, payload.validated_data["order_number"], staff=True)
        refund = services.refund_order(
            order,
            amount=payload.validated_data.get("amount"),
            reason=payload.validated_data["reason"],
            notes=payload.validated_data.get("notes", ""),
            initiated_by=request.user,
        )

        return success_response(
            RefundSerializer(refund, context=self.get_serializer_context()).data,
            message=f"Refund of {refund.currency} {refund.amount} initiated.",
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["Payments: Webhooks"])
class WebhookViewSet(viewsets.GenericViewSet):
    """Gateway webhook receiver.

    Unauthenticated and CSRF exempt on purpose: gateways call from rotating IP
    ranges with no credential we issued. The HMAC signature over the raw body
    *is* the authentication, and it is checked before anything is written.
    """

    permission_classes = [WebhookPermission]
    authentication_classes: list[Any] = []
    pagination_class = None
    serializer_class = None

    @extend_schema(
        summary="Receive a gateway webhook",
        parameters=[
            OpenApiParameter(
                name="gateway",
                location=OpenApiParameter.PATH,
                description="Registry key of the sending gateway, e.g. razorpay.",
                type=str,
            )
        ],
        request=None,
        responses={200: None},
    )
    @action(detail=False, methods=["post"], url_path=r"(?P<gateway>[a-z]+)")
    def receive(self, request: Request, gateway: str | None = None) -> Response:
        """Verify, log and apply one webhook.

        Always answers 200 for a verified event — including duplicates and
        events this integration does not handle. Anything else makes the
        provider retry for hours over something that is not a failure.
        """
        headers = {
            key.replace("HTTP_", "").replace("_", "-").title(): value
            for key, value in request.META.items()
            if key.startswith("HTTP_")
        }

        result = services.handle_webhook(gateway or "", request.body, headers)
        return Response({"success": True, **result}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="My refunds", tags=["Payments"]),
)
class RefundViewSet(viewsets.GenericViewSet):
    """A customer's refunds."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    serializer_class = RefundSerializer

    @property
    def is_staff(self) -> bool:
        """Return whether the caller may see other customers' refunds."""
        user = getattr(self.request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)

    def get_queryset(self) -> Any:
        """Return refunds visible to the caller."""
        if self.is_staff:
            return Refund.objects.with_order().order_by("-created_at")
        return services.get_refunds(self.request.user)

    def list(self, request: Request) -> Response:
        """Return the caller's refund history."""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)

        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Your refunds."
            return response
        return success_response(serializer.data, message="Your refunds.")
