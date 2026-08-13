"""App configuration for the homepage banner module."""

from __future__ import annotations

from django.apps import AppConfig


class BannerConfig(AppConfig):
    """Registers the banner app.

    No ``ready()`` hook: banners are edited by merchandisers and read by the
    storefront. Nothing in the system reacts to a banner changing, so there are
    no signal receivers to connect.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.banner"
    label = "banner"
    verbose_name = "Homepage Banners"
