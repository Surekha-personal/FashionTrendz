"""Product serializers.

Five tiers, sized to their surface:

* **Card** — what a listing grid renders. Kept deliberately small: a listing
  page holds 24 of these, so every extra field costs 24x on the wire.
* **QuickView** — card plus variants and the description, for the modal.
* **Detail** — everything the product page needs.
* **Admin** — every column, writable.
* **Satellites** — image, variant, attribute, specification, tag.

SEO naming follows the catalog module: the columns are ``meta_title`` /
``meta_description``; the API exposes ``seo_title`` / ``seo_description``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.catalog.serializers import (
    BrandLiteSerializer,
    CategoryLiteSerializer,
    CollectionLiteSerializer,
    SEOFieldsSerializerMixin,
    SubCategoryLiteSerializer,
)
from apps.products.models import (
    Product,
    ProductAttribute,
    ProductImage,
    ProductSpecification,
    ProductTag,
    ProductVariant,
)


# ---------------------------------------------------------------------------
# Satellites
# ---------------------------------------------------------------------------


class ProductImageSerializer(serializers.ModelSerializer):
    """One product photograph."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    alt_text = serializers.CharField(source="get_alt_text", read_only=True)

    class Meta:
        model = ProductImage
        fields = ("id", "image", "thumbnail", "alt_text", "display_order", "is_primary")
        read_only_fields = fields


class ProductVariantSerializer(serializers.ModelSerializer):
    """A buyable colour/size combination.

    ``stock`` is deliberately absent. Exposing the exact on-hand figure hands
    competitors a live inventory feed; ``available_stock`` (on hand minus
    reservations) and the low-stock flag are what a shopper actually needs.
    """

    id = serializers.UUIDField(source="uuid", read_only=True)
    available_stock = serializers.IntegerField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    price = serializers.DecimalField(
        source="effective_price", max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = ProductVariant
        fields = (
            "id",
            "sku",
            "color",
            "color_code",
            "size",
            "price",
            "image_override",
            "available_stock",
            "is_available",
            "is_low_stock",
        )
        read_only_fields = fields


class ProductAttributeSerializer(serializers.ModelSerializer):
    """A key/value fact about a product."""

    class Meta:
        model = ProductAttribute
        fields = ("key", "value")
        read_only_fields = fields


class ProductSpecificationSerializer(serializers.ModelSerializer):
    """One row of the specification table."""

    class Meta:
        model = ProductSpecification
        fields = ("label", "value", "display_order")
        read_only_fields = fields


class ProductTagSerializer(serializers.ModelSerializer):
    """A merchandising tag."""

    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = ProductTag
        fields = ("id", "name", "slug")
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------


class ProductCardSerializer(serializers.ModelSerializer):
    """The payload a listing grid, rail or search result renders.

    Every field here is one a card actually displays. The long description,
    specifications, attributes and full variant list are excluded — at 24 cards
    a page they would multiply the response size several times over for content
    no pixel shows.
    """

    id = serializers.UUIDField(source="uuid", read_only=True)
    brand = BrandLiteSerializer(read_only=True)
    category = CategoryLiteSerializer(read_only=True)
    subcategory = SubCategoryLiteSerializer(read_only=True)

    primary_image = serializers.SerializerMethodField()
    hover_image = serializers.SerializerMethodField()

    is_on_sale = serializers.BooleanField(read_only=True)
    is_in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "short_description",
            "brand",
            "category",
            "subcategory",
            "primary_image",
            "hover_image",
            "mrp",
            "selling_price",
            "discount_percentage",
            "discount_amount",
            "currency",
            "rating_average",
            "rating_count",
            "review_count",
            "stock_status",
            "is_in_stock",
            "is_on_sale",
            "is_featured",
            "is_new_arrival",
            "is_best_seller",
            "is_trending",
            "is_luxury",
        )
        read_only_fields = fields

    def get_primary_image(self, obj: Product) -> dict[str, Any] | None:
        """Return the card image, using the prefetch when present."""
        image = obj.primary_image
        if image is None:
            return None
        return ProductImageSerializer(image, context=self.context).data

    def get_hover_image(self, obj: Product) -> str | None:
        """Return the second gallery shot, shown on card hover.

        Reads from the prefetched list rather than querying, so a 24-card grid
        does not issue 24 extra queries for a purely decorative image. Returns
        None when the view used the lighter card prefetch.
        """
        images = getattr(obj, "_prefetched_objects_cache", {}).get("images")
        if not images:
            return None

        gallery = [image for image in images if not image.is_primary]
        if not gallery:
            return None

        request = self.context.get("request")
        url = gallery[0].image.url if gallery[0].image else None
        return request.build_absolute_uri(url) if (request and url) else url


