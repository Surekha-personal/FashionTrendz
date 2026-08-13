"""Django admin for the cart module.

Built for support: find a customer's bag, see what is in it and why checkout is
failing, without opening a database client.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import Count, QuerySet, Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.cart.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    """Cart lines, edited from the cart page."""

    model = CartItem
    extra = 0
    fields = (
        "product",
        "variant",
        "quantity",
        "unit_price",
        "subtotal",
        "saved_for_later",
        "availability",
    )
    readonly_fields = ("unit_price", "subtotal", "availability")
    autocomplete_fields = ("product", "variant")
    ordering = ("saved_for_later", "-created_at")

    @admin.display(description=_("Availability"))
    def availability(self, obj: CartItem) -> str:
        """Show whether the line can still be checked out."""
        if obj.pk is None:
            return "—"
        available = obj.variant.available_stock
        if available <= 0:
            return format_html('<b style="color:#b91c1c;">out of stock</b>')
        if available < obj.quantity:
            return format_html(
                '<b style="color:#b45309;">only {} left</b>', available
            )
        return format_html('<span style="color:#15803d;">ok</span>')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """Admin for carts."""

    list_display = (
        "owner",
        "kind",
        "line_count",
        "unit_total",
        "value",
        "coupon_code",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "currency", "created_at")
    search_fields = ("user__email", "session_key", "coupon_code", "items__product__name")
    ordering = ("-updated_at",)
    date_hierarchy = "created_at"
    readonly_fields = ("uuid", "coupon_discount", "created_at", "updated_at")
    autocomplete_fields = ("user",)
    inlines = [CartItemInline]
    actions = ["deactivate_carts", "clear_carts"]
    list_per_page = 50

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join the user and annotate totals so the list issues no per-row query."""
        return (
            super()
            .get_queryset(request)
            .select_related("user")
            .annotate(
                _line_count=Count("items", distinct=True),
                _unit_total=Sum("items__quantity"),
                _value=Sum("items__subtotal"),
            )
        )

    @admin.display(description=_("Owner"), ordering="user__email")
    def owner(self, obj: Cart) -> str:
        """Column showing the customer, or the guest session."""
        if obj.user_id:
            return obj.user.email
        return format_html(
            '<span style="color:#6b7280;">guest:{}</span>', obj.session_key[:12]
        )

    @admin.display(description=_("Kind"))
    def kind(self, obj: Cart) -> str:
        """Column distinguishing guest carts from account carts."""
        return _("Guest") if obj.is_guest else _("Account")

    @admin.display(description=_("Lines"), ordering="_line_count")
    def line_count(self, obj: Cart) -> int:
        """Column showing how many distinct lines the cart holds."""
        return getattr(obj, "_line_count", 0)

    @admin.display(description=_("Units"), ordering="_unit_total")
    def unit_total(self, obj: Cart) -> int:
        """Column showing total units."""
        return getattr(obj, "_unit_total", 0) or 0

    @admin.display(description=_("Value"), ordering="_value")
    def value(self, obj: Cart) -> str:
        """Column showing the bag's subtotal."""
        return f"{obj.currency} {getattr(obj, '_value', 0) or 0}"

    @admin.action(description=_("Deactivate selected carts"))
    def deactivate_carts(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Take carts out of circulation without destroying their contents."""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            _("%(count)d cart(s) deactivated.") % {"count": updated},
            messages.SUCCESS,
        )

    @admin.action(description=_("Empty selected carts"))
    def clear_carts(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Delete every line in the selected carts."""
        removed, _ = CartItem.objects.filter(cart__in=queryset).delete()
        self.message_user(
            request,
            _("%(count)d cart line(s) removed.") % {"count": removed},
            messages.SUCCESS,
        )


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    """Admin for individual cart lines, used for demand and abandonment analysis."""

    list_display = (
        "product_link",
        "variant_label",
        "owner",
        "quantity",
        "unit_price",
        "subtotal",
        "saved_for_later",
        "created_at",
    )
    list_filter = ("saved_for_later", "created_at", "product__category", "product__brand")
    search_fields = (
        "product__name",
        "product__sku",
        "variant__sku",
        "cart__user__email",
        "cart__session_key",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    readonly_fields = (
        "uuid",
        "unit_price",
        "unit_mrp",
        "discount",
        "tax",
        "subtotal",
        "total",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("cart", "product", "variant")
    list_per_page = 100

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join every row the list view renders."""
        return (
            super()
            .get_queryset(request)
            .select_related("cart__user", "product", "variant")
        )

    @admin.display(description=_("Product"), ordering="product__name")
    def product_link(self, obj: CartItem) -> str:
        """Link through to the product."""
        url = reverse("admin:products_product_change", args=[obj.product_id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    @admin.display(description=_("Variant"))
    def variant_label(self, obj: CartItem) -> str:
        """Column showing the chosen colour and size."""
        return f"{obj.variant.color} / {obj.variant.size}"

    @admin.display(description=_("Owner"))
    def owner(self, obj: CartItem) -> str:
        """Column showing whose bag this line is in."""
        cart = obj.cart
        return cart.user.email if cart.user_id else f"guest:{cart.session_key[:8]}"
