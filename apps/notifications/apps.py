"""App configuration for the notifications module."""

from __future__ import annotations

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Registers the notifications app and connects its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    label = "notifications"
    verbose_name = "Notifications"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.notifications import signals  # noqa: F401
