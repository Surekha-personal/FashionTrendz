"""Catalog serializers.

Four tiers, because one serializer cannot serve a mega menu and an admin form
without being wrong for both:

* **Lite** — id, name, slug and one image. What menus, chips and cross-links
  need. Deliberately tiny: the mega menu embeds dozens of these.
* **Public** — the full read payload for a listing or landing page.
* **Nested** — public plus its children, for a category detail page.
* **Admin** — every column including the flags and audit fields, writable.

Field naming: the SEO columns are ``meta_title`` / ``meta_description`` on the
model, inherited from :class:`apps.core.mixins.SEOFieldsMixin`.
:class:`SEOFieldsSerializerMixin` exposes them under the requested ``seo_title``
/ ``seo_description`` names so the database stays free of duplicate columns
while the API reads as specified.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.catalog.models import Brand, Category, Collection, CollectionType, SubCategory


class SEOFieldsSerializerMixin(serializers.Serializer):
    """Expose the inherited meta columns under their public SEO names."""

    seo_title = serializers.CharField(
        source="meta_title", required=False, allow_blank=True, max_length=70
    )
    seo_description = serializers.CharField(
        source="meta_description", required=False, allow_blank=True, max_length=170
    )


# ---------------------------------------------------------------------------
# Lite serializers
# ---------------------------------------------------------------------------


class CategoryLiteSerializer(serializers.ModelSerializer):
    """Minimal category reference for menus and cross-links."""

    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "icon", "image", "display_order")
        read_only_fields = fields


class SubCategoryLiteSerializer(serializers.ModelSerializer):
    """Minimal subcategory reference for menus and cross-links."""

    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = SubCategory
        fields = ("id", "name", "slug", "image", "display_order")
        read_only_fields = fields


class BrandLiteSerializer(serializers.ModelSerializer):
    """Minimal brand reference for menus, chips and product cards."""

    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = Brand
        fields = ("id", "name", "slug", "logo", "is_luxury")
        read_only_fields = fields


class CollectionLiteSerializer(serializers.ModelSerializer):
    """Minimal collection reference for menus and rails."""

    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = Collection
        fields = ("id", "title", "slug", "type", "image")
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Public serializers
# ---------------------------------------------------------------------------


class CategorySerializer(SEOFieldsSerializerMixin, serializers.ModelSerializer):
    """Full public representation of a category."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    subcategory_count = serializers.IntegerField(
        source="active_subcategory_count", read_only=True
    )

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "image",
            "banner_image",
            "menu_image",
            "seo_title",
            "seo_description",
            "is_featured",
            "is_trending",
            "is_luxury",
            "display_order",
            "subcategory_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SubCategorySerializer(SEOFieldsSerializerMixin, serializers.ModelSerializer):
    """Full public representation of a subcategory, with its parent inlined."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    category = CategoryLiteSerializer(read_only=True)

    class Meta:
        model = SubCategory
        fields = (
            "id",
            "category",
            "name",
            "slug",
            "description",
            "image",
            "banner_image",
            "seo_title",
            "seo_description",
            "display_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class BrandSerializer(SEOFieldsSerializerMixin, serializers.ModelSerializer):
    """Full public representation of a brand."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    categories = CategoryLiteSerializer(many=True, read_only=True)

    class Meta:
        model = Brand
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "logo",
            "banner",
            "website",
            "country",
            "founded_year",
            "is_featured",
            "is_luxury",
            "display_order",
            "categories",
            "seo_title",
            "seo_description",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class CollectionSerializer(SEOFieldsSerializerMixin, serializers.ModelSerializer):
    """Full public representation of a collection."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    categories = CategoryLiteSerializer(many=True, read_only=True)
    is_seasonal = serializers.BooleanField(read_only=True)

    class Meta:
        model = Collection
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "type",
            "type_display",
            "is_seasonal",
            "image",
            "banner",
            "is_featured",
            "display_order",
            "categories",
            "seo_title",
            "seo_description",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Nested serializers
# ---------------------------------------------------------------------------


class CategoryDetailSerializer(CategorySerializer):
    """Category plus its active subcategories, for a landing page."""

    subcategories = serializers.SerializerMethodField()

    class Meta(CategorySerializer.Meta):
        fields = CategorySerializer.Meta.fields + ("subcategories",)
        read_only_fields = fields

    def get_subcategories(self, obj: Category) -> list[dict[str, Any]]:
        """Return active children, using the prefetch when the view supplied one."""
        children = getattr(obj, "active_subcategories", None)
        if children is None:
            children = obj.subcategories.filter(is_active=True).order_by(
                "display_order", "name"
            )
        return SubCategoryLiteSerializer(children, many=True, context=self.context).data


class CategoryTreeSerializer(serializers.Serializer):
    """Schema-only description of the ``/categories/tree/`` payload.

    The tree is assembled as plain dictionaries in
    :func:`apps.catalog.services.get_category_tree` so it can be cached
    directly. This class exists purely so drf-spectacular documents the shape;
    it never serialises anything.
    """

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    icon = serializers.CharField(read_only=True, allow_null=True)
    image = serializers.CharField(read_only=True, allow_null=True)
    display_order = serializers.IntegerField(read_only=True)
    is_featured = serializers.BooleanField(read_only=True)
    subcategories = serializers.ListField(child=serializers.DictField(), read_only=True)


class MegaMenuSerializer(serializers.Serializer):
    """Schema-only description of the ``/categories/mega-menu/`` payload."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    icon = serializers.CharField(read_only=True, allow_null=True)
    menu_image = serializers.CharField(read_only=True, allow_null=True)
    subcategories = serializers.ListField(child=serializers.DictField(), read_only=True)
    collections = serializers.ListField(child=serializers.DictField(), read_only=True)
    brands = serializers.ListField(child=serializers.DictField(), read_only=True)


