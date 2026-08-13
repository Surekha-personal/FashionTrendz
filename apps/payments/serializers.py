"""Payment serializers.

Customer-facing payloads deliberately omit ``raw_response``, ``gateway_signature``
and the webhook headers. They are stored for disputes and debugging, not for
display, and a raw gateway body can contain card metadata that has no business
crossing the API boundary.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.payments.models import (
    Payment,
    PaymentAttempt,
    PaymentWebhookLog,
    Refund,
    RefundReason,
)


class PaymentAttemptSerializer(serializers.ModelSerializer):
    """One try within a payment intent."""

    class Meta:
        model = PaymentAttempt
        fields = ("attempt_number", "status", "failure_reason", "retry_count", "created_at")
        read_only_fields = fields


class RefundSerializer(serializers.ModelSerializer):
    """One refund, as the customer sees it."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    order_number = serializers.CharField(
        source="payment.order.order_number", read_only=True
    )
    is_partial = serializers.BooleanField(read_only=True)

    class Meta:
        model = Refund
        fields = (
            "id",
            "order_number",
            "amount",
            "currency",
            "status",
            "status_display",
            "reason",
            "reason_display",
            "reference_number",
            "is_partial",
            "processed_at",
            "created_at",
        )
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    """One payment, as the customer sees it."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    refundable_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    refunds = RefundSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "order_number",
            "gateway",
            "method",
            "amount",
            "refunded_amount",
            "refundable_amount",
            "currency",
            "status",
            "status_display",
            "transaction_id",
            "reference_number",
            "failure_reason",
            "captured_at",
            "refunds",
            "created_at",
        )
        read_only_fields = fields


class PaymentAdminSerializer(PaymentSerializer):
    """Staff view, adding the gateway identifiers and attempt history."""

    attempts = PaymentAttemptSerializer(many=True, read_only=True)

    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields + (
            "gateway_order_id",
            "gateway_payment_id",
            "attempts",
            "updated_at",
        )
        read_only_fields = fields


class WebhookLogSerializer(serializers.ModelSerializer):
    """One received webhook, for the staff audit view."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    is_processed = serializers.BooleanField(read_only=True)

    class Meta:
        model = PaymentWebhookLog
        fields = (
            "id",
            "gateway",
            "event_id",
            "event_type",
            "is_verified",
            "is_duplicate",
            "is_processed",
            "processed_at",
            "error",
            "created_at",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Request payloads
# ---------------------------------------------------------------------------


class CreatePaymentSerializer(serializers.Serializer):
    """Payload for opening a payment intent."""

    order_number = serializers.CharField(max_length=32)
    gateway = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        help_text="Defaults to the order's chosen payment method.",
    )


class CreatePaymentResultSerializer(serializers.Serializer):
    """What the browser needs to open the gateway widget."""

    payment = PaymentSerializer(read_only=True)
    gateway = serializers.CharField(read_only=True)
    is_offline = serializers.BooleanField(read_only=True)
    checkout = serializers.DictField(read_only=True)


class VerifyPaymentSerializer(serializers.Serializer):
    """Payload the browser returns after the gateway widget closes.

    Field names match Razorpay's callback verbatim so the frontend can forward
    its response unchanged. ``gateway_order_id`` is the neutral alias other
    providers and the COD flow use.
    """

    razorpay_order_id = serializers.CharField(required=False, allow_blank=True)
    razorpay_payment_id = serializers.CharField(required=False, allow_blank=True)
    razorpay_signature = serializers.CharField(required=False, allow_blank=True)
    gateway_order_id = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Require some reference to the payment being verified."""
        if not (attrs.get("razorpay_order_id") or attrs.get("gateway_order_id")):
            raise serializers.ValidationError(
                {"gateway_order_id": "A gateway order reference is required."}
            )
        return attrs


class CreateRefundSerializer(serializers.Serializer):
    """Payload for issuing a refund. Staff only."""

    order_number = serializers.CharField(max_length=32)
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Omit to refund everything still refundable.",
    )
    reason = serializers.ChoiceField(
        choices=RefundReason.choices, default=RefundReason.OTHER
    )
    notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
