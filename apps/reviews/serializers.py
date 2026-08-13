"""Review serializers.

Read and write shapes are separate classes throughout. A single serializer
doing both ends up with half its fields read-only and a ``validate`` method
that has to guess which direction it is running in.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.orders.models import OrderItem
from apps.reviews.models import ModerationStatus, Review, ReviewImage
from apps.reviews.services import MAX_IMAGES_PER_REVIEW
from apps.reviews.validators import (
    MAX_REVIEW_LENGTH,
    validate_no_contact_details,
    validate_review_body,
    validate_review_image,
)


class ReviewImageSerializer(serializers.ModelSerializer):
    """One customer photograph."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    image = serializers.ImageField(read_only=True)
    thumbnail = serializers.ImageField(read_only=True)

    class Meta:
        model = ReviewImage
        fields = ("id", "image", "thumbnail", "caption", "display_order")
        read_only_fields = fields


class ReviewSerializer(serializers.ModelSerializer):
    """A review as it appears on a product page.

    ``user_name`` rather than a nested user object: the review list is public,
    and nesting the account would put an email address on every card.
    """

    id = serializers.UUIDField(source="uuid", read_only=True)
    user_name = serializers.CharField(source="author_name", read_only=True)
    images = ReviewImageSerializer(many=True, read_only=True)
    has_voted = serializers.BooleanField(read_only=True, default=False)
    product_slug = serializers.CharField(source="product.slug", read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "product_slug",
            "user_name",
            "rating",
            "title",
            "body",
            "is_verified_purchase",
            "helpful_count",
            "has_voted",
            "images",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class MyReviewSerializer(ReviewSerializer):
    """A review shown to its own author.

    Adds the moderation state. The author is the one person entitled to know
    that their review is held or why it was rejected.
    """

    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta(ReviewSerializer.Meta):
        fields = ReviewSerializer.Meta.fields + (
            "status",
            "status_display",
            "rejection_reason",
            "product_name",
        )
        read_only_fields = fields


class ReviewCreateSerializer(serializers.Serializer):
    """Payload for writing a review against a delivered purchase.

    ``order_item`` and not ``product``. The product is derived from the
    purchase in the service layer, so a client cannot point a genuine purchase
    at someone else's listing.
    """

    order_item = serializers.IntegerField(min_value=1)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    body = serializers.CharField(
        max_length=MAX_REVIEW_LENGTH,
        required=False,
        allow_blank=True,
        validators=[validate_review_body, validate_no_contact_details],
    )
    images = serializers.ListField(
        child=serializers.ImageField(validators=[validate_review_image]),
        required=False,
        allow_empty=True,
        max_length=MAX_IMAGES_PER_REVIEW,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Require a written review below four stars.

        A bare one-star rating tells the next shopper nothing and the merchant
        nothing. Praise needs no explanation; a complaint does.
        """
        if attrs["rating"] <= 3 and not (attrs.get("body") or "").strip():
            raise serializers.ValidationError(
                {"body": "Please tell us what went wrong so we can fix it."}
            )
        return attrs


class ReviewUpdateSerializer(serializers.Serializer):
    """Payload for amending an existing review. Every field optional."""

    rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    body = serializers.CharField(
        max_length=MAX_REVIEW_LENGTH,
        required=False,
        allow_blank=True,
        validators=[validate_review_body, validate_no_contact_details],
    )
    images = serializers.ListField(
        child=serializers.ImageField(validators=[validate_review_image]),
        required=False,
        allow_empty=True,
        max_length=MAX_IMAGES_PER_REVIEW,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Reject an empty patch rather than silently doing nothing."""
        if not attrs:
            raise serializers.ValidationError("Send at least one field to update.")
        return attrs


class StarBucketSerializer(serializers.Serializer):
    """One bar of the star-distribution chart."""

    stars = serializers.IntegerField(read_only=True)
    count = serializers.IntegerField(read_only=True)
    percentage = serializers.FloatField(read_only=True)


class RatingSummarySerializer(serializers.Serializer):
    """The rating block above a product's review list."""

    average = serializers.FloatField(read_only=True)
    count = serializers.IntegerField(read_only=True)
    verified_count = serializers.IntegerField(read_only=True)
    with_images_count = serializers.IntegerField(read_only=True)
    distribution = StarBucketSerializer(many=True, read_only=True)


class CanReviewSerializer(serializers.Serializer):
    """Whether the caller may review a product, and against which purchase."""

    can_review = serializers.BooleanField(read_only=True)
    reason = serializers.CharField(read_only=True, allow_blank=True)
    order_item = serializers.IntegerField(read_only=True, allow_null=True)


class HelpfulVoteResultSerializer(serializers.Serializer):
    """The state of the helpful button after a toggle."""

    voted = serializers.BooleanField(read_only=True)
    helpful_count = serializers.IntegerField(read_only=True)


class PendingReviewItemSerializer(serializers.ModelSerializer):
    """A delivered line the customer has not reviewed yet."""

    order_item = serializers.IntegerField(source="pk", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    delivered_at = serializers.DateTimeField(source="order.delivered_at", read_only=True)

    class Meta:
        model = OrderItem
        fields = (
            "order_item",
            "order_number",
            "delivered_at",
            "product_name",
            "product_slug",
            "brand_name",
            "size",
            "color",
            "image_url",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


class ReviewModerationSerializer(serializers.ModelSerializer):
    """A review as a moderator sees it: everything, including the author."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    images = ReviewImageSerializer(many=True, read_only=True)
    moderated_by_email = serializers.EmailField(
        source="moderated_by.email", read_only=True, allow_null=True
    )

    class Meta:
        model = Review
        fields = (
            "id",
            "pk",
            "product_name",
            "product_slug",
            "user_email",
            "rating",
            "title",
            "body",
            "is_verified_purchase",
            "status",
            "rejection_reason",
            "helpful_count",
            "images",
            "moderated_by_email",
            "moderated_at",
            "created_at",
        )
        read_only_fields = fields


class ModerationActionSerializer(serializers.Serializer):
    """Payload for approving or rejecting one or many reviews."""

    status = serializers.ChoiceField(
        choices=[ModerationStatus.APPROVED, ModerationStatus.REJECTED]
    )
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
    review_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=False,
        help_text="Omit for a single-review action; supply for bulk moderation.",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Require a reason when rejecting.

        The author sees this string. "Rejected" with no explanation generates a
        support ticket every time.
        """
        if attrs["status"] == ModerationStatus.REJECTED and not (
            attrs.get("reason") or ""
        ).strip():
            raise serializers.ValidationError(
                {"reason": "Give a reason so the customer knows what to change."}
            )
        return attrs
