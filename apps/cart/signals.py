"""Signal receivers for the cart module.

One job: keep the parent cart's ``updated_at`` moving when its lines change.
Django does not propagate child writes to a parent row, so without this an
actively edited cart looks untouched to the abandoned-cart query.

Price recomputation deliberately stays out of signals. It lives in
:func:`apps.cart.services.recalculate_cart`, called explicitly at the start of
every cart read — a signal would fire it on every single line write, which is
several times per cart-page interaction for no benefit.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.core.logging import get_logger

logger = get_logger(__name__)


@receiver(post_save, sender=CartItem, dispatch_uid="cart.touch_on_item_save")
def touch_cart_on_item_save(sender: type, instance: CartItem, **kwargs: Any) -> None:
    """Bump the parent cart's timestamp after a line is written."""
    Cart.objects.filter(pk=instance.cart_id).update(updated_at=timezone.now())


@receiver(post_delete, sender=CartItem, dispatch_uid="cart.touch_on_item_delete")
def touch_cart_on_item_delete(sender: type, instance: CartItem, **kwargs: Any) -> None:
    """Bump the parent cart's timestamp after a line is removed."""
    # Guard against the cascade from deleting the cart itself, where the parent
    # row is already gone.
    Cart.objects.filter(pk=instance.cart_id).update(updated_at=timezone.now())


@receiver(post_save, sender=Cart, dispatch_uid="cart.log_deactivation")
def log_cart_deactivation(sender: type, instance: Cart, **kwargs: Any) -> None:
    """Record when a cart leaves circulation.

    A cart goes inactive on exactly two paths — merged into a user cart at
    sign-in, or converted into an order. Both are worth a line when a customer
    reports a bag that "emptied itself".
    """
    if kwargs.get("created") or instance.is_active:
        return

    logger.info(
        "cart deactivated id=%s user_id=%s session=%s",
        instance.pk,
        instance.user_id,
        instance.session_key[:8] or "-",
    )
