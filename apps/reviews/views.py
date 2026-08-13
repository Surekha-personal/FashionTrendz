"""Review API views. Thin by construction — decisions live in services."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.pagination import StandardPagination
from apps.core.responses import success_response
from apps.products.models import Product
from apps.reviews import services
from apps.reviews.models import ModerationStatus, Review
from apps.reviews.permissions import IsReviewAuthor, IsReviewModerator
from apps.reviews.serializers import (
    CanReviewSerializer,
    HelpfulVoteResultSerializer,
    ModerationActionSerializer,
    MyReviewSerializer,
    PendingReviewItemSerializer,
    RatingSummarySerializer,
    ReviewCreateSerializer,
    ReviewImageSerializer,
    ReviewModerationSerializer,
    ReviewSerializer,
    ReviewUpdateSerializer,
)


def _bool(value: Any) -> bool:
    """Read a query-string flag. Absent, "0", "false" and "" all mean False."""
    return str(value).lower() in {"1", "true", "yes"}


@extend_schema(tags=["Reviews"])
class ProductReviewViewSet(viewsets.GenericViewSet):
    """Public reads for one product's reviews, addressed by product slug."""

    permission_classes = [AllowAny]
    pagination_class = StandardPagination
    serializer_class = ReviewSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self) -> Any:
        """Return the filtered, sorted review list for the product in the URL."""
        rating = self.request.query_params.get("rating")
        return services.get_product_reviews(
            self.kwargs["slug"],
            user=self.request.user,
            rating=int(rating) if (rating or "").isdigit() else None,
            verified_only=_bool(self.request.query_params.get("verified")),
            with_images=_bool(self.request.query_params.get("with_images")),
            sort=self.request.query_params.get("sort", "newest"),
        )

    @extend_schema(
        summary="List a product's reviews",
        parameters=[
            OpenApiParameter("rating", int, description="Filter to one star rating."),
            OpenApiParameter("verified", bool, description="Verified purchases only."),
            OpenApiParameter("with_images", bool, description="Reviews with photos."),
            OpenApiParameter(
                "sort",
                str,
                description="newest | oldest | most_helpful",
            ),
        ],
        responses={200: ReviewSerializer(many=True)},
    )
    def list(self, request: Request, slug: str) -> Response:
        """Return approved reviews for one product."""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(
            page if page is not None else queryset, many=True
        )
        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Reviews retrieved."
            return response
        return success_response(serializer.data, message="Reviews retrieved.")

    @extend_schema(
        summary="Rating summary and star distribution",
        responses={200: RatingSummarySerializer},
    )
    @action(detail=False, methods=["get"])
    def summary(self, request: Request, slug: str) -> Response:
        """Return the average, counts and per-star breakdown."""
        product = get_object_or_404(Product, slug=slug)
        payload = services.get_rating_summary(product)
        return success_response(
            RatingSummarySerializer(payload).data, message="Rating summary retrieved."
        )

    @extend_schema(
        summary="Customer photo gallery",
        responses={200: ReviewImageSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def gallery(self, request: Request, slug: str) -> Response:
        """Return photographs attached to approved reviews of this product."""
        images = services.get_product_gallery(slug)
        return success_response(
            ReviewImageSerializer(images, many=True, context={"request": request}).data,
            message="Review photos retrieved.",
        )

    @extend_schema(
        summary="May I review this product?",
        responses={200: CanReviewSerializer},
    )
    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def eligibility(self, request: Request, slug: str) -> Response:
        """Report whether the caller may review, and against which purchase."""
        product = get_object_or_404(Product, slug=slug)
        payload = services.can_review_product(request.user, product)
        return success_response(
            CanReviewSerializer(payload).data, message="Eligibility checked."
        )


@extend_schema(tags=["Reviews"])
class ReviewViewSet(viewsets.GenericViewSet):
    """Write and manage the signed-in customer's own reviews."""

    permission_classes = [IsAuthenticated, IsReviewAuthor]
    pagination_class = StandardPagination
    serializer_class = MyReviewSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    def get_queryset(self) -> Any:
        """Return every review the caller has written, any status."""
        return services.get_user_reviews(self.request.user)

    @extend_schema(
        summary="List my reviews", responses={200: MyReviewSerializer(many=True)}
    )
    def list(self, request: Request) -> Response:
        """Return the caller's reviews, including pending and rejected ones."""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(
            page if page is not None else queryset, many=True
        )
        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Your reviews retrieved."
            return response
        return success_response(serializer.data, message="Your reviews retrieved.")

    @extend_schema(
        summary="Write a review",
        request=ReviewCreateSerializer,
        responses={201: MyReviewSerializer},
    )
    def create(self, request: Request) -> Response:
        """Record a review against a delivered purchase."""
        payload = ReviewCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        review = services.create_review(
            user=request.user,
            order_item_id=payload.validated_data["order_item"],
            rating=payload.validated_data["rating"],
            title=payload.validated_data.get("title", ""),
            body=payload.validated_data.get("body", ""),
            images=payload.validated_data.get("images", []),
        )
        return success_response(
            MyReviewSerializer(review, context={"request": request}).data,
            message="Thanks — your review has been submitted.",
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Edit my review",
        request=ReviewUpdateSerializer,
        responses={200: MyReviewSerializer},
    )
    def partial_update(self, request: Request, uuid: str) -> Response:
        """Amend a review. Edits return it to the moderation queue."""
        review = self.get_object()
        payload = ReviewUpdateSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)

        review = services.update_review(
            review,
            rating=payload.validated_data.get("rating"),
            title=payload.validated_data.get("title"),
            body=payload.validated_data.get("body"),
            images=payload.validated_data.get("images"),
        )
        return success_response(
            MyReviewSerializer(review, context={"request": request}).data,
            message="Review updated.",
        )

    @extend_schema(summary="Delete my review", responses={200: None})
    def destroy(self, request: Request, uuid: str) -> Response:
        """Remove a review and refresh the product's rating."""
        services.delete_review(self.get_object())
        return success_response(None, message="Review deleted.")

    @extend_schema(
        summary="Purchases awaiting a review",
        responses={200: PendingReviewItemSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="pending")
    def pending(self, request: Request) -> Response:
        """Return delivered lines the customer has not reviewed yet."""
        items = services.reviewable_order_items(request.user)
        return success_response(
            PendingReviewItemSerializer(items, many=True).data,
            message="Pending reviews retrieved.",
        )

    @extend_schema(
        summary="Toggle helpful", responses={200: HelpfulVoteResultSerializer}
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="helpful",
        permission_classes=[IsAuthenticated],
    )
    def helpful(self, request: Request, uuid: str) -> Response:
        """Mark a review helpful, or take the vote back."""
        review = get_object_or_404(Review.objects.approved(), uuid=uuid)
        result = services.toggle_helpful(review, request.user)
        return success_response(
            HelpfulVoteResultSerializer(result).data,
            message="Thanks for the feedback." if result["voted"] else "Vote removed.",
        )


@extend_schema(tags=["Reviews — Admin"])
class ReviewModerationViewSet(viewsets.GenericViewSet):
    """Staff moderation queue and actions."""

    permission_classes = [IsReviewModerator]
    pagination_class = StandardPagination
    serializer_class = ReviewModerationSerializer

    def get_queryset(self) -> Any:
        """Return reviews filtered by ``?status=``, defaulting to the queue."""
        wanted = self.request.query_params.get("status", ModerationStatus.PENDING)
        queryset = Review.objects.with_detail()
        if wanted in ModerationStatus.values:
            queryset = queryset.filter(status=wanted)
        return queryset.order_by("created_at")

    @extend_schema(
        summary="Moderation queue",
        parameters=[
            OpenApiParameter("status", str, description="pending | approved | rejected")
        ],
        responses={200: ReviewModerationSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        """Return reviews awaiting a decision, oldest first."""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(
            page if page is not None else queryset, many=True
        )
        if page is not None:
            response = self.get_paginated_response(serializer.data)
            response.message = "Moderation queue retrieved."
            return response
        return success_response(serializer.data, message="Moderation queue retrieved.")

    @extend_schema(
        summary="Approve or reject reviews",
        request=ModerationActionSerializer,
        responses={200: ModerationActionSerializer},
    )
    @action(detail=False, methods=["post"])
    def moderate(self, request: Request) -> Response:
        """Act on one review or a batch of them.

        One endpoint for both: the bulk path is the single path with a longer
        id list, and a separate single-review route would duplicate every rule.
        """
        payload = ModerationActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        ids = payload.validated_data.get("review_ids") or []
        queryset = Review.objects.filter(pk__in=ids)
        count = services.bulk_moderate(
            queryset,
            moderator=request.user,
            status=payload.validated_data["status"],
            reason=payload.validated_data.get("reason", ""),
        )
        return success_response(
            {"updated": count, "status": payload.validated_data["status"]},
            message=f"{count} review(s) updated.",
        )
