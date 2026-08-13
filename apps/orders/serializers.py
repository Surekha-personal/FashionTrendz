"""Order serializers.

Five shapes, matching the five surfaces: checkout context, order summary
(history list), order detail, invoice and shipment.

Order lines serialise from their **snapshot columns**, never through the
product foreign key. That is what makes a two-year-old order render correctly
after the product was renamed, repriced or deleted.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.cart.serializers import CartSerializer, CartSummarySerializer
from apps.core.choices import PaymentMethod
from apps.orders.models import (
    DeliveryMethod,
    Order,
    OrderItem,
    OrderStatusHistory,
    Shipment,
)
from apps.users.serializers import AddressSerializer


class AddressSnapshotSerializer(serializers.Serializer):
    """A frozen address as stored on an order."""

    full_name = serializers.CharField(read_only=True)
    mobile = serializers.CharField(read_only=True)
    address_line_1 = serializers.CharField(read_only=True)
    address_line_2 = serializers.CharField(read_only=True, allow_blank=True)
    city = serializers.CharField(read_only=True)
    state = serializers.CharField(read_only=True)
    country = serializers.CharField(read_only=True)
    postal_code = serializers.CharField(read_only=True)


class OrderItemSerializer(serializers.ModelSerializer):
    """One purchased line, rendered entirely from its snapshot."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    variant_label = serializers.CharField(source="display_variant", read_only=True)
    can_reorder = serializers.BooleanField(read_only=True)

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product_name",
            "product_slug",
            "brand_name",
            "sku",
            "size",
            "color",
            "variant_label",
            "image_url",
            "mrp",
            "selling_price",
            "discount",
            "tax",
            "quantity",
            "subtotal",
            "grand_total",
            "can_reorder",
        )
        read_only_fields = fields


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    """One entry in the order timeline."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    changed_by = serializers.SerializerMethodField()
    at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = OrderStatusHistory
        fields = ("previous_status", "status", "status_display", "remarks", "changed_by", "at")
        read_only_fields = fields

    def get_changed_by(self, obj: OrderStatusHistory) -> str:
        """Return who made the change, without leaking a staff email."""
        if obj.changed_by_id is None:
            return "system"
        return "you" if obj.changed_by_id == obj.order.user_id else "Fashion Trendz"


class ShipmentSerializer(serializers.ModelSerializer):
    """One parcel."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    is_delivered = serializers.BooleanField(read_only=True)
    is_in_transit = serializers.BooleanField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Shipment
        fields = (
            "id",
            "courier_name",
            "tracking_number",
            "tracking_url",
            "dispatched_at",
            "expected_delivery_date",
            "delivered_at",
            "remarks",
            "is_delivered",
            "is_in_transit",
            "is_overdue",
        )
        read_only_fields = fields


class OrderSummarySerializer(serializers.ModelSerializer):
    """One row of the order-history list.

    Carries a thumbnail and item count rather than the full line array, so the
    history page stays small even for a customer with hundreds of orders.
    """

    id = serializers.UUIDField(source="uuid", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_status_display = serializers.CharField(
        source="get_payment_status_display", read_only=True
    )
    item_count = serializers.IntegerField(source="line_count", read_only=True)
    unit_count = serializers.IntegerField(read_only=True)
    is_cancellable = serializers.BooleanField(read_only=True)
    preview_items = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "status",
            "status_display",
            "payment_status",
            "payment_status_display",
            "payment_method",
            "grand_total",
            "currency",
            "item_count",
            "unit_count",
            "preview_items",
            "estimated_delivery_date",
            "delivered_at",
            "is_cancellable",
            "created_at",
        )
        read_only_fields = fields

    def get_preview_items(self, obj: Order) -> list[dict[str, Any]]:
        """Return up to three lines, for the thumbnail strip on the card."""
        items = list(obj.items.all())[:3]
        return [
            {"product_name": item.product_name, "image_url": item.image_url}
            for item in items
        ]


