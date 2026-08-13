"""App configuration for the orders module."""

from __future__ import annotations

from django.apps import AppConfig


class OrdersConfig(AppConfig):
    """Registers the orders app and connects its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.orders"
    label = "orders"
    verbose_name = "Checkout & Orders"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.orders import signals  # noqa: F401
