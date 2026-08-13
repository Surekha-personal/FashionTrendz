"""Django admin for the catalog module.

Every list view is designed to be usable by a merchandiser, not just by a
developer: inline thumbnails, editable ordering and flags directly in the list,
and bulk actions for the operations that are otherwise a hundred clicks.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Brand, Category, Collection, SubCategory


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


class ActivationActionsMixin:
    """Bulk activate / deactivate / feature / unfeature.

    Written as ``queryset.update()`` rather than a Python loop so a thousand
    rows cost one statement. The tradeoff is that ``update()`` does not send
    ``post_save``, so the catalog cache would not be dropped — each action
    therefore invalidates it explicitly.
    """

    @admin.action(description=_("Activate selected"))
    def activate(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Mark every selected row active."""
        self._bulk(request, queryset, {"is_active": True}, _("activated"))

    @admin.action(description=_("Deactivate selected"))
    def deactivate(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Mark every selected row inactive."""
        self._bulk(request, queryset, {"is_active": False}, _("deactivated"))

    @admin.action(description=_("Mark selected as featured"))
    def feature(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Promote every selected row."""
        self._bulk(request, queryset, {"is_featured": True}, _("featured"))

    @admin.action(description=_("Remove featured flag from selected"))
    def unfeature(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Demote every selected row."""
        self._bulk(request, queryset, {"is_featured": False}, _("unfeatured"))

    def _bulk(
        self,
        request: HttpRequest,
        queryset: QuerySet,
        values: dict[str, Any],
        verb: str,
    ) -> None:
        """Apply ``values`` to the queryset and refresh the catalog cache."""
        from apps.catalog.services import invalidate_catalog_cache

        updated = queryset.update(**values)
        invalidate_catalog_cache()
        self.message_user(
            request,
            _("%(count)d record(s) %(verb)s.") % {"count": updated, "verb": verb},
            messages.SUCCESS,
        )


class SubCategoryInline(admin.TabularInline):
    """Edit a category's children from the category page."""

    model = SubCategory
    extra = 0
    fields = ("name", "slug", "display_order", "is_active")
    # No prepopulated slug here: subcategory slugs are prefixed with the parent
    # name ("women-dresses"), which the browser-side prepopulate script cannot
    # know. Leaving the field blank lets the model build the correct value.
    show_change_link = True
    ordering = ("display_order", "name")


@admin.register(Category)
class CategoryAdmin(ActivationActionsMixin, admin.ModelAdmin):
    """Admin for top-level categories."""

    list_display = (
        "icon_preview",
        "name",
        "slug",
        "subcategory_count",
        "display_order",
        "is_active",
        "is_featured",
        "is_trending",
        "is_luxury",
    )
    list_display_links = ("icon_preview", "name")
    # Editable in the list so reordering the whole menu is one save, not one
    # page load per category.
    list_editable = (
        "display_order",
        "is_active",
        "is_featured",
        "is_trending",
        "is_luxury",
    )
    list_filter = ("is_active", "is_featured", "is_trending", "is_luxury")
    search_fields = ("name", "slug", "description", "meta_title")
    ordering = ("display_order", "name")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = (
        "uuid",
        "created_at",
        "updated_at",
        "icon_preview_large",
        "image_preview",
        "banner_preview",
        "menu_preview",
    )
    inlines = [SubCategoryInline]
    actions = ["activate", "deactivate", "feature", "unfeature"]
    list_per_page = 50

    fieldsets = (
        (None, {"fields": ("name", "slug", "description")}),
        (
            _("Artwork"),
            {
                "fields": (
                    ("icon", "icon_preview_large"),
                    ("image", "image_preview"),
                    ("banner_image", "banner_preview"),
                    ("menu_image", "menu_preview"),
                )
            },
        ),
        (
            _("Merchandising"),
            {
                "fields": (
                    "display_order",
                    "is_active",
                    "is_featured",
                    "is_trending",
                    "is_luxury",
                )
            },
        ),
        (
            _("SEO"),
            {"fields": ("meta_title", "meta_description", "meta_keywords")},
        ),
        (
            _("Audit"),
            {"fields": ("uuid", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Annotate the child count so the list view issues no per-row query."""
        return (
            super()
            .get_queryset(request)
            .annotate(_subcategory_count=Count("subcategories", distinct=True))
        )

    @admin.display(description=_("Subcategories"), ordering="_subcategory_count")
    def subcategory_count(self, obj: Category) -> int:
        """Column showing how many children a category has."""
        return getattr(obj, "_subcategory_count", 0)

    @admin.display(description=_("Icon"))
    def icon_preview(self, obj: Category) -> str:
        """Small inline icon for the list view."""
        return _thumbnail(obj.icon, 28)

    @admin.display(description=_("Preview"))
    def icon_preview_large(self, obj: Category) -> str:
        """Icon preview for the change form."""
        return _thumbnail(obj.icon, 80)

    @admin.display(description=_("Preview"))
    def image_preview(self, obj: Category) -> str:
        """Tile preview for the change form."""
        return _thumbnail(obj.image, 120)

    @admin.display(description=_("Preview"))
    def banner_preview(self, obj: Category) -> str:
        """Banner preview for the change form."""
        return _thumbnail(obj.banner_image, 90)

    @admin.display(description=_("Preview"))
    def menu_preview(self, obj: Category) -> str:
        """Menu-panel preview for the change form."""
        return _thumbnail(obj.menu_image, 90)


@admin.register(SubCategory)
class SubCategoryAdmin(ActivationActionsMixin, admin.ModelAdmin):
    """Admin for second-level categories."""

    list_display = (
        "image_preview",
        "name",
        "category",
        "slug",
        "display_order",
        "is_active",
    )
    list_display_links = ("image_preview", "name")
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name", "slug", "description", "category__name")
    ordering = ("category__display_order", "display_order", "name")
    # Deliberately not prepopulated — see SubCategoryInline. "Dresses" exists
    # under both Women and Kids, so a name-only slug would collide.
    autocomplete_fields = ("category",)
    readonly_fields = ("uuid", "created_at", "updated_at", "image_preview_large", "banner_preview")
    # is_featured does not exist on this model, so the feature actions are
    # deliberately omitted rather than inherited and left to fail.
    actions = ["activate", "deactivate"]
    list_per_page = 50

    fieldsets = (
        (None, {"fields": ("category", "name", "slug", "description")}),
        (
            _("Artwork"),
            {"fields": (("image", "image_preview_large"), ("banner_image", "banner_preview"))},
        ),
        (_("Merchandising"), {"fields": ("display_order", "is_active")}),
        (_("SEO"), {"fields": ("meta_title", "meta_description", "meta_keywords")}),
        (
            _("Audit"),
            {"fields": ("uuid", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join the parent so the list view does not issue N+1 queries."""
        return super().get_queryset(request).select_related("category")

    @admin.display(description=_("Image"))
    def image_preview(self, obj: SubCategory) -> str:
        """Small inline thumbnail for the list view."""
        return _thumbnail(obj.image, 28)

    @admin.display(description=_("Preview"))
    def image_preview_large(self, obj: SubCategory) -> str:
        """Tile preview for the change form."""
        return _thumbnail(obj.image, 120)

    @admin.display(description=_("Preview"))
    def banner_preview(self, obj: SubCategory) -> str:
        """Banner preview for the change form."""
        return _thumbnail(obj.banner_image, 90)


@admin.register(Brand)
class BrandAdmin(ActivationActionsMixin, admin.ModelAdmin):
    """Admin for brands."""

    list_display = (
        "logo_preview",
        "name",
        "country",
        "founded_year",
        "popularity_score",
        "display_order",
        "is_active",
        "is_featured",
        "is_luxury",
    )
    list_display_links = ("logo_preview", "name")
    list_editable = (
        "popularity_score",
        "display_order",
        "is_active",
        "is_featured",
        "is_luxury",
    )
    list_filter = ("is_active", "is_featured", "is_luxury", "country")
    search_fields = ("name", "slug", "description", "country")
    ordering = ("display_order", "name")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("categories",)
    readonly_fields = ("uuid", "created_at", "updated_at", "logo_preview_large", "banner_preview")
    actions = ["activate", "deactivate", "feature", "unfeature", "mark_luxury", "unmark_luxury"]
    list_per_page = 50

    fieldsets = (
        (None, {"fields": ("name", "slug", "description")}),
        (_("Artwork"), {"fields": (("logo", "logo_preview_large"), ("banner", "banner_preview"))}),
        (_("Profile"), {"fields": ("website", "country", "founded_year", "categories")}),
        (
            _("Merchandising"),
            {
                "fields": (
                    "display_order",
                    "popularity_score",
                    "is_active",
                    "is_featured",
                    "is_luxury",
                )
            },
        ),
        (_("SEO"), {"fields": ("meta_title", "meta_description", "meta_keywords")}),
        (
            _("Audit"),
            {"fields": ("uuid", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    @admin.action(description=_("Mark selected as luxury"))
    def mark_luxury(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Add every selected brand to the luxury edit."""
        self._bulk(request, queryset, {"is_luxury": True}, _("marked as luxury"))

    @admin.action(description=_("Remove luxury flag from selected"))
    def unmark_luxury(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Remove every selected brand from the luxury edit."""
        self._bulk(request, queryset, {"is_luxury": False}, _("removed from luxury"))

    @admin.display(description=_("Logo"))
    def logo_preview(self, obj: Brand) -> str:
        """Small inline logo for the list view."""
        return _thumbnail(obj.logo, 28)

    @admin.display(description=_("Preview"))
    def logo_preview_large(self, obj: Brand) -> str:
        """Logo preview for the change form."""
        return _thumbnail(obj.logo, 100)

    @admin.display(description=_("Preview"))
    def banner_preview(self, obj: Brand) -> str:
        """Banner preview for the change form."""
        return _thumbnail(obj.banner, 90)


@admin.register(Collection)
class CollectionAdmin(ActivationActionsMixin, admin.ModelAdmin):
    """Admin for editorial collections."""

    list_display = (
        "image_preview",
        "title",
        "type",
        "display_order",
        "is_active",
        "is_featured",
    )
    list_display_links = ("image_preview", "title")
    list_editable = ("display_order", "is_active", "is_featured")
    list_filter = ("is_active", "is_featured", "type")
    search_fields = ("title", "slug", "description")
    ordering = ("display_order", "title")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("categories",)
    readonly_fields = ("uuid", "created_at", "updated_at", "image_preview_large", "banner_preview")
    actions = ["activate", "deactivate", "feature", "unfeature"]
    list_per_page = 50

    fieldsets = (
        (None, {"fields": ("title", "slug", "type", "description")}),
        (_("Artwork"), {"fields": (("image", "image_preview_large"), ("banner", "banner_preview"))}),
        (
            _("Merchandising"),
            {"fields": ("display_order", "is_active", "is_featured", "categories")},
        ),
        (_("SEO"), {"fields": ("meta_title", "meta_description", "meta_keywords")}),
        (
            _("Audit"),
            {"fields": ("uuid", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    @admin.display(description=_("Image"))
    def image_preview(self, obj: Collection) -> str:
        """Small inline thumbnail for the list view."""
        return _thumbnail(obj.image, 28)

    @admin.display(description=_("Preview"))
    def image_preview_large(self, obj: Collection) -> str:
        """Tile preview for the change form."""
        return _thumbnail(obj.image, 120)

    @admin.display(description=_("Preview"))
    def banner_preview(self, obj: Collection) -> str:
        """Banner preview for the change form."""
        return _thumbnail(obj.banner, 90)
