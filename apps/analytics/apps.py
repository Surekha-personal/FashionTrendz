"""App configuration for the analytics module."""

from __future__ import annotations

from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """Registers the analytics app.

    No ``ready()`` hook and no models. Every number this app serves is derived
    from tables other modules already own, so there is nothing to migrate and
    nothing to keep in sync.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    label = "analytics"
    verbose_name = "Analytics & Reporting"
