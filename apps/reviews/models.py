"""Review models.

Three models: :class:`Review`, its :class:`ReviewImage` photographs, and a
:class:`HelpfulVote` per upvote.

The invariant the whole module exists to protect is **one review per purchased
line**. It is enforced by a unique constraint on ``order_item``, not by an
application check — a customer double-tapping "Submit" fires two requests, and
a check-then-insert loses that race every time.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalog.utils import UploadPath
from apps.core.choices import Rating
from apps.core.mixins import BaseModel
from apps.core.validators import validate_no_html
from apps.products.models import Product
from apps.reviews.managers import ReviewImageManager, ReviewManager
from apps.reviews.validators import (
    MAX_REVIEW_LENGTH,
    validate_no_contact_details,
    validate_review_body,
    validate_review_image,
)

review_image_path = UploadPath("reviews/images")
review_thumbnail_path = UploadPath("reviews/thumbnails")


class ModerationStatus(models.TextChoices):
    """Where a review sits in the moderation queue.

    Three states rather than a pair of booleans. ``approved`` and ``rejected``
    as separate flags allow the meaningless "both true" and the ambiguous
    "both false", and every read then has to decide which it meant.
    """

    PENDING = "pending", _("Pending review")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")


class Review(BaseModel):
    """One customer's verdict on one product they bought."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("product"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("customer"),
    )

    # The purchase this review is attached to. Nullable so a review survives
    # an order being purged, but required at creation: it is what proves the
    # reviewer actually owns the product.
    order_item = models.OneToOneField(
        "orders.OrderItem",
        on_delete=models.SET_NULL,
        related_name="review",
        null=True,
        blank=True,
        verbose_name=_("purchased line"),
    )

    rating = models.PositiveSmallIntegerField(
        _("rating"), choices=Rating.choices, db_index=True
    )
    title = models.CharField(
        _("title"), max_length=120, blank=True, validators=[validate_no_html]
    )
    body = models.TextField(
        _("review"),
        max_length=MAX_REVIEW_LENGTH,
        blank=True,
        validators=[validate_review_body, validate_no_contact_details, validate_no_html],
    )

    is_verified_purchase = models.BooleanField(
        _("verified purchase"),
        default=False,
        db_index=True,
        help_text=_("True when the review is backed by a delivered order line."),
    )

    status = models.CharField(
        _("moderation status"),
        max_length=12,
        choices=ModerationStatus.choices,
        default=ModerationStatus.PENDING,
        db_index=True,
    )
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="moderated_reviews",
        null=True,
        blank=True,
        verbose_name=_("moderated by"),
    )
    moderated_at = models.DateTimeField(_("moderated at"), null=True, blank=True)
    rejection_reason = models.CharField(
        _("rejection reason"), max_length=255, blank=True
    )

    helpful_count = models.PositiveIntegerField(
        _("helpful votes"),
        default=0,
        db_index=True,
        editable=False,
        help_text=_("Denormalised vote count, maintained by the service layer."),
    )

    objects = ReviewManager()

    class Meta:
        verbose_name = _("review")
        verbose_name_plural = _("reviews")
        ordering = ["-created_at"]
        constraints = [
            # One review per purchased line. A customer who bought the same
            # dress twice may review it twice — two lines, two opinions — but
            # cannot review one purchase repeatedly to inflate its rating.
            models.UniqueConstraint(
                fields=["order_item"],
                condition=models.Q(order_item__isnull=False),
                name="unique_review_per_order_item",
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="review_rating_within_range",
            ),
        ]
        indexes = [
            # The product page's read: approved reviews for one product,
            # newest first.
            models.Index(
                fields=["product", "status", "-created_at"], name="review_product_idx"
            ),
            models.Index(
                fields=["product", "status", "-helpful_count"],
                name="review_helpful_idx",
            ),
            models.Index(fields=["user", "-created_at"], name="review_user_idx"),
            models.Index(fields=["status", "-created_at"], name="review_queue_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.rating}★ on {self.product.name} by {self.user.email}"

    # -- Derived state ------------------------------------------------------

    @property
    def is_approved(self) -> bool:
        """Return whether this review is publicly visible."""
        return self.status == ModerationStatus.APPROVED

    @property
    def is_pending(self) -> bool:
        """Return whether this review is still awaiting moderation."""
        return self.status == ModerationStatus.PENDING

    @property
    def has_images(self) -> bool:
        """Return whether the customer attached photographs."""
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("images")
        if prefetched is not None:
            return bool(prefetched)
        return self.images.exists()

    @property
    def author_name(self) -> str:
        """Return the display name shown against the review.

        First name and a surname initial — "Aditi S." Reviews are public, and
        publishing a customer's full name next to their purchase history is
        more than they agreed to when they clicked submit.
        """
        first = (self.user.first_name or "").strip()
        last = (self.user.last_name or "").strip()

        if not first:
            return "Verified buyer" if self.is_verified_purchase else "Customer"
        return f"{first} {last[0]}." if last else first


class ReviewImage(BaseModel):
    """One photograph attached to a review."""

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("review"),
    )
    image = models.ImageField(
        _("image"), upload_to=review_image_path, validators=[validate_review_image]
    )
    thumbnail = models.ImageField(
        _("thumbnail"),
        upload_to=review_thumbnail_path,
        blank=True,
        null=True,
        help_text=_("Generated on upload from the full image."),
    )
    caption = models.CharField(
        _("caption"), max_length=150, blank=True, validators=[validate_no_html]
    )
    display_order = models.PositiveSmallIntegerField(
        _("display order"), default=0, db_index=True
    )

    objects = ReviewImageManager()

    class Meta:
        verbose_name = _("review image")
        verbose_name_plural = _("review images")
        ordering = ["display_order", "id"]
        indexes = [
            models.Index(fields=["review", "display_order"], name="reviewimage_order_idx"),
        ]

    def __str__(self) -> str:
        return f"Image {self.display_order} on review {self.review_id}"


class HelpfulVote(BaseModel):
    """One customer marking one review helpful.

    A row rather than a counter, because the question the UI asks is "have *I*
    voted on this", which an integer cannot answer. ``Review.helpful_count``
    exists alongside purely so the list can be ordered without a join.
    """

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="helpful_votes",
        verbose_name=_("review"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="helpful_votes",
        verbose_name=_("customer"),
    )

    class Meta:
        verbose_name = _("helpful vote")
        verbose_name_plural = _("helpful votes")
        ordering = ["-created_at"]
        constraints = [
            # One vote per customer per review, enforced in the database:
            # a double-tapped thumbs-up is two concurrent requests.
            models.UniqueConstraint(
                fields=["review", "user"], name="unique_helpful_vote_per_user"
            ),
        ]
        indexes = [
            models.Index(fields=["review", "user"], name="helpfulvote_lookup_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} found review {self.review_id} helpful"
