"""Coupon serializers."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.coupons.models import Coupon, CouponUsage, DiscountType


class CouponSerializer(serializers.ModelSerializer):
    """A coupon as the storefront's offers strip shows it.

    ``max_uses`` and ``times_used`` are deliberately absent. Telling a customer
    "3 of 500 remaining" turns a discount into a countdown, and telling a
    competitor how a campaign is performing is nobody's intention.
    """

    id = serializers.UUIDField(source="uuid", read_only=True)
    type = serializers.CharField(source="discount_type", read_only=True)
    display_value = serializers.CharField(read_only=True)

    class Meta:
        model = Coupon
        fields = (
            "id",
            "code",
            "description",
            "type",
            "value",
            "display_value",
            "max_discount",
            "min_cart_value",
            "currency",
            "valid_from",
            "valid_until",
            "first_order_only",
        )
        read_only_fields = fields


class CouponAdminSerializer(serializers.ModelSerializer):
    """Writable coupon representation for staff."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    times_used = serializers.IntegerField(read_only=True)
    remaining_uses = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Coupon
        fields = (
            "id",
            "code",
            "description",
            "discount_type",
            "value",
            "max_discount",
            "min_cart_value",
            "currency",
            "max_uses",
            "uses_per_user",
            "times_used",
            "remaining_uses",
            "valid_from",
            "valid_until",
            "is_active",
            "is_public",
            "first_order_only",
            "categories",
            "brands",
            "products",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "times_used", "remaining_uses", "created_at", "updated_at")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Check the discount shape and the validity window.

        The database enforces the window ordering too, but a check constraint
        reports a generic 409; naming the field gives the admin form something
        to highlight.
        """
        discount_type = attrs.get(
            "discount_type", getattr(self.instance, "discount_type", None)
        )
        value = attrs.get("value", getattr(self.instance, "value", None))

        if discount_type == DiscountType.PERCENTAGE and value is not None:
            if value <= 0 or value > 100:
                raise serializers.ValidationError(
                    {"value": "A percentage discount must be between 0 and 100."}
                )
            if not attrs.get("max_discount", getattr(self.instance, "max_discount", None)):
                # Not fatal, but worth refusing by default: an uncapped
                # percentage coupon on a luxury catalogue is a blank cheque.
                raise serializers.ValidationError(
                    {
                        "max_discount": (
                            "Set a maximum discount for percentage coupons, or the "
                            "cap is unbounded on high-value items."
                        )
                    }
                )

        if discount_type == DiscountType.FLAT and value is not None and value <= 0:
            raise serializers.ValidationError(
                {"value": "A flat discount must be greater than zero."}
            )

        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_until = attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        if valid_from and valid_until and valid_until <= valid_from:
            raise serializers.ValidationError(
                {"valid_until": "The end date must be after the start date."}
            )

        return attrs


class CouponUsageSerializer(serializers.ModelSerializer):
    """One redemption, for the customer's offer history."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    code = serializers.CharField(source="coupon.code", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True, default="")
    used_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = CouponUsage
        fields = ("id", "code", "order_number", "discount_amount", "is_released", "used_at")
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Request payloads
# ---------------------------------------------------------------------------


class ApplyCouponSerializer(serializers.Serializer):
    """Payload for applying or previewing a coupon."""

    code = serializers.CharField(max_length=40)

    def validate_code(self, value: str) -> str:
        """Normalise the typed code to its canonical form."""
        return (value or "").strip().upper()


class CouponResultSerializer(serializers.Serializer):
    """The outcome of applying, previewing or removing a coupon."""

    code = serializers.CharField(read_only=True, allow_blank=True)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    applied = serializers.BooleanField(read_only=True)
    free_shipping = serializers.BooleanField(read_only=True, required=False)
    message = serializers.CharField(read_only=True)