class HomepageSerializer(serializers.Serializer):
    """Every catalog rail the homepage renders, in one payload."""

    featured_categories = CategoryLiteSerializer(many=True, read_only=True)
    trending_categories = CategoryLiteSerializer(many=True, read_only=True)
    luxury_categories = CategoryLiteSerializer(many=True, read_only=True)
    top_brands = BrandLiteSerializer(many=True, read_only=True)
    featured_brands = BrandLiteSerializer(many=True, read_only=True)
    luxury_brands = BrandLiteSerializer(many=True, read_only=True)
    featured_collections = CollectionLiteSerializer(many=True, read_only=True)
    editors_picks = CollectionLiteSerializer(many=True, read_only=True)
    seasonal_collections = CollectionLiteSerializer(many=True, read_only=True)


# ---------------------------------------------------------------------------
# Admin serializers
# ---------------------------------------------------------------------------


class CategoryAdminSerializer(SEOFieldsSerializerMixin, serializers.ModelSerializer):
    """Writable category representation for staff."""

    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "image",
            "banner_image",
            "menu_image",
            "seo_title",
            "seo_description",
            "is_active",
            "is_featured",
            "is_trending",
            "is_luxury",
            "display_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            # Left blank, the model derives it from the name. Editors override
            # it only to preserve an existing URL after a rename.
            "slug": {"required": False, "allow_blank": True},
        }


class SubCategoryAdminSerializer(SEOFieldsSerializerMixin, serializers.ModelSerializer):
    """Writable subcategory representation for staff."""

    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = SubCategory
        fields = (
            "id",
            "category",
            "name",
            "slug",
            "description",
            "image",
            "banner_image",
            "seo_title",
            "seo_description",
            "is_active",
            "display_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {"slug": {"required": False, "allow_blank": True}}

    def get_unique_together_validators(self) -> list[Any]:
        """Suppress DRF's auto-generated unique-together validator.

        DRF derives one from the model's ``UniqueConstraint`` and runs it
        *before* ``validate()``, so it wins and reports
        ``non_field_errors: ["The fields category, name must make a unique
        set."]`` — which no frontend can attach to an input.

        The check in ``validate()`` below replaces it and is strictly stronger:
        it is case-insensitive, so "dresses" and "Dresses" are caught as the
        duplicate a merchandiser means, and it names the offending field.
        Field-level unique validators (on ``slug``) are untouched, and the
        database constraint remains the final guard under concurrency.
        """
        return []

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Reject a duplicate name within the same parent category.

        The database constraint catches this too, but a serializer check turns
        a 409 with a generic message into a 400 naming the offending field.
        """
        category = attrs.get("category") or getattr(self.instance, "category", None)
        name = attrs.get("name") or getattr(self.instance, "name", None)

        if category and name:
            clashes = SubCategory.objects.filter(category=category, name__iexact=name)
            if self.instance is not None:
                clashes = clashes.exclude(pk=self.instance.pk)
            if clashes.exists():
                raise serializers.ValidationError(
                    {"name": "This category already has a subcategory with that name."}
                )
        return attrs


class BrandAdminSerializer(SEOFieldsSerializerMixin, serializers.ModelSerializer):
    """Writable brand representation for staff."""

    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = Brand
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "logo",
            "banner",
            "website",
            "country",
            "founded_year",
            "seo_title",
            "seo_description",
            "is_active",
            "is_featured",
            "is_luxury",
            "display_order",
            "popularity_score",
            "categories",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {"slug": {"required": False, "allow_blank": True}}


class CollectionAdminSerializer(SEOFieldsSerializerMixin, serializers.ModelSerializer):
    """Writable collection representation for staff."""

    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = Collection
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "type",
            "image",
            "banner",
            "seo_title",
            "seo_description",
            "is_active",
            "is_featured",
            "display_order",
            "categories",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {"slug": {"required": False, "allow_blank": True}}

    def validate_type(self, value: str) -> str:
        """Reject a type outside the enumeration."""
        if value not in CollectionType.values:
            raise serializers.ValidationError("Unknown collection type.")
        return value
