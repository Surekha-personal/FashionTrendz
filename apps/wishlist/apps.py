"""App configuration for the wishlist module."""

from __future__ import annotations

from django.apps import AppConfig


class WishlistConfig(AppConfig):
    """Registers the wishlist app and connects its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.wishlist"
    label = "wishlist"
    verbose_name = "Wishlist"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.wishlist import signals  # noqa: F401
