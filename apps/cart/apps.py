"""App configuration for the cart module."""

from __future__ import annotations

from django.apps import AppConfig


class CartConfig(AppConfig):
    """Registers the cart app and connects its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cart"
    label = "cart"
    verbose_name = "Shopping Cart"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.cart import signals  # noqa: F401
