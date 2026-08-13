"""Django admin for homepage banners."""

from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.banner.models import Banner


class LiveStatusFilter(admin.SimpleListFilter):
    """Filter by whether a banner is showing right now.

    Distinct from the ``is_active`` filter: a banner can be active and still
    invisible because its window has not opened or has closed, which is the
    usual cause of "why isn't my campaign live?".
    """

    title = _("live status")
    parameter_name = "live"

    def lookups(self, request: HttpRequest, model_admin: object) -> list[tuple[str, str]]:
        """Return the three states a merchandiser cares about."""
        return [
            ("live", _("Live now")),
            ("scheduled", _("Scheduled")),
            ("expired", _("Expired")),
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        """Apply the chosen state."""
        return {
            "live": lambda: queryset.live(),
            "scheduled": lambda: queryset.scheduled(),
            "expired": lambda: queryset.expired(),
        }.get(self.value(), lambda: queryset)()


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    """Merchandising console for homepage content."""

    list_display = (
        "preview",
        "title",
        "placement",
        "display_order",
        "live_badge",
        "starts_at",
        "ends_at",
        "impression_count",
        "click_count",
        "ctr",
    )
    list_display_links = ("preview", "title")
    list_editable = ("display_order",)
    list_filter = ("placement", "is_active", LiveStatusFilter, "created_at")
    search_fields = ("title", "subtitle", "button_text", "button_link")
    ordering = ("placement", "display_order")
    date_hierarchy = "starts_at"
    list_per_page = 30
    readonly_fields = (
        "uuid",
        "impression_count",
        "click_count",
        "ctr",
        "large_preview",
        "created_at",
        "updated_at",
    )
    actions = ("activate", "deactivate", "reset_counters")

    fieldsets = (
        (None, {"fields": ("uuid", "title", "subtitle", "placement")}),
        (
            _("Imagery"),
            {
                "fields": ("image", "mobile_image", "alt_text", "large_preview"),
                "description": _(
                    "Supply a portrait mobile crop wherever possible — a wide hero "
                    "letterboxed onto a phone usually crops the subject out."
                ),
            },
        ),
        (_("Call to action"), {"fields": ("button_text", "button_link")}),
        (
            _("Scheduling"),
            {"fields": ("is_active", "display_order", "starts_at", "ends_at")},
        ),
        (
            _("Performance"),
            {"fields": ("impression_count", "click_count", "ctr")},
        ),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("preview"))
    def preview(self, obj: Banner) -> str:
        """Render a thumbnail in the changelist."""
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" style="height:38px;width:96px;object-fit:cover;'
            'border-radius:3px;" />',
            obj.image.url,
        )

    @admin.display(description=_("image"))
    def large_preview(self, obj: Banner) -> str:
        """Render the full banner on the edit page."""
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" style="max-width:640px;border-radius:6px;" />', obj.image.url
        )

    @admin.display(description=_("status"))
    def live_badge(self, obj: Banner) -> str:
        """Colour the live state so a dark homepage slot is obvious."""
        if obj.is_live:
            return format_html('<b style="color:#0a7d33">Live</b>')
        if not obj.is_active:
            return format_html('<span style="color:#8a8a8a">Off</span>')
        return format_html('<b style="color:#9a6700">Scheduled / expired</b>')

    @admin.display(description=_("CTR"))
    def ctr(self, obj: Banner) -> str:
        """Render the click-through rate as a percentage."""
        return f"{obj.click_through_rate}%"

    @admin.action(description=_("Activate selected banners"))
    def activate(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Switch the selected banners on."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} banner(s) activated.", messages.SUCCESS)

    @admin.action(description=_("Deactivate selected banners"))
    def deactivate(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Switch the selected banners off."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} banner(s) deactivated.", messages.WARNING)

    @admin.action(description=_("Reset impression and click counters"))
    def reset_counters(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Zero the engagement counters, for re-running a campaign."""
        count = queryset.update(impression_count=0, click_count=0)
        self.message_user(request, f"{count} banner(s) reset.", messages.SUCCESS)
