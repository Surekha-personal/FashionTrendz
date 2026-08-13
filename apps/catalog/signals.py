"""Cache invalidation for the catalog module.

Every catalog write drops the cached tree, mega menu and homepage payload so an
editor's change is visible on the next request instead of after the TTL.

Signals are the right tool here specifically because the trigger is "any write
to any of four models, from anywhere" — the admin, the API, a management
command, a shell session or a bulk update. Putting the call in ``save()`` would
miss the admin's bulk actions and every ``queryset.update()``; putting it in
the viewset would miss the admin entirely.

Business rules deliberately stay out of this module — they live in
:mod:`apps.catalog.services`, where they are explicit and directly testable.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from apps.catalog.models import Brand, Category, Collection, SubCategory
from apps.catalog.services import invalidate_catalog_cache
from apps.core.logging import get_logger

logger = get_logger(__name__)

#: Models whose rows appear in a cached payload.
_CACHED_MODELS = (Category, SubCategory, Brand, Collection)


@receiver(post_save, dispatch_uid="catalog.invalidate_on_save")
def invalidate_on_save(sender: type, instance: Any, **kwargs: Any) -> None:
    """Drop cached payloads after any catalog row is written."""
    if sender in _CACHED_MODELS:
        invalidate_catalog_cache()


@receiver(post_delete, dispatch_uid="catalog.invalidate_on_delete")
def invalidate_on_delete(sender: type, instance: Any, **kwargs: Any) -> None:
    """Drop cached payloads after any catalog row is deleted."""
    if sender in _CACHED_MODELS:
        invalidate_catalog_cache()


@receiver(m2m_changed, sender=Brand.categories.through,
          dispatch_uid="catalog.invalidate_on_brand_categories")
def invalidate_on_brand_categories(sender: type, **kwargs: Any) -> None:
    """Drop cached payloads when a brand's category links change.

    ``post_save`` does not fire for many-to-many edits, so without this the
    mega menu keeps showing a brand under a category it was just removed from
    until the TTL expires.
    """
    if kwargs.get("action") in {"post_add", "post_remove", "post_clear"}:
        invalidate_catalog_cache()


@receiver(m2m_changed, sender=Collection.categories.through,
          dispatch_uid="catalog.invalidate_on_collection_categories")
def invalidate_on_collection_categories(sender: type, **kwargs: Any) -> None:
    """Drop cached payloads when a collection's category links change."""
    if kwargs.get("action") in {"post_add", "post_remove", "post_clear"}:
        invalidate_catalog_cache()
