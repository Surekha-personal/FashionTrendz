"""Cart serializers.

Three tiers, matching the three surfaces:

* **Compact** — the navbar badge and quick-view state.
* **Detailed** — the cart page: lines, money, saved items, blocking issues.
* **Checkout summary** — everything the checkout page needs, including the
  per-line problems that decide whether its button is enabled.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.cart.models import MAX_QUANTITY_PER_LINE, Cart, CartItem
from apps.products.serializers import ProductCardSerializer, ProductVariantSerializer


class CartItemSerializer(serializers.ModelSerializer):
    """One cart line, with its product, variant and money."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    product = ProductCardSerializer(read_only=True)
    variant = ProductVariantSerializer(read_only=True)
    added_at = serializers.DateTimeField(source="created_at", read_only=True)

    available_stock = serializers.IntegerField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    max_quantity = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = (
            "id",
            "product",
            "variant",
            "quantity",
            "unit_price",
            "unit_mrp",
            "discount",
            "tax",
            "subtotal",
            "total",
            "saved_for_later",
            "available_stock",
            "is_available",
            "max_quantity",
            "added_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_max_quantity(self, obj: CartItem) -> int:
        """Return the highest quantity the stepper may offer.

        The lower of the purchase limit and what is actually in stock, so the
        control cannot propose a quantity the next request would reject.
        """
        return max(min(MAX_QUANTITY_PER_LINE, obj.variant.available_stock), 0)


class CartSummarySerializer(serializers.Serializer):
    """The price breakdown shown on the cart and checkout pages."""

    currency = serializers.CharField(read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    unit_count = serializers.IntegerField(read_only=True)

    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    coupon_code = serializers.CharField(read_only=True, allow_blank=True)
    coupon_discount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    tax = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    shipping = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    free_shipping_threshold = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    amount_to_free_shipping = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    platform_fee = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    grand_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    total_savings = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    estimated_delivery_days = serializers.IntegerField(read_only=True)


class CartIssueSerializer(serializers.Serializer):
    """One reason a line cannot be checked out."""

    variant_sku = serializers.CharField(read_only=True)
    product = serializers.CharField(read_only=True)
    reason = serializers.CharField(read_only=True)
    requested = serializers.IntegerField(read_only=True)
    available = serializers.IntegerField(read_only=True)


class CartSerializer(serializers.ModelSerializer):
    """The full cart page payload."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    items = serializers.SerializerMethodField()
    saved_items = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    issues = serializers.SerializerMethodField()
    is_guest = serializers.BooleanField(read_only=True)

    class Meta:
        model = Cart
        fields = (
            "id",
            "is_guest",
            "currency",
            "coupon_code",
            "items",
            "saved_items",
            "summary",
            "issues",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def _lines(self, obj: Cart, saved: bool) -> list[CartItem]:
        """Split the prefetched lines without issuing another query.

        ``with_items()`` already loaded every line; filtering in Python here
        keeps the bag and the saved section to one query between them.
        """
        cached = obj.__dict__.get("_prefetched_objects_cache", {}).get("items")
        lines = list(cached) if cached is not None else list(obj.items.all())
        return [line for line in lines if line.saved_for_later is saved]

    def get_items(self, obj: Cart) -> list[dict[str, Any]]:
        """Return the lines in the bag."""
        return CartItemSerializer(
            self._lines(obj, saved=False), many=True, context=self.context
        ).data

    def get_saved_items(self, obj: Cart) -> list[dict[str, Any]]:
        """Return the saved-for-later lines."""
        return CartItemSerializer(
            self._lines(obj, saved=True), many=True, context=self.context
        ).data

    def get_summary(self, obj: Cart) -> dict[str, Any]:
        """Return the price breakdown."""
        from apps.cart.services import get_cart_summary

        return CartSummarySerializer(get_cart_summary(obj)).data

    def get_issues(self, obj: Cart) -> list[dict[str, Any]]:
        """Return anything blocking checkout."""
        from apps.cart.services import get_cart_issues

        return CartIssueSerializer(get_cart_issues(obj), many=True).data


class CartCompactSerializer(serializers.Serializer):
    """Navbar badge payload. Deliberately tiny — it is fetched on every page."""

    count = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)


class CheckoutSummarySerializer(serializers.Serializer):
    """Everything the checkout page needs, in one payload."""

    cart = CartSerializer(read_only=True)
    summary = CartSummarySerializer(read_only=True)
    issues = CartIssueSerializer(many=True, read_only=True)
    is_checkout_ready = serializers.BooleanField(read_only=True)


# ---------------------------------------------------------------------------
# Request payloads
# ---------------------------------------------------------------------------


class AddToCartSerializer(serializers.Serializer):
    """Payload for adding units of a variant."""

    product = serializers.SlugField(help_text="Product slug.")
    variant = serializers.CharField(help_text="Variant SKU (colour and size).")
    quantity = serializers.IntegerField(
        min_value=1, max_value=MAX_QUANTITY_PER_LINE, default=1
    )


class UpdateQuantitySerializer(serializers.Serializer):
    """Payload for setting a line's quantity outright.

    Zero is allowed and removes the line, so the stepper needs no special case
    at its lower bound.
    """

    variant = serializers.CharField()
    quantity = serializers.IntegerField(min_value=0, max_value=MAX_QUANTITY_PER_LINE)


class ChangeQuantitySerializer(serializers.Serializer):
    """Payload for the +/- stepper buttons."""

    variant = serializers.CharField()
    delta = serializers.IntegerField(min_value=-MAX_QUANTITY_PER_LINE, max_value=MAX_QUANTITY_PER_LINE)


class CartLineSerializer(serializers.Serializer):
    """Payload for any action addressing a single existing line."""

    variant = serializers.CharField()


class CouponSerializer(serializers.Serializer):
    """Payload for applying a coupon code. Validation lands with the coupon module."""

    code = serializers.CharField(max_length=40)


class MergeCartSerializer(serializers.Serializer):
    """Payload for folding a guest cart into the signed-in customer's cart."""

    session_key = serializers.CharField(
        max_length=64,
        help_text="The guest session key held by the client before sign-in.",
    )
