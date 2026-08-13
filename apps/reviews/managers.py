"""Querysets and managers for the reviews module."""

from __future__ import annotations

from django.db import models
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.utils import timezone


class ReviewQuerySet(models.QuerySet):
    """Queries over reviews."""

    def approved(self) -> "ReviewQuerySet":
        """Restrict to reviews a shopper may see.

        The default for every public read. An unmoderated review feed is how a
        product page ends up displaying spam, abuse or a competitor's link to
        every visitor before anyone notices.
        """
        from apps.reviews.models import ModerationStatus

        return self.filter(status=ModerationStatus.APPROVED)

    def pending(self) -> "ReviewQuerySet":
        """Restrict to reviews awaiting moderation — the moderator's queue."""
        from apps.reviews.models import ModerationStatus

        return self.filter(status=ModerationStatus.PENDING)

    def rejected(self) -> "ReviewQuerySet":
        """Restrict to rejected reviews."""
        from apps.reviews.models import ModerationStatus

        return self.filter(status=ModerationStatus.REJECTED)

    def for_product(self, slug: str) -> "ReviewQuerySet":
        """Restrict to one product, addressed by slug."""
        return self.filter(product__slug=slug)

    def for_user(self, user: models.Model) -> "ReviewQuerySet":
        """Restrict to one customer's reviews."""
        return self.filter(user=user)

    def verified(self) -> "ReviewQuerySet":
        """Restrict to reviews backed by a real purchase."""
        return self.filter(is_verified_purchase=True)

    def with_images(self) -> "ReviewQuerySet":
        """Restrict to reviews carrying at least one photograph.

        ``Exists`` rather than ``annotate(Count(...)).filter(gt=0)``: the
        subquery stops at the first matching row instead of counting every
        image on every review.
        """
        from apps.reviews.models import ReviewImage

        return self.filter(
            Exists(ReviewImage.objects.filter(review=OuterRef("pk")))
        )

    def rated(self, stars: int) -> "ReviewQuerySet":
        """Restrict to one star rating."""
        return self.filter(rating=stars)

    def recent(self) -> "ReviewQuerySet":
        """Newest first."""
        return self.order_by("-created_at")

    def oldest(self) -> "ReviewQuerySet":
        """Oldest first."""
        return self.order_by("created_at")

    def most_helpful(self) -> "ReviewQuerySet":
        """Most upvoted first, newest breaking ties.

        Recency is the tiebreak rather than rating: two reviews with the same
        vote count are equally useful, and the newer one describes the product
        as it ships today.
        """
        return self.order_by("-helpful_count", "-created_at")

    def featured(self) -> "ReviewQuerySet":
        """The handful a product page shows above the fold.

        Verified, substantial and upvoted — in that order of preference. A
        two-word five-star review is not what convinces the next shopper.
        """
        return (
            self.approved()
            .verified()
            .exclude(body="")
            .order_by("-helpful_count", "-rating", "-created_at")
        )

    def with_detail(self) -> "ReviewQuerySet":
        """Load everything a review card renders."""
        from apps.reviews.models import ReviewImage

        return self.select_related("user", "product").prefetch_related(
            Prefetch(
                "images", queryset=ReviewImage.objects.order_by("display_order", "id")
            )
        )

    def voted_by(self, user: models.Model) -> "ReviewQuerySet":
        """Annotate whether ``user`` has already found each review helpful.

        One subquery for the whole page rather than one lookup per review,
        which is what lets the frontend render vote state without N+1.
        """
        from apps.reviews.models import HelpfulVote

        if not (user and user.is_authenticated):
            return self.annotate(
                has_voted=models.Value(False, output_field=models.BooleanField())
            )

        return self.annotate(
            has_voted=Exists(
                HelpfulVote.objects.filter(review=OuterRef("pk"), user=user)
            )
        )


class ReviewImageQuerySet(models.QuerySet):
    """Queries over review photographs."""

    def approved(self) -> "ReviewImageQuerySet":
        """Restrict to images on approved reviews.

        The customer photo gallery reads through this: an image attached to a
        rejected review must not surface on the product page just because the
        gallery queries images directly.
        """
        from apps.reviews.models import ModerationStatus

        return self.filter(review__status=ModerationStatus.APPROVED)

    def for_product(self, slug: str) -> "ReviewImageQuerySet":
        """Restrict to one product's customer photographs."""
        return self.filter(review__product__slug=slug)


ReviewManager = models.Manager.from_queryset(ReviewQuerySet)
ReviewImageManager = models.Manager.from_queryset(ReviewImageQuerySet)
