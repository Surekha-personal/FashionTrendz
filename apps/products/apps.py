"""App configuration for the products module."""

from __future__ import annotations

from django.apps import AppConfig


class ProductsConfig(AppConfig):
    """Registers the products app and connects its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.products"
    label = "products"
    verbose_name = "Products & Product Catalog"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.products import signals  # noqa: F401
