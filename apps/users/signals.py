"""Signal receivers for the users module.

Scope is deliberately narrow: file-system cleanup that has no natural home on
the model itself. Business invariants (such as the single default address)
live in ``models.py`` where they are explicit and testable, not here.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from apps.users.models import User


@receiver(pre_save, sender=User, dispatch_uid="users.delete_replaced_profile_image")
def delete_replaced_profile_image(sender: type[User], instance: User, **kwargs: Any) -> None:
    """Delete the previous profile image file when a new one is uploaded.

    Django replaces the column value but leaves the old file on disk forever.
    On a storefront where users re-upload avatars this leaks media
    indefinitely, so the superseded file is removed here.
    """
    if instance.pk is None:
        return

    previous = sender.objects.filter(pk=instance.pk).only("profile_image").first()
    if previous is None or not previous.profile_image:
        return

    if previous.profile_image.name == getattr(instance.profile_image, "name", None):
        return

    previous.profile_image.delete(save=False)


@receiver(post_delete, sender=User, dispatch_uid="users.delete_profile_image_on_delete")
def delete_profile_image_on_delete(sender: type[User], instance: User, **kwargs: Any) -> None:
    """Remove the stored profile image when the account row is deleted."""
    if instance.profile_image:
        instance.profile_image.delete(save=False)
