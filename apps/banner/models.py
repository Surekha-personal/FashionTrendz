"""Homepage banner model.

The only genuinely missing table in the brief — homepage promotional content is
hard-coded in the Next.js frontend today, so every campaign needs a deploy.
This was flagged as ``homepage_banner`` in the database design document.

Deliberately one table, not two. A separate ``HeroCarouselSlide`` would carry
the same columns as a banner with ``placement='hero'`` and add a join for no
gain; the placement column already distinguishes them.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.banner.managers import BannerManager
from apps.catalog.utils import UploadPath
from apps.core.mixins import BaseModel
from apps.core.validators import validate_no_html

banner_desktop_path = UploadPath("banners/desktop")
banner_mobile_path = UploadPath("banners/mobile")


class BannerPlacement(models.TextChoices):
    """Where on the storefront a banner renders.

    The frontend requests one placement at a time, so this column is what lets
    a merchandiser add a strip banner without a code change deciding where it
    goes.
    """

    HERO = "hero", _("Homepage hero carousel")
    STRIP = "strip", _("Homepage promotional strip")
    GRID_LEFT = "grid_left", _("Homepage grid — left tile")
    GRID_RIGHT = "grid_right", _("Homepage grid — right tile")
    CATEGORY_TOP = "category_top", _("Category landing header")
    FOOTER = "footer", _("Footer promotion")


class Banner(BaseModel):
    """One scheduled promotional banner."""

    title = models.CharField(
        _("title"), max_length=150, validators=[validate_no_html]
    )
    subtitle = models.CharField(
        _("subtitle"), max_length=255, blank=True, validators=[validate_no_html]
    )

    placement = models.CharField(
        _("placement"),
        max_length=16,
        choices=BannerPlacement.choices,
        default=BannerPlacement.HERO,
        db_index=True,
    )

    image = models.ImageField(
        _("desktop image"),
        upload_to=banner_desktop_path,
        help_text=_("Wide crop, shown at tablet width and above."),
    )
    # A separate crop rather than CSS cropping the desktop asset: a 3:1 hero
    # letterboxed onto a phone leaves the model's head out of frame, which is
    # the single most common complaint about responsive banners.
    mobile_image = models.ImageField(
        _("mobile image"),
        upload_to=banner_mobile_path,
        blank=True,
        null=True,
        help_text=_("Portrait crop for phones. Falls back to the desktop image."),
    )
    alt_text = models.CharField(
        _("alt text"),
        max_length=200,
        blank=True,
        validators=[validate_no_html],
        help_text=_("Required for accessibility; describes the image, not the offer."),
    )

    button_text = models.CharField(
        _("button text"), max_length=40, blank=True, validators=[validate_no_html]
    )
    # Relative by convention ("/collections/festive"), so the banner survives
    # the storefront moving domains. Absolute URLs still work.
    button_link = models.CharField(_("button link"), max_length=500, blank=True)

    display_order = models.PositiveSmallIntegerField(
        _("display order"), default=0, db_index=True
    )
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    # Scheduling. A campaign that goes live at midnight should not need someone
    # awake at midnight to tick a box.
    starts_at = models.DateTimeField(_("starts at"), default=timezone.now)
    ends_at = models.DateTimeField(
        _("ends at"),
        null=True,
        blank=True,
        help_text=_("Leave blank to run indefinitely."),
    )

    # Denormalised engagement counters, maintained with F() expressions so
    # concurrent impressions do not overwrite each other.
    impression_count = models.PositiveIntegerField(
        _("impressions"), default=0, editable=False
    )
    click_count = models.PositiveIntegerField(
        _("clicks"), default=0, editable=False
    )

    objects = BannerManager()

    class Meta:
        verbose_name = _("banner")
        verbose_name_plural = _("banners")
        ordering = ["placement", "display_order", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__isnull=True)
                | models.Q(ends_at__gt=models.F("starts_at")),
                name="banner_window_ordered",
            ),
        ]
        indexes = [
            # The storefront's only read: live banners for one placement, in
            # display order.
            models.Index(
                fields=["placement", "is_active", "display_order"],
                name="banner_placement_idx",
            ),
            # The scheduler's read.
            models.Index(fields=["is_active", "starts_at", "ends_at"], name="banner_window_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_placement_display()}: {self.title}"

    @property
    def is_live(self) -> bool:
        """Return whether this banner should be showing right now."""
        now = timezone.now()
        return bool(
            self.is_active
            and self.starts_at <= now
            and (self.ends_at is None or self.ends_at > now)
        )

    @property
    def click_through_rate(self) -> float:
        """Return clicks as a percentage of impressions.

        Zero impressions returns 0.0 rather than dividing — a banner nobody has
        seen has no rate, and reporting it as infinite breaks the admin column.
        """
        if not self.impression_count:
            return 0.0
        return round(self.click_count * 100 / self.impression_count, 2)
