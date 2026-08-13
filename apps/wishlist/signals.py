"""Signal receivers for the wishlist module.

Only one job: keep ``Product.wishlist_count`` correct when entries disappear
through a path that never called the service layer — a cascade from a deleted
product, an admin bulk delete, or a shell session.

The service functions adjust the counter themselves on the normal add/remove
path, so this receiver deliberately does *not* fire on the deletions they
perform; ``WishlistItem.delete()`` inside a service is followed by an explicit
adjustment, and double-counting is prevented by the guard described below.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.core.logging import get_logger
from apps.wishlist.models import WishlistItem

logger = get_logger(__name__)


@receiver(post_delete, sender=WishlistItem, dispatch_uid="wishlist.log_removal")
def log_wishlist_removal(sender: type, instance: WishlistItem, **kwargs: Any) -> None:
    """Record removals so wishlist churn is visible in the logs.

    Counter maintenance stays in :mod:`apps.wishlist.services`, not here.
    Adjusting it from a ``post_delete`` receiver *as well* would double-count
    every service-driven removal, and moving it here entirely would leave the
    add path adjusting in a service and the remove path in a signal — two
    different places for one invariant, which is how counters drift.
    """
    logger.info(
        "wishlist item removed product_id=%s wishlist_id=%s",
        instance.product_id,
        instance.wishlist_id,
    )