class OrderDetailSerializer(serializers.ModelSerializer):
    """Everything the order detail page renders."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    shipments = ShipmentSerializer(many=True, read_only=True)

    shipping_address = AddressSnapshotSerializer(read_only=True)
    billing_address = AddressSnapshotSerializer(read_only=True)

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    delivery_status_display = serializers.CharField(
        source="get_delivery_status_display", read_only=True
    )
    payment_method_display = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )
    payment_status_display = serializers.CharField(
        source="get_payment_status_display", read_only=True
    )

    item_count = serializers.IntegerField(source="line_count", read_only=True)
    unit_count = serializers.IntegerField(read_only=True)
    total_savings = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    is_cancellable = serializers.BooleanField(read_only=True)
    has_invoice = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "invoice_number",
            "has_invoice",
            "status",
            "status_display",
            "delivery_status",
            "delivery_status_display",
            "delivery_method",
            "payment_method",
            "payment_method_display",
            "payment_status",
            "payment_status_display",
            "shipping_address",
            "billing_address",
            "items",
            "item_count",
            "unit_count",
            "subtotal",
            "discount",
            "coupon_code",
            "coupon_discount",
            "shipping_charge",
            "platform_fee",
            "tax",
            "grand_total",
            "total_savings",
            "currency",
            "estimated_delivery_date",
            "delivered_at",
            "cancelled_at",
            "cancel_reason",
            "notes",
            "is_cancellable",
            "status_history",
            "shipments",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_has_invoice(self, obj: Order) -> bool:
        """Return whether an invoice PDF has been generated yet."""
        return bool(obj.invoice_file)


class InvoiceSerializer(serializers.Serializer):
    """The invoice payload, for a client that renders its own document."""

    invoice_number = serializers.CharField(read_only=True)
    invoice_date = serializers.DateField(read_only=True)
    order_number = serializers.SerializerMethodField()
    customer_name = serializers.CharField(read_only=True)
    shipping_address = AddressSnapshotSerializer(read_only=True)
    billing_address = AddressSnapshotSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    coupon_discount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    shipping_charge = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    platform_fee = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    tax = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    grand_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    currency = serializers.CharField(read_only=True)
    payment_method = serializers.CharField(read_only=True)
    payment_status = serializers.CharField(read_only=True)

    def get_order_number(self, obj: dict[str, Any]) -> str:
        """Return the order number from the context dict."""
        return obj["order"].order_number


class TrackingSerializer(serializers.Serializer):
    """The order-tracking payload."""

    order_number = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(read_only=True)
    delivery_status = serializers.CharField(read_only=True)
    delivery_status_display = serializers.CharField(read_only=True)
    estimated_delivery_date = serializers.DateField(read_only=True, allow_null=True)
    delivered_at = serializers.DateTimeField(read_only=True, allow_null=True)
    courier_name = serializers.CharField(read_only=True, allow_blank=True)
    tracking_number = serializers.CharField(read_only=True, allow_blank=True)
    tracking_url = serializers.CharField(read_only=True, allow_blank=True)
    dispatched_at = serializers.DateTimeField(read_only=True, allow_null=True)
    timeline = serializers.ListField(child=serializers.DictField(), read_only=True)


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


class PaymentMethodOptionSerializer(serializers.Serializer):
    """One selectable payment method."""

    code = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    available = serializers.BooleanField(read_only=True)
    is_placeholder = serializers.BooleanField(read_only=True)


class DeliveryMethodOptionSerializer(serializers.Serializer):
    """One selectable delivery speed."""

    code = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)


class CheckoutContextSerializer(serializers.Serializer):
    """Everything the checkout page needs before an order exists."""

    cart = CartSerializer(read_only=True)
    summary = CartSummarySerializer(read_only=True)
    issues = serializers.ListField(child=serializers.DictField(), read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)
    default_address = AddressSerializer(read_only=True, allow_null=True)
    payment_methods = PaymentMethodOptionSerializer(many=True, read_only=True)
    delivery_methods = DeliveryMethodOptionSerializer(many=True, read_only=True)
    is_checkout_ready = serializers.BooleanField(read_only=True)


class OrderReviewSerializer(serializers.Serializer):
    """The exact order that would be created, before it is."""

    summary = CartSummarySerializer(read_only=True)
    shipping_address = AddressSnapshotSerializer(read_only=True)
    billing_address = AddressSnapshotSerializer(read_only=True)
    payment_method = serializers.CharField(read_only=True)
    delivery_method = serializers.CharField(read_only=True)
    estimated_delivery_date = serializers.DateField(read_only=True)
    issues = serializers.ListField(child=serializers.DictField(), read_only=True)


class PlaceOrderSerializer(serializers.Serializer):
    """Payload for placing an order.

    Addresses are resolved against the requesting user inside the service, so a
    guessed identifier yields "not found" rather than a stranger's doorstep.
    """

    shipping_address = serializers.IntegerField(
        help_text="Id of a saved delivery address, as returned by /api/v1/addresses/."
    )
    billing_address = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Defaults to the shipping address when omitted.",
    )
    payment_method = serializers.ChoiceField(
        choices=PaymentMethod.choices, default=PaymentMethod.COD
    )
    delivery_method = serializers.ChoiceField(
        choices=DeliveryMethod.choices, default=DeliveryMethod.STANDARD
    )
    notes = serializers.CharField(
        required=False, allow_blank=True, max_length=1000, default=""
    )


class ReviewOrderSerializer(serializers.Serializer):
    """Payload for the review step. Same shape as placing, minus the notes."""

    shipping_address = serializers.IntegerField()
    billing_address = serializers.IntegerField(required=False, allow_null=True)
    payment_method = serializers.ChoiceField(
        choices=PaymentMethod.choices, default=PaymentMethod.COD
    )
    delivery_method = serializers.ChoiceField(
        choices=DeliveryMethod.choices, default=DeliveryMethod.STANDARD
    )


class CancelOrderSerializer(serializers.Serializer):
    """Payload for cancelling an order."""

    reason = serializers.CharField(
        max_length=255,
        min_length=5,
        help_text="Why the customer is cancelling. Feeds the cancellation report.",
    )


class ReturnRequestSerializer(serializers.Serializer):
    """Payload for requesting a return. Placeholder until the returns module."""

    reason = serializers.CharField(max_length=255, min_length=5)


class ReorderResultSerializer(serializers.Serializer):
    """What a reorder managed to add, and what it could not."""

    added = serializers.ListField(child=serializers.CharField(), read_only=True)
    skipped = serializers.ListField(child=serializers.DictField(), read_only=True)
    cart = CartSerializer(read_only=True)


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------


class OrderStatusUpdateSerializer(serializers.Serializer):
    """Payload for a staff-driven status change."""

    status = serializers.CharField()
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")


class ShipmentCreateSerializer(serializers.Serializer):
    """Payload for recording a dispatched parcel."""

    courier_name = serializers.CharField(max_length=100)
    tracking_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    tracking_url = serializers.URLField(required=False, allow_blank=True, default="")
    expected_delivery_date = serializers.DateField(required=False, allow_null=True)
    dispatch = serializers.BooleanField(default=True)