# ---------------------------------------------------------------------------
# Quick view and detail
# ---------------------------------------------------------------------------


class ProductQuickViewSerializer(ProductCardSerializer):
    """Card plus what the quick-view modal adds: images and variants."""

    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta(ProductCardSerializer.Meta):
        fields = ProductCardSerializer.Meta.fields + (
            "images",
            "variants",
            "gender",
            "material",
            "fit",
            "is_returnable",
            "estimated_delivery_days",
        )
        read_only_fields = fields


class ProductDetailSerializer(SEOFieldsSerializerMixin, serializers.ModelSerializer):
    """Everything the product detail page renders."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    brand = BrandLiteSerializer(read_only=True)
    category = CategoryLiteSerializer(read_only=True)
    subcategory = SubCategoryLiteSerializer(read_only=True)
    collection = CollectionLiteSerializer(read_only=True)
    tags = ProductTagSerializer(many=True, read_only=True)

    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    specifications = ProductSpecificationSerializer(many=True, read_only=True)

    primary_image = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()

    is_on_sale = serializers.BooleanField(read_only=True)
    is_in_stock = serializers.BooleanField(read_only=True)
    tax_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    material_display = serializers.CharField(
        source="get_material_display", read_only=True
    )
    fit_display = serializers.CharField(source="get_fit_display", read_only=True)
    occasion_display = serializers.CharField(
        source="get_occasion_display", read_only=True
    )

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "sku",
            "short_description",
            "long_description",
            "brand",
            "category",
            "subcategory",
            "collection",
            "tags",
            "images",
            "primary_image",
            "variants",
            "availability",
            "attributes",
            "specifications",
            "mrp",
            "selling_price",
            "discount_percentage",
            "discount_amount",
            "tax_percentage",
            "tax_amount",
            "currency",
            "gender",
            "material",
            "material_display",
            "fit",
            "fit_display",
            "sleeve_type",
            "neck_type",
            "pattern",
            "occasion",
            "occasion_display",
            "season",
            "country_of_origin",
            "weight_grams",
            "dimensions",
            "warranty",
            "care_instructions",
            "return_policy",
            "shipping_info",
            "estimated_delivery_days",
            "rating_average",
            "rating_count",
            "review_count",
            "wishlist_count",
            "stock_status",
            "is_in_stock",
            "is_on_sale",
            "is_featured",
            "is_new_arrival",
            "is_best_seller",
            "is_trending",
            "is_luxury",
            "is_recommended",
            "is_returnable",
            "seo_title",
            "seo_description",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_primary_image(self, obj: Product) -> dict[str, Any] | None:
        """Return the hero image."""
        image = obj.primary_image
        return ProductImageSerializer(image, context=self.context).data if image else None

    def get_availability(self, obj: Product) -> dict[str, Any]:
        """Return the colour/size availability matrix."""
        from apps.products.services import get_variant_availability

        return get_variant_availability(obj)


# ---------------------------------------------------------------------------
# Response shapes for non-model endpoints
# ---------------------------------------------------------------------------


class HomepageProductsSerializer(serializers.Serializer):
    """Every product rail the homepage renders."""

    featured = ProductCardSerializer(many=True, read_only=True)
    trending = ProductCardSerializer(many=True, read_only=True)
    new_arrivals = ProductCardSerializer(many=True, read_only=True)
    best_sellers = ProductCardSerializer(many=True, read_only=True)
    luxury = ProductCardSerializer(many=True, read_only=True)
    flash_sale = ProductCardSerializer(many=True, read_only=True)
    editors_picks = ProductCardSerializer(many=True, read_only=True)
    trending_this_week = ProductCardSerializer(many=True, read_only=True)
    recommended = ProductCardSerializer(many=True, read_only=True)
    recently_added = ProductCardSerializer(many=True, read_only=True)


class SearchSuggestionSerializer(serializers.Serializer):
    """One autocomplete row."""

    label = serializers.CharField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    type = serializers.CharField(read_only=True)


class SearchSuggestionsSerializer(serializers.Serializer):
    """Autocomplete rows grouped by type."""

    products = SearchSuggestionSerializer(many=True, read_only=True)
    brands = SearchSuggestionSerializer(many=True, read_only=True)
    categories = SearchSuggestionSerializer(many=True, read_only=True)


class PriceRangeSerializer(serializers.Serializer):
    """Lowest and highest price in a result set."""

    min = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    max = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)


class FacetOptionSerializer(serializers.Serializer):
    """One selectable filter option with its result count."""

    name = serializers.CharField(read_only=True, required=False)
    slug = serializers.SlugField(read_only=True, required=False)
    product_count = serializers.IntegerField(read_only=True)


class ProductFacetsSerializer(serializers.Serializer):
    """Filter options available for the current result set."""

    price = PriceRangeSerializer(read_only=True)
    brands = FacetOptionSerializer(many=True, read_only=True)
    categories = FacetOptionSerializer(many=True, read_only=True)
    colors = serializers.ListField(child=serializers.DictField(), read_only=True)
    sizes = serializers.ListField(child=serializers.DictField(), read_only=True)
    materials = serializers.ListField(child=serializers.DictField(), read_only=True)
    discount_buckets = serializers.ListField(
        child=serializers.IntegerField(), read_only=True
    )
    rating_buckets = serializers.ListField(
        child=serializers.IntegerField(), read_only=True
    )
    sort_options = serializers.ListField(child=serializers.CharField(), read_only=True)
    availability = serializers.ListField(child=serializers.CharField(), read_only=True)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


class ProductImageAdminSerializer(serializers.ModelSerializer):
    """Writable image representation for staff."""

    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = ProductImage
        fields = (
            "id",
            "product",
            "image",
            "thumbnail",
            "alt_text",
            "display_order",
            "is_primary",
        )
        read_only_fields = ("id",)


class ProductVariantAdminSerializer(serializers.ModelSerializer):
    """Writable variant representation for staff, including raw stock."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    available_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = (
            "id",
            "product",
            "sku",
            "barcode",
            "color",
            "color_code",
            "size",
            "stock",
            "reserved_stock",
            "available_stock",
            "price_override",
            "image_override",
            "weight_grams",
            "is_active",
        )
        read_only_fields = ("id", "available_stock")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Reject a reservation larger than the stock backing it."""
        stock = attrs.get("stock", getattr(self.instance, "stock", 0))
        reserved = attrs.get(
            "reserved_stock", getattr(self.instance, "reserved_stock", 0)
        )
        if reserved > stock:
            raise serializers.ValidationError(
                {"reserved_stock": "Reserved stock cannot exceed stock on hand."}
            )
        return attrs


class ProductAdminSerializer(SEOFieldsSerializerMixin, serializers.ModelSerializer):
    """Writable product representation for staff."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    discount_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    total_stock = serializers.IntegerField(read_only=True)
    stock_status = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "sku",
            "barcode",
            "short_description",
            "long_description",
            "category",
            "subcategory",
            "brand",
            "collection",
            "tags",
            "mrp",
            "selling_price",
            "discount_percentage",
            "discount_amount",
            "tax_percentage",
            "currency",
            "gender",
            "material",
            "fit",
            "sleeve_type",
            "neck_type",
            "pattern",
            "occasion",
            "season",
            "country_of_origin",
            "weight_grams",
            "dimensions",
            "warranty",
            "care_instructions",
            "return_policy",
            "shipping_info",
            "estimated_delivery_days",
            "rating_average",
            "rating_count",
            "review_count",
            "wishlist_count",
            "view_count",
            "purchase_count",
            "total_stock",
            "stock_status",
            "seo_title",
            "seo_description",
            "is_active",
            "is_featured",
            "is_new_arrival",
            "is_best_seller",
            "is_trending",
            "is_luxury",
            "is_recommended",
            "is_returnable",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "discount_percentage",
            "discount_amount",
            "total_stock",
            "stock_status",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {"slug": {"required": False, "allow_blank": True}}

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Check pricing coherence and taxonomy consistency.

        The database enforces both, but a check constraint reports a generic
        409; naming the offending field gives the admin form something to
        highlight.
        """
        mrp = attrs.get("mrp", getattr(self.instance, "mrp", None))
        selling_price = attrs.get(
            "selling_price", getattr(self.instance, "selling_price", None)
        )
        if mrp is not None and selling_price is not None and selling_price > mrp:
            raise serializers.ValidationError(
                {"selling_price": "Selling price cannot be higher than MRP."}
            )

        category = attrs.get("category", getattr(self.instance, "category", None))
        subcategory = attrs.get(
            "subcategory", getattr(self.instance, "subcategory", None)
        )
        if category and subcategory and subcategory.category_id != category.pk:
            raise serializers.ValidationError(
                {
                    "subcategory": (
                        f"'{subcategory.name}' does not belong to '{category.name}'."
                    )
                }
            )

        return attrs
