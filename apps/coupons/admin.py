"""Django admin for the coupons module."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import Count, QuerySet, Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.coupons.models import Coupon, CouponUsage


class CouponUsageInline(admin.TabularInline):
    """Redemptions, shown read-only on the coupon page."""

    model = CouponUsage
    extra = 0
    can_delete = False
    fields = ("user", "order", "discount_amount", "is_released", "created_at")
    readonly_fields = fields
    ordering = ("-created_at",)
    max_num = 20

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Redemptions are written by the service layer, never by hand."""
        return False


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    """Admin for coupons."""

    list_display = (
        "code",
        "discount_display",
        "min_cart_value",
        "usage_display",
        "window",
        "state",
        "is_active",
        "is_public",
    )
    list_display_links = ("code",)
    list_editable = ("is_active", "is_public")
    list_filter = ("is_active", "is_public", "discount_type", "first_order_only", "valid_from")
    search_fields = ("code", "description")
    ordering = ("-created_at",)
    date_hierarchy = "valid_from"
    filter_horizontal = ("categories", "brands", "products")
    readonly_fields = ("uuid", "times_used", "created_at", "updated_at", "savings_total")
    inlines = [CouponUsageInline]
    actions = ["activate", "deactivate", "make_private", "make_public", "expire_now"]
    list_per_page = 50

    fieldsets = (
        (None, {"fields": ("code", "description")}),
        (
            _("Discount"),
            {
                "fields": (
                    "discount_type",
                    "value",
                    "max_discount",
                    "min_cart_value",
                    "currency",
                ),
                "description": _(
                    "Always set a maximum discount on a percentage coupon — "
                    "without it, the cap is unbounded on high-value items."
                ),
            },
        ),
        (
            _("Limits"),
            {
                "fields": (
                    ("max_uses", "uses_per_user"),
                    "times_used",
                    "first_order_only",
                )
            },
        ),
        (_("Validity"), {"fields": ("valid_from", "valid_until", "is_active", "is_public")}),
        (
            _("Restrictions"),
            {
                "fields": ("categories", "brands", "products"),
                "description": _(
                    "Leave empty to apply to everything. When set, only the "
                    "qualifying part of the bag is discounted."
                ),
            },
        ),
        (
            _("Audit"),
            {"fields": ("uuid", "savings_total", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Annotate redemption totals so the list issues no per-row query."""
        return (
            super()
            .get_queryset(request)
            .annotate(
                _usage_count=Count("usages", distinct=True),
                _savings=Sum("usages__discount_amount"),
            )
        )

    @admin.display(description=_("Discount"), ordering="value")
    def discount_display(self, obj: Coupon) -> str:
        """Column showing the discount and its cap."""
        base = obj.display_value
        if obj.max_discount:
            return format_html(
                "{} <span style='color:#6b7280;'>(max {})</span>", base, obj.max_discount
            )
        return base

    @admin.display(description=_("Used"), ordering="_usage_count")
    def usage_display(self, obj: Coupon) -> str:
        """Column showing redemptions against the cap."""
        used = getattr(obj, "_usage_count", 0)
        if not obj.max_uses:
            return f"{used} / ∞"

        remaining = max(obj.max_uses - obj.times_used, 0)
        colour = "#b91c1c" if remaining == 0 else "#374151"
        return format_html(
            '<span style="color:{};">{} / {}</span>', colour, obj.times_used, obj.max_uses
        )

    @admin.display(description=_("Window"))
    def window(self, obj: Coupon) -> str:
        """Column showing the validity window."""
        start = obj.valid_from.strftime("%d %b %Y")
        end = obj.valid_until.strftime("%d %b %Y") if obj.valid_until else "∞"
        return f"{start} — {end}"

    @admin.display(description=_("State"))
    def state(self, obj: Coupon) -> str:
        """Column flagging why a coupon is not currently redeemable."""
        if not obj.is_active:
            return format_html('<span style="color:#6b7280;">disabled</span>')
        if obj.is_expired:
            return format_html('<b style="color:#b91c1c;">expired</b>')
        if not obj.has_started:
            return format_html('<span style="color:#b45309;">scheduled</span>')
        if obj.is_exhausted:
            return format_html('<b style="color:#b91c1c;">exhausted</b>')
        return format_html('<b style="color:#15803d;">live</b>')

    @admin.display(description=_("Total savings given"))
    def savings_total(self, obj: Coupon) -> str:
        """Read-only field showing what this campaign has cost."""
        return f"{obj.currency} {getattr(obj, '_savings', None) or 0}"

    # -- Bulk actions -------------------------------------------------------

    @admin.action(description=_("Activate selected"))
    def activate(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Switch coupons on."""
        self._bulk(request, queryset, {"is_active": True}, _("activated"))

    @admin.action(description=_("Deactivate selected"))
    def deactivate(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Switch coupons off."""
        self._bulk(request, queryset, {"is_active": False}, _("deactivated"))

    @admin.action(description=_("Make private"))
    def make_private(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Hide coupons from the public offers list without disabling them."""
        self._bulk(request, queryset, {"is_public": False}, _("made private"))

    @admin.action(description=_("Make public"))
    def make_public(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Advertise coupons in the offers list."""
        self._bulk(request, queryset, {"is_public": True}, _("made public"))

    @admin.action(description=_("Expire now"))
    def expire_now(self, request: HttpRequest, queryset: QuerySet) -> None:
        """End a campaign immediately.

        Sets the end date rather than deactivating, so the campaign report
        still shows when it actually stopped.
        """
        from django.utils import timezone

        self._bulk(request, queryset, {"valid_until": timezone.now()}, _("expired"))

    def _bulk(
        self, request: HttpRequest, queryset: QuerySet, values: dict[str, Any], verb: str
    ) -> None:
        """Apply ``values`` to the queryset and report the count."""
        updated = queryset.update(**values)
        self.message_user(
            request,
            _("%(count)d coupon(s) %(verb)s.") % {"count": updated, "verb": verb},
            messages.SUCCESS,
        )


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    """Read-mostly admin for redemptions, used for campaign analysis."""

    list_display = ("coupon_code", "customer", "order_link", "discount_amount", "is_released", "created_at")
    list_filter = ("is_released", "created_at", "coupon")
    search_fields = ("coupon__code", "user__email", "order__order_number")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    readonly_fields = ("uuid", "created_at", "updated_at")
    list_select_related = ("coupon", "user", "order")
    list_per_page = 100

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Redemptions are created by the order flow only."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join every row the list view renders."""
        return super().get_queryset(request).select_related("coupon", "user", "order")

    @admin.display(description=_("Coupon"), ordering="coupon__code")
    def coupon_code(self, obj: CouponUsage) -> str:
        """Column showing the redeemed code."""
        return obj.coupon.code

    @admin.display(description=_("Customer"), ordering="user__email")
    def customer(self, obj: CouponUsage) -> str:
        """Column showing who redeemed it."""
        return obj.user.email

    @admin.display(description=_("Order"), ordering="order__order_number")
    def order_link(self, obj: CouponUsage) -> str:
        """Link through to the order."""
        if not obj.order_id:
            return "—"
        url = reverse("admin:orders_order_change", args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
