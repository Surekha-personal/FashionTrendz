"""Signal receivers for the products module.

Three jobs, all of them cross-cutting cleanup that has no single natural home
on a model:

1. keep ``Product.total_stock`` and ``stock_status`` in step with the variant
   rows, whatever wrote them;
2. keep exactly one primary image per product;
3. drop cached product payloads on any write.

Business rules stay in :mod:`apps.products.services`.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.core.logging import get_logger
from apps.products.models import Product, ProductImage, ProductTag, ProductVariant
from apps.products.services import invalidate_product_cache, sync_product_stock

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------


@receiver(post_save, sender=ProductVariant, dispatch_uid="products.stock_on_variant_save")
def sync_stock_on_variant_save(
    sender: type, instance: ProductVariant, **kwargs: Any
) -> None:
    """Refresh the parent product's cached stock after a variant is written.

    A signal rather than ``ProductVariant.save()`` because stock also moves
    through the admin's inline formsets, bulk imports and the checkout
    reservation path — every one of which would need remembering otherwise.
    """
    sync_product_stock(instance.product)


@receiver(post_delete, sender=ProductVariant, dispatch_uid="products.stock_on_variant_delete")
def sync_stock_on_variant_delete(
    sender: type, instance: ProductVariant, **kwargs: Any
) -> None:
    """Refresh cached stock after a variant is removed."""
    # When the whole product is being deleted its row is already gone, and
    # recomputing against it would raise.
    if Product.objects.filter(pk=instance.product_id).exists():
        sync_product_stock(instance.product)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


@receiver(pre_save, sender=ProductImage, dispatch_uid="products.single_primary_image")
def enforce_single_primary_image(
    sender: type, instance: ProductImage, **kwargs: Any
) -> None:
    """Demote the previous primary before this one is written.

    A partial unique index enforces "one primary per product" in the database,
    and it is checked per row as the statement runs — so the demotion has to
    happen *first* or the insert is rejected while the old primary still holds
    the slot. Same ordering rule as the default-address constraint in Module 2.
    """
    if not instance.is_primary:
        return

    siblings = ProductImage.objects.filter(
        product_id=instance.product_id, is_primary=True
    )
    if instance.pk is not None:
        siblings = siblings.exclude(pk=instance.pk)
    siblings.update(is_primary=False)


@receiver(post_save, sender=ProductImage, dispatch_uid="products.promote_first_image")
def promote_first_image(sender: type, instance: ProductImage, **kwargs: Any) -> None:
    """Make the first uploaded image primary automatically.

    Without this, a product whose editor forgot to tick the box renders with no
    card image at all — a blank tile in every listing.
    """
    if not kwargs.get("created"):
        return

    has_primary = ProductImage.objects.filter(
        product_id=instance.product_id, is_primary=True
    ).exists()
    if not has_primary:
        ProductImage.objects.filter(pk=instance.pk).update(is_primary=True)
        # Keep the in-memory object in step with the row. queryset.update()
        # writes the column but leaves this instance stale, and callers that
        # keep using it — including the delete path below — would then act on
        # a value that has not been true since the moment it was written.
        instance.is_primary = True


@receiver(post_delete, sender=ProductImage, dispatch_uid="products.reassign_primary_image")
def reassign_primary_image(sender: type, instance: ProductImage, **kwargs: Any) -> None:
    """Promote another image when a product is left without a primary.

    Asks the database whether a primary still exists rather than trusting
    ``instance.is_primary``. The in-memory flag can be stale — it is written by
    ``queryset.update()`` in ``promote_first_image`` — and a product silently
    left with no primary renders as a blank tile in every listing.
    """
    if not Product.objects.filter(pk=instance.product_id).exists():
        return

    remaining = ProductImage.objects.filter(product_id=instance.product_id)
    if remaining.filter(is_primary=True).exists():
        return

    successor = remaining.order_by("display_order", "id").first()
    if successor is not None:
        ProductImage.objects.filter(pk=successor.pk).update(is_primary=True)


@receiver(post_delete, sender=ProductImage, dispatch_uid="products.delete_image_files")
def delete_image_files(sender: type, instance: ProductImage, **kwargs: Any) -> None:
    """Remove the stored files when an image row is deleted.

    Django never deletes files on its own, so without this every replaced
    product photograph leaks storage forever.
    """
    for field in (instance.image, instance.thumbnail):
        if field:
            field.delete(save=False)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHED_MODELS = (Product, ProductVariant, ProductImage, ProductTag)


@receiver(post_save, dispatch_uid="products.invalidate_cache_on_save")
def invalidate_cache_on_save(sender: type, instance: Any, **kwargs: Any) -> None:
    """Drop cached product payloads after any product-related write."""
    if sender in _CACHED_MODELS:
        invalidate_product_cache()


@receiver(post_delete, dispatch_uid="products.invalidate_cache_on_delete")
def invalidate_cache_on_delete(sender: type, instance: Any, **kwargs: Any) -> None:
    """Drop cached product payloads after any product-related delete."""
    if sender in _CACHED_MODELS:
        invalidate_product_cache()
