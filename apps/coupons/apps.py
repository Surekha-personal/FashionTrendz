"""App configuration for the coupons module."""

from __future__ import annotations

from django.apps import AppConfig


class CouponsConfig(AppConfig):
    """Registers the coupons app and connects its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.coupons"
    label = "coupons"
    verbose_name = "Coupons & Discounts"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.coupons import signals  # noqa: F401
