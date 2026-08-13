"""App configuration for the recommendations module."""

from __future__ import annotations

from django.apps import AppConfig


class RecommendationsConfig(AppConfig):
    """Registers the recommendations app and connects its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.recommendations"
    label = "recommendations"
    verbose_name = "Recommendations & Recently Viewed"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.recommendations import signals  # noqa: F401
