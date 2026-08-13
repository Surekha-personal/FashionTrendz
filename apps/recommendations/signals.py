"""Signal receivers for the recommendations module.

Only two, and both exist because the thing they react to happens somewhere the
recommendations service layer cannot see.

The guest-trail merge is deliberately *not* here. Module 2 authenticates with
JWT, which never fires ``user_logged_in``, so the merge runs at trail-resolution
time in the view — the same place and for the same reason the cart merges.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.recommendations.scoring import invalidate_store_mean
from apps.reviews.models import Review


@receiver(post_save, sender=Review, dispatch_uid="reco_store_mean_on_review_save")
@receiver(post_delete, sender=Review, dispatch_uid="reco_store_mean_on_review_delete")
def refresh_store_mean(sender: type, **kwargs: Any) -> None:
    """Drop the cached store-mean rating when a review changes.

    The Bayesian prior in the trending score is the catalogue-wide mean rating.
    It barely moves for one review, but a bulk moderation pass can approve
    hundreds at once, and leaving the prior stale for an hour afterwards would
    rank the whole catalogue against a number that no longer describes it.

    Deleting one cache key is cheap enough that reacting to every review write
    costs less than working out which writes matter.
    """
    invalidate_store_mean()
