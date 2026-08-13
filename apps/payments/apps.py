"""App configuration for the payments module."""

from __future__ import annotations

from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Registers the payments app and connects its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments"
    label = "payments"
    verbose_name = "Payments & Refunds"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.payments import signals  # noqa: F401
