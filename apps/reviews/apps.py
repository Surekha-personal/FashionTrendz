"""App configuration for the reviews module."""

from __future__ import annotations

from django.apps import AppConfig


class ReviewsConfig(AppConfig):
    """Registers the reviews app and connects its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reviews"
    label = "reviews"
    verbose_name = "Reviews & Ratings"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.reviews import signals  # noqa: F401
