"""App configuration for the shared core module."""

from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Registers the core module.

    Core owns no concrete models — every model class it exports is abstract —
    so this app never generates a migration. It is listed in ``INSTALLED_APPS``
    so its checks, templates and future management commands are discovered.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "Core Infrastructure"
