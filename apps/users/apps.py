"""App configuration for the users module."""

from __future__ import annotations

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """Registers the users app and wires up its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    # Without an explicit label Django would derive "users" from the last
    # dotted segment anyway, but pinning it makes migration state independent
    # of where the package sits on disk.
    label = "users"
    verbose_name = "Users & Authentication"

    def ready(self) -> None:
        """Import signal receivers so they are connected at startup."""
        from apps.users import signals  # noqa: F401
