"""Review business logic.

Views stay thin; everything that decides *whether* something may happen lives
here. Three groups: eligibility (who may review what), the review lifecycle
(write, edit, delete, moderate), and aggregation (keeping ``Product``'s cached
rating honest).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, F, Q, QuerySet
from django.utils import timezone

from apps.core.choices import OrderStatus
from apps.core.exceptions import BusinessRuleViolation, ResourceConflict
from apps.orders.models import OrderItem
from apps.products.models import Product
from apps.reviews.models import HelpfulVote, ModerationStatus, Review, ReviewImage

#: Order states in which the customer has the product in hand. Reviewing before
#: delivery describes the checkout, not the garment.
REVIEWABLE_ORDER_STATUSES: tuple[str, ...] = (OrderStatus.DELIVERED,)

#: How long the rating summary stays cached. A product page reads it on every
#: hit; a review lands on a popular product maybe hourly.
RATING_SUMMARY_TTL: int = 900

#: Photographs one customer may attach to one review.
MAX_IMAGES_PER_REVIEW: int = 5

#: Number of stars, used to build a complete distribution including zeroes.
STAR_VALUES: tuple[int, ...] = (5, 4, 3, 2, 1)


def _summary_cache_key(product_id: int) -> str:
    return f"reviews:summary:{product_id}"


def auto_approve() -> bool:
    """Return whether new reviews skip the moderation queue.

    Off by default. A store with no moderator staffed still wants the setting,
    because a queue nobody drains is a review section that never fills.
    """
    return bool(getattr(settings, "REVIEW_AUTO_APPROVE", False))


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def reviewable_order_items(user: Any) -> QuerySet[OrderItem]:
    """Return delivered lines this customer has not reviewed yet.

    This is the source of truth for "may I review?". It is a single query with
    an anti-join rather than a per-product loop, because the account page shows
    the whole pending-reviews list at once.
    """
    return (
        OrderItem.objects.filter(
            order__user=user, order__status__in=REVIEWABLE_ORDER_STATUSES
        )
        .filter(review__isnull=True)
        .select_related("order", "product", "variant")
        .order_by("-order__delivered_at", "-id")
    )


def get_reviewable_item(user: Any, order_item_id: int) -> OrderItem:
    """Return one line this customer may review, or explain why they may not.

    Distinguishing "not yours", "not delivered" and "already reviewed" matters:
    a single "cannot review" message sends the customer to support for what is
    usually just an undelivered order.
    """
    try:
        item = OrderItem.objects.select_related("order", "product").get(pk=order_item_id)
    except OrderItem.DoesNotExist as exc:
        raise BusinessRuleViolation("That order item does not exist.") from exc

    if item.order.user_id != getattr(user, "pk", None):
        # Same message as "does not exist" would leak less, but the customer is
        # authenticated and the id came from their own order list.
        raise BusinessRuleViolation("That order item does not belong to you.")

    if item.order.status not in REVIEWABLE_ORDER_STATUSES:
        raise BusinessRuleViolation(
            "You can review a product once your order has been delivered."
        )

    if Review.objects.filter(order_item_id=item.pk).exists():
        raise ResourceConflict("You have already reviewed this purchase.")

    return item


def can_review_product(user: Any, product: Product) -> dict[str, Any]:
    """Report whether ``user`` may review ``product``, and against which line.

    Returned as data rather than a boolean so the product page can render the
    right call to action — "Write a review", "Edit your review" or nothing —
    without a second round trip.
    """
    if not (user and user.is_authenticated):
        return {"can_review": False, "reason": "authentication_required", "order_item": None}

    existing = Review.objects.filter(user=user, product=product).first()
    item = reviewable_order_items(user).filter(product=product).first()

    if item is not None:
        return {"can_review": True, "reason": "", "order_item": item.pk}

    if existing is not None:
        return {"can_review": False, "reason": "already_reviewed", "order_item": None}

    return {"can_review": False, "reason": "not_purchased", "order_item": None}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@transaction.atomic
def create_review(
    *,
    user: Any,
    order_item_id: int,
    rating: int,
    title: str = "",
    body: str = "",
    images: list[Any] | None = None,
) -> Review:
    """Record a review against a delivered purchase.

    The product is read off the order line, never from the request. A client
    that could name its own product would be able to attach a five-star review
    to any item in the catalogue by quoting one real purchase.
    """
    item = get_reviewable_item(user, order_item_id)

    status = (
        ModerationStatus.APPROVED if auto_approve() else ModerationStatus.PENDING
    )

    try:
        review = Review.objects.create(
            product_id=item.product_id,
            user=user,
            order_item=item,
            rating=rating,
            title=title.strip(),
            body=body.strip(),
            is_verified_purchase=True,
            status=status,
            moderated_at=timezone.now() if status == ModerationStatus.APPROVED else None,
        )
    except IntegrityError as exc:
        # The unique constraint fired: two submissions raced. Report the
        # outcome the customer would have got had they arrived a moment later.
        raise ResourceConflict("You have already reviewed this purchase.") from exc

    attach_images(review, images or [])
    recompute_product_rating(review.product)
    return review


@transaction.atomic
def update_review(
    review: Review,
    *,
    rating: int | None = None,
    title: str | None = None,
    body: str | None = None,
    images: list[Any] | None = None,
) -> Review:
    """Amend an existing review and send it back through moderation.

    Editing resets an approved review to pending. Otherwise an approved review
    is a permanently writable slot on a public page — write something benign,
    get approved, replace the body with anything.
    """
    fields: list[str] = []

    if rating is not None and rating != review.rating:
        review.rating = rating
        fields.append("rating")
    if title is not None:
        review.title = title.strip()
        fields.append("title")
    if body is not None:
        review.body = body.strip()
        fields.append("body")

    if fields and not auto_approve():
        review.status = ModerationStatus.PENDING
        review.moderated_at = None
        review.moderated_by = None
        review.rejection_reason = ""
        fields += ["status", "moderated_at", "moderated_by", "rejection_reason"]

    if fields:
        review.full_clean(exclude=["order_item"])
        review.save(update_fields=[*set(fields), "updated_at"])

    if images:
        attach_images(review, images)

    recompute_product_rating(review.product)
    return review


@transaction.atomic
def delete_review(review: Review) -> None:
    """Remove a review and refresh the product's rating.

    A hard delete. Soft-deleting would leave the row inside every aggregate
    unless every query learned to exclude it, and a customer who withdraws an
    opinion expects it gone rather than hidden.

    The rating refresh is the ``post_delete`` receiver's job, so a review
    removed here and one removed by a cascade behave identically.
    """
    review.delete()


def attach_images(review: Review, images: list[Any]) -> list[ReviewImage]:
    """Attach photographs to a review, respecting the per-review ceiling."""
    if not images:
        return []

    existing = review.images.count()
    room = MAX_IMAGES_PER_REVIEW - existing
    if room <= 0:
        raise BusinessRuleViolation(
            f"A review can have at most {MAX_IMAGES_PER_REVIEW} photos."
        )

    created = [
        ReviewImage.objects.create(
            review=review, image=image, display_order=existing + offset
        )
        for offset, image in enumerate(images[:room])
    ]
    return created


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------


@transaction.atomic
def moderate_review(
    review: Review,
    *,
    moderator: Any,
    status: str,
    reason: str = "",
) -> Review:
    """Approve or reject one review."""
    if status not in {ModerationStatus.APPROVED, ModerationStatus.REJECTED}:
        raise BusinessRuleViolation("A review can only be approved or rejected.")

    review.status = status
    review.moderated_by = moderator if getattr(moderator, "pk", None) else None
    review.moderated_at = timezone.now()
    review.rejection_reason = reason.strip() if status == ModerationStatus.REJECTED else ""
    review.save(
        update_fields=[
            "status",
            "moderated_by",
            "moderated_at",
            "rejection_reason",
            "updated_at",
        ]
    )

    recompute_product_rating(review.product)
    return review


def bulk_moderate(
    queryset: QuerySet[Review], *, moderator: Any, status: str, reason: str = ""
) -> int:
    """Approve or reject many reviews, then refresh every product touched.

    The status change is one ``UPDATE``; only the affected products are
    recomputed. Iterating review-by-review would recompute the same popular
    product once per review in the batch.
    """
    if status not in {ModerationStatus.APPROVED, ModerationStatus.REJECTED}:
        raise BusinessRuleViolation("A review can only be approved or rejected.")

    product_ids = list(queryset.values_list("product_id", flat=True).distinct())

    with transaction.atomic():
        updated = queryset.update(
            status=status,
            moderated_by=moderator if getattr(moderator, "pk", None) else None,
            moderated_at=timezone.now(),
            rejection_reason=reason.strip() if status == ModerationStatus.REJECTED else "",
            updated_at=timezone.now(),
        )

    for product in Product.objects.filter(pk__in=product_ids):
        recompute_product_rating(product)

    return updated


def get_moderation_queue() -> QuerySet[Review]:
    """Return reviews awaiting a decision, oldest first.

    Oldest first on purpose: newest-first leaves the tail of the queue
    permanently unseen on a store that receives reviews faster than it clears
    them.
    """
    return Review.objects.pending().with_detail().order_by("created_at")


# ---------------------------------------------------------------------------
# Helpful votes
# ---------------------------------------------------------------------------


@transaction.atomic
def toggle_helpful(review: Review, user: Any) -> dict[str, Any]:
    """Add or remove ``user``'s helpful vote and return the new state.

    A toggle rather than separate add/remove endpoints: the button has one
    visual state and a mis-tapped vote should undo with the same tap. The
    counter moves by ``F()`` so concurrent voters do not overwrite each other.
    """
    if review.user_id == getattr(user, "pk", None):
        raise BusinessRuleViolation("You cannot vote on your own review.")

    vote = HelpfulVote.objects.filter(review=review, user=user).first()

    if vote is not None:
        # The decrement lives in the ``post_delete`` receiver, so a vote
        # removed by a cascade counts the same as one removed here. Doing it
        # again in this branch would subtract twice.
        vote.delete()
        voted = False
    else:
        try:
            with transaction.atomic():
                HelpfulVote.objects.create(review=review, user=user)
        except IntegrityError:
            # Double-tap raced past the SELECT above. The vote exists, which is
            # what the customer wanted; do not double-count it.
            return {
                "voted": True,
                "helpful_count": Review.objects.filter(pk=review.pk)
                .values_list("helpful_count", flat=True)
                .first()
                or 0,
            }
        Review.objects.filter(pk=review.pk).update(
            helpful_count=F("helpful_count") + 1
        )
        voted = True

    review.refresh_from_db(fields=["helpful_count"])
    return {"voted": voted, "helpful_count": review.helpful_count}


def recount_helpful(review: Review) -> int:
    """Rebuild ``helpful_count`` from the vote rows.

    The repair path for the denormalised counter. Cheap enough to run from a
    management shell when a number looks wrong, which is the only reason a
    denormalised counter is safe to keep.
    """
    total = HelpfulVote.objects.filter(review=review).count()
    Review.objects.filter(pk=review.pk).update(helpful_count=total)
    return total


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def recompute_product_rating(product: Product) -> Product:
    """Recompute a product's cached rating from its **approved** reviews.

    Approved-only is the whole point. Averaging the pending queue means a
    rejected one-star spam review still moved the number that shoppers see,
    and rejecting it later would not move it back unless this ran again.

    One aggregate query, one ``UPDATE``, and the cached summary dropped.
    """
    aggregate = Review.objects.filter(
        product=product, status=ModerationStatus.APPROVED
    ).aggregate(average=Avg("rating"), total=Count("id"))

    average = aggregate["average"]
    total = aggregate["total"] or 0

    Product.objects.filter(pk=product.pk).update(
        rating_average=Decimal(str(round(average, 2))) if average else Decimal("0.00"),
        rating_count=total,
        review_count=total,
    )

    cache.delete(_summary_cache_key(product.pk))
    product.rating_average = (
        Decimal(str(round(average, 2))) if average else Decimal("0.00")
    )
    product.rating_count = total
    product.review_count = total
    return product


def get_star_distribution(product: Product) -> dict[str, Any]:
    """Return how many approved reviews sit at each star, with percentages.

    One ``GROUP BY`` for all five buckets rather than five ``COUNT`` queries,
    then filled out in Python so a star nobody used still appears as zero — the
    bar chart needs the empty rows.
    """
    rows = (
        Review.objects.filter(product=product, status=ModerationStatus.APPROVED)
        .values("rating")
        .annotate(count=Count("id"))
    )
    counts = {int(row["rating"]): row["count"] for row in rows}
    total = sum(counts.values())

    return {
        "total": total,
        "distribution": [
            {
                "stars": star,
                "count": counts.get(star, 0),
                "percentage": round(counts.get(star, 0) * 100 / total, 1) if total else 0.0,
            }
            for star in STAR_VALUES
        ],
    }


def get_rating_summary(product: Product, *, use_cache: bool = True) -> dict[str, Any]:
    """Return the rating block a product page renders, cached.

    Cached because it is read on every product view and written only when a
    review changes state — and every one of those writes deletes this key.
    """
    key = _summary_cache_key(product.pk)

    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return cached

    breakdown = get_star_distribution(product)
    approved = Review.objects.filter(product=product, status=ModerationStatus.APPROVED)
    aggregate = approved.aggregate(average=Avg("rating"))

    summary = {
        "average": float(round(aggregate["average"], 2)) if aggregate["average"] else 0.0,
        "count": breakdown["total"],
        "verified_count": approved.filter(is_verified_purchase=True).count(),
        "with_images_count": approved.with_images().count(),
        "distribution": breakdown["distribution"],
    }

    if use_cache:
        cache.set(key, summary, RATING_SUMMARY_TTL)
    return summary


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

#: Sort keys the review list accepts, mapped to queryset methods.
SORT_CHOICES: dict[str, str] = {
    "newest": "recent",
    "oldest": "oldest",
    "most_helpful": "most_helpful",
}


def get_product_reviews(
    slug: str,
    *,
    user: Any = None,
    rating: int | None = None,
    verified_only: bool = False,
    with_images: bool = False,
    sort: str = "newest",
) -> QuerySet[Review]:
    """Return the approved review list for one product, filtered and sorted."""
    queryset = Review.objects.approved().for_product(slug).with_detail()

    if rating is not None:
        queryset = queryset.rated(rating)
    if verified_only:
        queryset = queryset.verified()
    if with_images:
        queryset = queryset.with_images()

    queryset = getattr(queryset, SORT_CHOICES.get(sort, "recent"))()
    return queryset.voted_by(user)


def get_product_gallery(slug: str, limit: int = 24) -> QuerySet[ReviewImage]:
    """Return customer photographs for a product's gallery strip."""
    return (
        ReviewImage.objects.approved()
        .for_product(slug)
        .select_related("review")
        .order_by("-review__helpful_count", "-id")[:limit]
    )


def get_user_reviews(user: Any) -> QuerySet[Review]:
    """Return every review a customer has written, whatever its status.

    Unlike the public list this includes pending and rejected rows: the author
    needs to see that their review is held, or why it was turned down.
    """
    return Review.objects.for_user(user).with_detail().recent()
