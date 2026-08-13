"""Django admin for the wishlist module."""

from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.wishlist.models import Wishlist, WishlistItem


class WishlistItemInline(admin.TabularInline):
    """Saved products, edited from the wishlist page."""

    model = WishlistItem
    extra = 0
    fields = ("product", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("product",)
    ordering = ("-created_at",)


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    """Admin for wishlists."""

    list_display = ("user_email", "item_count", "created_at", "updated_at")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    ordering = ("-created_at",)
    readonly_fields = ("uuid", "created_at", "updated_at")
    autocomplete_fields = ("user",)
    inlines = [WishlistItemInline]
    list_per_page = 50

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join the user and annotate the count, avoiding N+1 in the list."""
        return (
            super()
            .get_queryset(request)
            .select_related("user")
            .annotate(_item_count=Count("items", distinct=True))
        )

    @admin.display(description=_("User"), ordering="user__email")
    def user_email(self, obj: Wishlist) -> str:
        """Column showing the owner."""
        return obj.user.email

    @admin.display(description=_("Items"), ordering="_item_count")
    def item_count(self, obj: Wishlist) -> int:
        """Column showing how many products are saved."""
        return getattr(obj, "_item_count", 0)


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    """Admin for individual saved products, used for demand analysis."""

    list_display = ("product_link", "user_email", "product_price", "created_at")
    list_filter = ("created_at", "product__category", "product__brand")
    search_fields = (
        "product__name",
        "product__sku",
        "wishlist__user__email",
    )
    ordering = ("-created_at",)
    readonly_fields = ("uuid", "created_at", "updated_at")
    autocomplete_fields = ("wishlist", "product")
    date_hierarchy = "created_at"
    actions = ["delete_selected_items"]
    list_per_page = 100

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join every row the list view renders."""
        return (
            super()
            .get_queryset(request)
            .select_related("wishlist__user", "product", "product__brand")
        )

    @admin.display(description=_("Product"), ordering="product__name")
    def product_link(self, obj: WishlistItem) -> str:
        """Link through to the product."""
        url = reverse("admin:products_product_change", args=[obj.product_id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    @admin.display(description=_("User"), ordering="wishlist__user__email")
    def user_email(self, obj: WishlistItem) -> str:
        """Column showing who saved it."""
        return obj.wishlist.user.email

    @admin.display(description=_("Price"), ordering="product__selling_price")
    def product_price(self, obj: WishlistItem) -> str:
        """Column showing the product's current price."""
        return f"{obj.product.currency} {obj.product.selling_price}"

    @admin.action(description=_("Delete selected saved products"))
    def delete_selected_items(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Remove entries and repair the products' wishlist counters.

        A plain ``queryset.delete()`` would leave ``Product.wishlist_count``
        overstated, because the counter is maintained by the service layer, not
        by a delete signal.
        """
        from django.db.models import F

        from apps.products.models import Product

        product_ids = list(queryset.values_list("product_id", flat=True))
        removed, _ = queryset.delete()

        for product_id in set(product_ids):
            Product.objects.filter(pk=product_id, wishlist_count__gt=0).update(
                wishlist_count=F("wishlist_count") - product_ids.count(product_id)
            )

        self.message_user(
            request,
            _("%(count)d saved product(s) removed.") % {"count": removed},
            messages.SUCCESS,
        )
