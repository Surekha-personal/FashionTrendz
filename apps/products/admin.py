"""Django admin for the products module.

Built for a merchandiser: thumbnails in the list, everything about one product
editable on a single page through inlines, and bulk actions for the flag
changes that are otherwise a hundred clicks.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.products.models import (
    LOW_STOCK_THRESHOLD,
    Product,
    ProductAttribute,
    ProductImage,
    ProductSpecification,
    ProductTag,
    ProductVariant,
)


def _thumbnail(field: Any, height: int = 40) -> str:
    """Render an image field as an inline preview, or a dash when empty."""
    if not field:
        return "—"
    try:
        url = field.url
    except ValueError:  # pragma: no cover - misconfigured storage
        return "—"
    return format_html(
        '<img src="{}" style="height:{}px;width:auto;'
        'border-radius:4px;object-fit:cover;" />',
        url,
        height,
    )


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------


class ProductImageInline(admin.TabularInline):
    """Gallery images, edited on the product page."""

    model = ProductImage
    extra = 1
    fields = ("preview", "image", "thumbnail", "alt_text", "display_order", "is_primary")
    readonly_fields = ("preview",)
    ordering = ("-is_primary", "display_order")

    @admin.display(description=_("Preview"))
    def preview(self, obj: ProductImage) -> str:
        """Inline thumbnail."""
        return _thumbnail(obj.image, 60)


class ProductVariantInline(admin.TabularInline):
    """Colour/size rows, edited on the product page."""

    model = ProductVariant
    extra = 1
    fields = (
        "sku",
        "color",
        "color_code",
        "size",
        "stock",
        "reserved_stock",
        "available",
        "price_override",
        "is_active",
    )
    readonly_fields = ("available",)
    ordering = ("color", "size")

    @admin.display(description=_("Available"))
    def available(self, obj: ProductVariant) -> str:
        """Show unreserved stock, flagged when it is running out."""
        if obj.pk is None:
            return "—"
        units = obj.available_stock
        if units <= 0:
            return format_html('<b style="color:#b91c1c;">out of stock</b>')
        if units <= LOW_STOCK_THRESHOLD:
            return format_html('<b style="color:#b45309;">{} left</b>', units)
        return str(units)


class ProductSpecificationInline(admin.TabularInline):
    """Specification table rows."""

    model = ProductSpecification
    extra = 1
    fields = ("label", "value", "display_order")
    ordering = ("display_order", "label")


class ProductAttributeInline(admin.TabularInline):
    """Key/value attribute rows."""

    model = ProductAttribute
    extra = 1
    fields = ("key", "value")
    ordering = ("key",)


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------


class ProductBulkActionsMixin:
    """Bulk flag changes.

    ``queryset.update()`` so a thousand rows cost one statement. That skips
    ``post_save``, so the product cache is invalidated explicitly — the same
    tradeoff as the catalog module's bulk actions.
    """

    @admin.action(description=_("Activate selected"))
    def activate(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Switch products on."""
        self._bulk(request, queryset, {"is_active": True}, _("activated"))

    @admin.action(description=_("Deactivate selected"))
    def deactivate(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Switch products off."""
        self._bulk(request, queryset, {"is_active": False}, _("deactivated"))

    @admin.action(description=_("Mark as featured"))
    def feature(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Promote to the featured rail."""
        self._bulk(request, queryset, {"is_featured": True}, _("featured"))

    @admin.action(description=_("Remove featured flag"))
    def unfeature(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Demote from the featured rail."""
        self._bulk(request, queryset, {"is_featured": False}, _("unfeatured"))

    @admin.action(description=_("Mark as trending"))
    def mark_trending(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Promote to the trending rail."""
        self._bulk(request, queryset, {"is_trending": True}, _("marked trending"))

    @admin.action(description=_("Mark as best seller"))
    def mark_best_seller(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Promote to the best-seller rail."""
        self._bulk(request, queryset, {"is_best_seller": True}, _("marked best seller"))

    @admin.action(description=_("Mark as new arrival"))
    def mark_new_arrival(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Promote to the new-arrivals rail."""
        self._bulk(request, queryset, {"is_new_arrival": True}, _("marked new arrival"))

    @admin.action(description=_("Clear all merchandising flags"))
    def clear_flags(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Reset every rail flag at once, for end-of-campaign cleanup."""
        self._bulk(
            request,
            queryset,
            {
                "is_featured": False,
                "is_trending": False,
                "is_best_seller": False,
                "is_new_arrival": False,
                "is_recommended": False,
            },
            _("cleared"),
        )

    @admin.action(description=_("Publish now"))
    def publish_now(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Set the publication time to now, making products live."""
        from django.utils import timezone

        self._bulk(
            request, queryset, {"published_at": timezone.now()}, _("published")
        )

    @admin.action(description=_("Resync stock from variants"))
    def resync_stock(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Repair cached stock figures.

        The signals keep these current, but a bulk import that wrote variants
        with ``bulk_create`` bypasses signals entirely — this is the repair.
        """
        from apps.products.services import sync_product_stock

        for product in queryset:
            sync_product_stock(product)

        self.message_user(
            request,
            _("Stock resynced for %(count)d product(s).") % {"count": queryset.count()},
            messages.SUCCESS,
        )

    def _bulk(
        self,
        request: HttpRequest,
        queryset: QuerySet,
        values: dict[str, Any],
        verb: str,
    ) -> None:
        """Apply ``values`` and refresh the product cache."""
        from apps.products.services import invalidate_product_cache

        updated = queryset.update(**values)
        invalidate_product_cache()
        self.message_user(
            request,
            _("%(count)d product(s) %(verb)s.") % {"count": updated, "verb": verb},
            messages.SUCCESS,
        )


# ---------------------------------------------------------------------------
# Admin classes
# ---------------------------------------------------------------------------


@admin.register(Product)
class ProductAdmin(ProductBulkActionsMixin, admin.ModelAdmin):
    """Admin for products."""

    list_display = (
        "image_preview",
        "name",
        "brand",
        "subcategory",
        "price_display",
        "stock_display",
        "rating_average",
        "is_active",
        "is_featured",
        "is_trending",
    )
    list_display_links = ("image_preview", "name")
    list_editable = ("is_active", "is_featured", "is_trending")
    list_filter = (
        "is_active",
        "is_featured",
        "is_trending",
        "is_new_arrival",
        "is_best_seller",
        "is_luxury",
        "stock_status",
        "gender",
        "season",
        "category",
        "brand",
    )
    search_fields = ("name", "slug", "sku", "barcode", "brand__name", "short_description")
    ordering = ("-published_at", "-created_at")
    date_hierarchy = "published_at"
    autocomplete_fields = ("category", "subcategory", "brand", "collection")
    filter_horizontal = ("tags",)
    prepopulated_fields = {"slug": ("name",)}
    list_per_page = 50
    list_select_related = ("brand", "subcategory", "category")

    inlines = [
        ProductImageInline,
        ProductVariantInline,
        ProductSpecificationInline,
        ProductAttributeInline,
    ]

    actions = [
        "activate",
        "deactivate",
        "feature",
        "unfeature",
        "mark_trending",
        "mark_best_seller",
        "mark_new_arrival",
        "clear_flags",
        "publish_now",
        "resync_stock",
    ]

    readonly_fields = (
        "uuid",
        "discount_percentage",
        "discount_amount",
        "total_stock",
        "stock_status",
        "rating_average",
        "rating_count",
        "review_count",
        "wishlist_count",
        "view_count",
        "purchase_count",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (None, {"fields": ("name", "slug", "sku", "barcode")}),
        (_("Description"), {"fields": ("short_description", "long_description")}),
        (
            _("Taxonomy"),
            {"fields": ("category", "subcategory", "brand", "collection", "tags")},
        ),
        (
            _("Pricing"),
            {
                "fields": (
                    "mrp",
                    "selling_price",
                    ("discount_percentage", "discount_amount"),
                    "tax_percentage",
                    "currency",
                ),
                "description": _(
                    "Discount is derived from MRP and selling price on save."
                ),
            },
        ),
        (
            _("Attributes"),
            {
                "fields": (
                    "gender",
                    "material",
                    "fit",
                    "sleeve_type",
                    "neck_type",
                    "pattern",
                    "occasion",
                    "season",
                )
            },
        ),
        (
            _("Logistics"),
            {
                "fields": (
                    "country_of_origin",
                    "weight_grams",
                    "dimensions",
                    "warranty",
                    "care_instructions",
                    "return_policy",
                    "shipping_info",
                    "estimated_delivery_days",
                    "is_returnable",
                )
            },
        ),
        (
            _("Merchandising"),
            {
                "fields": (
                    "is_active",
                    "published_at",
                    "is_featured",
                    "is_new_arrival",
                    "is_best_seller",
                    "is_trending",
                    "is_luxury",
                    "is_recommended",
                )
            },
        ),
        (_("SEO"), {"fields": ("meta_title", "meta_description", "meta_keywords")}),
        (
            _("Statistics"),
            {
                "fields": (
                    ("total_stock", "stock_status"),
                    ("rating_average", "rating_count", "review_count"),
                    ("view_count", "purchase_count", "wishlist_count"),
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Audit"),
            {"fields": ("uuid", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join and annotate so the list view issues no per-row query."""
        return (
            super()
            .get_queryset(request)
            .select_related("brand", "category", "subcategory")
            .annotate(_variant_count=Count("variants", distinct=True))
        )

    @admin.display(description=_("Image"))
    def image_preview(self, obj: Product) -> str:
        """Primary image thumbnail."""
        image = obj.images.filter(is_primary=True).first()
        return _thumbnail(image.image if image else None, 44)

    @admin.display(description=_("Price"), ordering="selling_price")
    def price_display(self, obj: Product) -> str:
        """Selling price with the MRP struck through when discounted."""
        if obj.discount_percentage > 0:
            return format_html(
                '{} <s style="color:#6b7280;">{}</s> '
                '<b style="color:#15803d;">-{}%</b>',
                obj.selling_price,
                obj.mrp,
                obj.discount_percentage.normalize(),
            )
        return str(obj.selling_price)

    @admin.display(description=_("Stock"), ordering="total_stock")
    def stock_display(self, obj: Product) -> str:
        """Available units, colour-coded by status."""
        variants = getattr(obj, "_variant_count", 0)
        if obj.total_stock <= 0:
            return format_html('<b style="color:#b91c1c;">out</b> ({} var.)', variants)
        if obj.total_stock <= LOW_STOCK_THRESHOLD:
            return format_html(
                '<b style="color:#b45309;">{}</b> ({} var.)', obj.total_stock, variants
            )
        return format_html("{} ({} var.)", obj.total_stock, variants)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    """Admin for variants, used as the inventory screen."""

    list_display = (
        "sku",
        "product_link",
        "color",
        "size",
        "stock",
        "reserved_stock",
        "available",
        "is_active",
    )
    list_editable = ("stock", "reserved_stock", "is_active")
    list_filter = ("is_active", "size", "product__brand", "product__category")
    search_fields = ("sku", "barcode", "color", "product__name", "product__sku")
    ordering = ("product__name", "color", "size")
    autocomplete_fields = ("product",)
    list_per_page = 100
    list_select_related = ("product",)

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join the parent product row."""
        return super().get_queryset(request).select_related("product", "product__brand")

    @admin.display(description=_("Product"), ordering="product__name")
    def product_link(self, obj: ProductVariant) -> str:
        """Link through to the parent product."""
        url = reverse("admin:products_product_change", args=[obj.product_id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    @admin.display(description=_("Available"))
    def available(self, obj: ProductVariant) -> str:
        """Unreserved units, colour-coded."""
        units = obj.available_stock
        if units <= 0:
            return format_html('<b style="color:#b91c1c;">0</b>')
        if units <= LOW_STOCK_THRESHOLD:
            return format_html('<b style="color:#b45309;">{}</b>', units)
        return str(units)


@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin):
    """Admin for merchandising tags."""

    list_display = ("name", "slug", "product_count", "is_active")
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("uuid", "created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Annotate the product count."""
        return super().get_queryset(request).annotate(_product_count=Count("products"))

    @admin.display(description=_("Products"), ordering="_product_count")
    def product_count(self, obj: ProductTag) -> int:
        """Column showing how many products carry a tag."""
        return getattr(obj, "_product_count", 0)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """Standalone image admin, for bulk artwork cleanup."""

    list_display = ("preview", "product", "display_order", "is_primary")
    list_display_links = ("preview", "product")
    list_editable = ("display_order", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("product__name", "product__sku", "alt_text")
    autocomplete_fields = ("product",)
    list_select_related = ("product",)

    @admin.display(description=_("Preview"))
    def preview(self, obj: ProductImage) -> str:
        """Image thumbnail."""
        return _thumbnail(obj.image, 44)
