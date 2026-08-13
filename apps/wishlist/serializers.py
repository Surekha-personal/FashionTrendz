"""Wishlist serializers.

The item serializer embeds :class:`apps.products.serializers.ProductCardSerializer`
verbatim, so a wishlist tile and a listing tile are byte-identical — the
frontend reuses one component for both.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.products.models import Product
from apps.products.serializers import ProductCardSerializer
from apps.wishlist.models import Wishlist, WishlistItem


class WishlistItemSerializer(serializers.ModelSerializer):
    """One saved product."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    product = ProductCardSerializer(read_only=True)
    added_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = WishlistItem
        fields = ("id", "product", "added_at")
        read_only_fields = fields


class WishlistSerializer(serializers.ModelSerializer):
    """The whole wishlist, for the wishlist page."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    items = WishlistItemSerializer(many=True, read_only=True)
    count = serializers.IntegerField(source="item_count", read_only=True)

    class Meta:
        model = Wishlist
        fields = ("id", "count", "items", "created_at", "updated_at")
        read_only_fields = fields


class WishlistActionSerializer(serializers.Serializer):
    """Payload for add, remove and toggle.

    Products are addressed by slug rather than id — the frontend routes on
    slugs and has no reason to hold internal primary keys.
    """

    product = serializers.SlugField(
        help_text="Slug of the product to add, remove or toggle."
    )

    def validate_product(self, value: str) -> str:
        """Reject a slug that matches no purchasable product."""
        if not Product.objects.visible().filter(slug=value).exists():
            raise serializers.ValidationError("This product is not available.")
        return value


class MoveToCartSerializer(serializers.Serializer):
    """Payload for moving a saved product into the cart.

    ``variant`` is required: a wishlist entry carries no size or colour, so the
    "move to bag" modal has to supply one.
    """

    product = serializers.SlugField()
    variant = serializers.CharField(
        help_text="SKU of the chosen colour/size variant."
    )
    quantity = serializers.IntegerField(min_value=1, default=1)


class WishlistCountSerializer(serializers.Serializer):
    """Navbar badge payload."""

    count = serializers.IntegerField(read_only=True)


class WishlistToggleResultSerializer(serializers.Serializer):
    """Result of a heart tap: the new state and the new badge count."""

    in_wishlist = serializers.BooleanField(read_only=True)
    count = serializers.IntegerField(read_only=True)
