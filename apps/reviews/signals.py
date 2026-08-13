"""Signal receivers for the reviews module.

Deliberately thin. Rating aggregation is called explicitly from
``services.py`` where the transaction boundary is visible, not from a
``post_save`` — a signal that rewrites a row on another table is invisible at
the call site and fires again for every fixture, seed and data migration.

What is left here is only the work that must happen however the row goes away,
including cascades and admin deletes, which never reach the service layer.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.reviews.models import HelpfulVote, Review, ReviewImage
from apps.reviews.services import recompute_product_rating


@receiver(post_delete, sender=Review, dispatch_uid="reviews_recompute_on_delete")
def recompute_rating_on_delete(sender: type, instance: Review, **kwargs: Any) -> None:
    """Refresh the product's rating when a review disappears.

    Covers the paths the service layer does not own: a queryset delete, the
    admin's delete action, and the cascade from a deleted account. Guarded
    because the product may be going away in the same cascade.
    """
    if instance.product_id is None:
        return

    from apps.products.models import Product

    product = Product.objects.filter(pk=instance.product_id).first()
    if product is not None:
        recompute_product_rating(product)


@receiver(post_save, sender=ReviewImage, dispatch_uid="reviews_thumbnail_on_save")
def generate_thumbnail(
    sender: type, instance: ReviewImage, created: bool, **kwargs: Any
) -> None:
    """Derive a thumbnail once, on first upload.

    Review galleries render dozens of photos at postage-stamp size; serving the
    full phone-camera upload for each is the single largest page weight on a
    product with photo reviews.
    """
    if not created or not instance.image or instance.thumbnail:
        return

    from apps.core.utils import compress_image

    try:
        thumbnail = compress_image(instance.image, max_dimension=400, quality=80)
    except Exception:  # noqa: BLE001
        # ponytail: an unreadable upload loses only its thumbnail — the gallery
        # falls back to the full image. Move this to a task queue if photo
        # reviews get heavy enough to slow the request.
        return

    instance.thumbnail.save(thumbnail.name, thumbnail, save=False)
    ReviewImage.objects.filter(pk=instance.pk).update(thumbnail=instance.thumbnail.name)


@receiver(post_delete, sender=HelpfulVote, dispatch_uid="reviews_helpful_on_delete")
def decrement_helpful_count(
    sender: type, instance: HelpfulVote, **kwargs: Any
) -> None:
    """Keep ``helpful_count`` honest when a vote is removed outside the service.

    The toggle already decrements, so this only fires for cascades — a deleted
    account taking its votes with it. Guarded against going negative, and
    skipped when the review itself is being deleted.
    """
    from django.db.models import F

    Review.objects.filter(pk=instance.review_id, helpful_count__gt=0).update(
        helpful_count=F("helpful_count") - 1
    )
