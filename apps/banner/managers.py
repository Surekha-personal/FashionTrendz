"""Querysets and managers for the banner module."""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class BannerQuerySet(models.QuerySet):
    """Queries over homepage banners."""

    def active(self) -> "BannerQuerySet":
        """Restrict to banners the merchandiser has switched on."""
        return self.filter(is_active=True)

    def live(self) -> "BannerQuerySet":
        """Restrict to banners inside their scheduled window right now.

        Evaluated in SQL rather than by filtering ``is_live`` in Python, so a
        homepage with forty scheduled campaigns still costs one indexed query.
        An open-ended banner (``ends_at IS NULL``) runs indefinitely.
        """
        now = timezone.now()
        return self.active().filter(starts_at__lte=now).filter(
            models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now)
        )

    def for_placement(self, placement: str) -> "BannerQuerySet":
        """Restrict to one slot on the storefront."""
        return self.filter(placement=placement)

    def ordered(self) -> "BannerQuerySet":
        """Merchandiser's order, newest first as the tiebreak."""
        return self.order_by("display_order", "-created_at")

    def scheduled(self) -> "BannerQuerySet":
        """Active banners whose window has not opened yet — the preview queue."""
        return self.active().filter(starts_at__gt=timezone.now())

    def expired(self) -> "BannerQuerySet":
        """Banners whose window has closed. What the cleanup job archives."""
        return self.filter(ends_at__isnull=False, ends_at__lte=timezone.now())


BannerManager = models.Manager.from_queryset(BannerQuerySet)
