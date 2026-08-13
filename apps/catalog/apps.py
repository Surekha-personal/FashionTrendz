"""App configuration for the catalog module."""

from __future__ import annotations

from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Registers the catalog app and connects its cache-invalidation signals."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"
    verbose_name = "Catalog: Categories, Brands & Collections"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.catalog import signals  # noqa: F401
