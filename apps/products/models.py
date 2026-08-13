"""Product catalogue models.

Six models: :class:`Product` and its five satellites — images, variants,
attributes, specifications and tags.

Every model reuses :class:`apps.core.mixins.BaseModel` (timestamps + public
UUID); :class:`Product` and :class:`ProductTag` add
:class:`apps.core.mixins.SEOFieldsMixin` for the slug and meta tags. As in the
catalog module, the API exposes ``meta_title`` / ``meta_description`` under the
``seo_title`` / ``seo_description`` names via a serializer alias.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Brand, Category, Collection, SubCategory
from apps.catalog.utils import UploadPath
from apps.core.choices import Currency, Gender, StockStatus
from apps.core.constants import (
    DEFAULT_CURRENCY,
    PRICE_DECIMAL_PLACES,
    PRICE_MAX_DIGITS,
)
from apps.core.mixins import BaseModel, SEOFieldsMixin
from apps.core.utils import generate_unique_slug, quantise_money
from apps.core.validators import validate_no_html, validate_price
from apps.products.managers import (
    ProductImageManager,
    ProductManager,
    ProductVariantManager,
)
from apps.products.validators import (
    barcode_validator,
    dimensions_validator,
    sku_validator,
    validate_product_image,
    validate_stock,
    validate_thumbnail_image,
)

product_image_path = UploadPath("products/images")
product_thumbnail_path = UploadPath("products/thumbnails")
variant_image_path = UploadPath("products/variants")


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Material(models.TextChoices):
    """Primary fabric or material a product is made from."""

    COTTON = "cotton", _("Cotton")
    LINEN = "linen", _("Linen")
    SILK = "silk", _("Silk")
    WOOL = "wool", _("Wool")
    DENIM = "denim", _("Denim")
    LEATHER = "leather", _("Leather")
    POLYESTER = "polyester", _("Polyester")
    RAYON = "rayon", _("Rayon")
    VISCOSE = "viscose", _("Viscose")
    GEORGETTE = "georgette", _("Georgette")
    CHIFFON = "chiffon", _("Chiffon")
    VELVET = "velvet", _("Velvet")
    SATIN = "satin", _("Satin")
    KHADI = "khadi", _("Khadi")
    BLENDED = "blended", _("Blended")
    OTHER = "other", _("Other")


class Fit(models.TextChoices):
    """How a garment sits on the body."""

    SLIM = "slim", _("Slim fit")
    REGULAR = "regular", _("Regular fit")
    RELAXED = "relaxed", _("Relaxed fit")
    OVERSIZED = "oversized", _("Oversized")
    BODYCON = "bodycon", _("Bodycon")
    A_LINE = "a_line", _("A-line")
    STRAIGHT = "straight", _("Straight")
    TAPERED = "tapered", _("Tapered")


class SleeveType(models.TextChoices):
    """Sleeve construction."""

    SLEEVELESS = "sleeveless", _("Sleeveless")
    CAP = "cap", _("Cap sleeve")
    SHORT = "short", _("Short sleeve")
    THREE_QUARTER = "three_quarter", _("Three-quarter sleeve")
    LONG = "long", _("Long sleeve")
    PUFF = "puff", _("Puff sleeve")
    BELL = "bell", _("Bell sleeve")
    NOT_APPLICABLE = "na", _("Not applicable")


class NeckType(models.TextChoices):
    """Neckline shape."""

    ROUND = "round", _("Round neck")
    V_NECK = "v_neck", _("V-neck")
    COLLARED = "collared", _("Collared")
    BOAT = "boat", _("Boat neck")
    SQUARE = "square", _("Square neck")
    HALTER = "halter", _("Halter neck")
    MANDARIN = "mandarin", _("Mandarin collar")
    SWEETHEART = "sweetheart", _("Sweetheart")
    NOT_APPLICABLE = "na", _("Not applicable")


class Pattern(models.TextChoices):
    """Surface print or weave."""

    SOLID = "solid", _("Solid")
    PRINTED = "printed", _("Printed")
    FLORAL = "floral", _("Floral")
    STRIPED = "striped", _("Striped")
    CHECKED = "checked", _("Checked")
    EMBROIDERED = "embroidered", _("Embroidered")
    COLOURBLOCK = "colourblock", _("Colourblock")
    ANIMAL = "animal", _("Animal print")
    ABSTRACT = "abstract", _("Abstract")
    WOVEN = "woven", _("Woven design")


class Occasion(models.TextChoices):
    """Where a piece is meant to be worn."""

    CASUAL = "casual", _("Casual")
    FORMAL = "formal", _("Formal")
    PARTY = "party", _("Party")
    WEDDING = "wedding", _("Wedding")
    FESTIVE = "festive", _("Festive")
    SPORTS = "sports", _("Sports")
    LOUNGE = "lounge", _("Lounge")
    BEACH = "beach", _("Beach")
    WORK = "work", _("Work")


class Season(models.TextChoices):
    """Season a product is merchandised for."""

    SUMMER = "summer", _("Summer")
    WINTER = "winter", _("Winter")
    MONSOON = "monsoon", _("Monsoon")
    SPRING = "spring", _("Spring")
    AUTUMN = "autumn", _("Autumn")
    ALL_SEASON = "all_season", _("All season")


class Size(models.TextChoices):
    """Size label carried by a variant.

    Apparel and numeric footwear sizes share one enumeration because a variant
    row carries exactly one size whatever the product type, and a second column
    would be null for every row of the other type.
    """

    XS = "XS", _("XS")
    S = "S", _("S")
    M = "M", _("M")
    L = "L", _("L")
    XL = "XL", _("XL")
    XXL = "XXL", _("XXL")
    XXXL = "3XL", _("3XL")
    FREE = "FREE", _("Free size")
    UK6 = "UK6", _("UK 6")
    UK7 = "UK7", _("UK 7")
    UK8 = "UK8", _("UK 8")
    UK9 = "UK9", _("UK 9")
    UK10 = "UK10", _("UK 10")
    UK11 = "UK11", _("UK 11")


#: Units at or below which a variant is reported as "low stock" on the PDP.
LOW_STOCK_THRESHOLD: int = 5


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class ProductTag(BaseModel, SEOFieldsMixin):
    """A free-form merchandising label such as "linen-edit" or "under-1999".

    Distinct from ``Collection``: a collection is an editorial page with its own
    artwork and hero, a tag is a lightweight cross-cut used for chips, filters
    and campaign landing pages.
    """

    name = models.CharField(
        _("name"), max_length=80, unique=True, validators=[validate_no_html]
    )
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    class Meta:
        verbose_name = _("product tag")
        verbose_name_plural = _("product tags")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Fill in the slug on first save."""
        if not self.slug:
            self.slug = generate_unique_slug(
                ProductTag, self.name, instance_pk=self.pk
            )
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


class Product(BaseModel, SEOFieldsMixin):
    """A sellable item in the catalogue.

    Colour and size live on :class:`ProductVariant`, so the product row carries
    everything shared across variants — description, brand, pricing and the
    denormalised counters the storefront ranks on.
    """

    # -- Identity -----------------------------------------------------------

    name = models.CharField(
        _("name"), max_length=200, db_index=True, validators=[validate_no_html]
    )
    short_description = models.CharField(
        _("short description"),
        max_length=300,
        blank=True,
        help_text=_("One-line summary shown on cards and in quick view."),
    )
    long_description = models.TextField(_("long description"), blank=True)

    sku = models.CharField(
        _("SKU"), max_length=50, unique=True, validators=[sku_validator]
    )
    barcode = models.CharField(
        _("barcode"), max_length=14, blank=True, validators=[barcode_validator]
    )

    # -- Taxonomy -----------------------------------------------------------
    # PROTECT throughout: a category with sold products must not be deletable,
    # because that would orphan or destroy the order history referencing it.
    # Deactivating is the intended way to retire a category.

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("category"),
    )
    subcategory = models.ForeignKey(
        SubCategory,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("subcategory"),
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("brand"),
    )
    collection = models.ForeignKey(
        Collection,
        on_delete=models.SET_NULL,
        related_name="products",
        null=True,
        blank=True,
        verbose_name=_("collection"),
        help_text=_("Optional editorial collection this product belongs to."),
    )
    tags = models.ManyToManyField(
        ProductTag, related_name="products", blank=True, verbose_name=_("tags")
    )

    # -- Pricing ------------------------------------------------------------
    # discount_percentage and discount_amount are derived from mrp and
    # selling_price in save(). They are stored rather than computed on read
    # because "sort by discount" and "filter discount >= 40%" have to happen
    # in SQL across the whole catalogue, not in Python over a fetched page.

    mrp = models.DecimalField(
        _("MRP"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        validators=[validate_price],
        help_text=_("Maximum retail price, before discount."),
    )
    selling_price = models.DecimalField(
        _("selling price"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        db_index=True,
        validators=[validate_price],
    )
    discount_percentage = models.DecimalField(
        _("discount percentage"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        db_index=True,
        editable=False,
        help_text=_("Derived from MRP and selling price on save."),
    )
    discount_amount = models.DecimalField(
        _("discount amount"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
        editable=False,
    )
    tax_percentage = models.DecimalField(
        _("tax percentage"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    currency = models.CharField(
        _("currency"),
        max_length=3,
        choices=Currency.choices,
        default=DEFAULT_CURRENCY,
    )

    # -- Attributes ---------------------------------------------------------

    gender = models.CharField(
        _("gender"),
        max_length=12,
        choices=Gender.choices,
        default=Gender.UNISEX,
        db_index=True,
    )
    material = models.CharField(
        _("material"), max_length=16, choices=Material.choices, blank=True, db_index=True
    )
    fit = models.CharField(_("fit"), max_length=12, choices=Fit.choices, blank=True)
    sleeve_type = models.CharField(
        _("sleeve type"), max_length=16, choices=SleeveType.choices, blank=True
    )
    neck_type = models.CharField(
        _("neck type"), max_length=16, choices=NeckType.choices, blank=True
    )
    pattern = models.CharField(
        _("pattern"), max_length=16, choices=Pattern.choices, blank=True
    )
    occasion = models.CharField(
        _("occasion"), max_length=12, choices=Occasion.choices, blank=True, db_index=True
    )
    season = models.CharField(
        _("season"),
        max_length=12,
        choices=Season.choices,
        default=Season.ALL_SEASON,
        db_index=True,
    )

    # -- Logistics ----------------------------------------------------------

    country_of_origin = models.CharField(
        _("country of origin"), max_length=100, blank=True, validators=[validate_no_html]
    )
    weight_grams = models.PositiveIntegerField(
        _("weight (grams)"),
        null=True,
        blank=True,
        help_text=_("Shipping weight, used for courier rate calculation."),
    )
    dimensions = models.CharField(
        _("dimensions"),
        max_length=60,
        blank=True,
        validators=[dimensions_validator],
        help_text=_("Packed size as 'L x W x H' in centimetres."),
    )
    warranty = models.CharField(_("warranty"), max_length=150, blank=True)
    care_instructions = models.TextField(_("care instructions"), blank=True)
    return_policy = models.CharField(_("return policy"), max_length=200, blank=True)
    shipping_info = models.CharField(_("shipping info"), max_length=200, blank=True)
    estimated_delivery_days = models.PositiveSmallIntegerField(
        _("estimated delivery (days)"), default=5
    )

    # -- Denormalised counters ----------------------------------------------
    # Maintained by signals and the recompute service. Stored on the row
    # because every listing sorts and filters on them; computing them with a
    # subquery per request would put an aggregate over the review table into
    # the hot path of every category page.

    rating_average = models.DecimalField(
        _("rating average"),
        max_digits=3,
        decimal_places=2,
        default=Decimal("0.00"),
        db_index=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("5"))],
    )
    rating_count = models.PositiveIntegerField(_("rating count"), default=0)
    review_count = models.PositiveIntegerField(_("review count"), default=0)
    wishlist_count = models.PositiveIntegerField(_("wishlist count"), default=0)
    view_count = models.PositiveIntegerField(_("view count"), default=0, db_index=True)
    purchase_count = models.PositiveIntegerField(
        _("purchase count"), default=0, db_index=True
    )
    total_stock = models.IntegerField(
        _("total available stock"),
        default=0,
        db_index=True,
        editable=False,
        help_text=_("Sum of active variant stock minus reservations."),
    )
    stock_status = models.CharField(
        _("stock status"),
        max_length=16,
        choices=StockStatus.choices,
        default=StockStatus.OUT_OF_STOCK,
        db_index=True,
        editable=False,
    )

    # -- Flags --------------------------------------------------------------

    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    is_featured = models.BooleanField(_("featured"), default=False, db_index=True)
    is_new_arrival = models.BooleanField(_("new arrival"), default=False, db_index=True)
    is_best_seller = models.BooleanField(_("best seller"), default=False, db_index=True)
    is_trending = models.BooleanField(_("trending"), default=False, db_index=True)
    is_luxury = models.BooleanField(_("luxury"), default=False, db_index=True)
    is_recommended = models.BooleanField(_("recommended"), default=False, db_index=True)
    is_returnable = models.BooleanField(_("returnable"), default=True)

    published_at = models.DateTimeField(
        _("published at"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Products are hidden until this time passes. Blank means unpublished."),
    )

    objects = ProductManager()

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["-published_at", "-created_at"]
        indexes = [
            # The storefront's default read: visible products, newest first.
            models.Index(
                fields=["is_active", "-published_at"], name="product_visible_new_idx"
            ),
            # Category and subcategory listing pages.
            models.Index(
                fields=["category", "is_active", "-published_at"],
                name="product_cat_listing_idx",
            ),
            models.Index(
                fields=["subcategory", "is_active", "-published_at"],
                name="product_subcat_listing_idx",
            ),
            models.Index(
                fields=["brand", "is_active", "-published_at"],
                name="product_brand_listing_idx",
            ),
            # Price filter plus sort, the most common combination on a listing.
            models.Index(
                fields=["is_active", "selling_price"], name="product_price_idx"
            ),
            models.Index(
                fields=["is_active", "-discount_percentage"], name="product_discount_idx"
            ),
            models.Index(
                fields=["is_active", "-rating_average"], name="product_rating_idx"
            ),
            models.Index(
                fields=["is_active", "-purchase_count"], name="product_bestseller_idx"
            ),
            # Homepage rails.
            models.Index(fields=["is_featured", "is_active"], name="product_featured_idx"),
            models.Index(fields=["is_trending", "is_active"], name="product_trending_idx"),
            models.Index(
                fields=["is_new_arrival", "is_active"], name="product_newarrival_idx"
            ),
            models.Index(fields=["is_luxury", "is_active"], name="product_luxury_idx"),
            models.Index(fields=["gender", "is_active"], name="product_gender_idx"),
        ]
        constraints = [
            # The database, not just the form, refuses a selling price above
            # MRP — that combination renders as a negative discount badge and
            # is the kind of thing a bulk import produces at 2am.
            models.CheckConstraint(
                condition=models.Q(selling_price__lte=models.F("mrp")),
                name="product_selling_price_not_above_mrp",
            ),
            models.CheckConstraint(
                condition=models.Q(mrp__gte=Decimal("0")),
                name="product_mrp_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.brand.name} {self.name}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Fill in the slug and recompute the derived discount fields.

        Discount is derived here rather than being editable, so the three
        pricing numbers can never disagree. An editable discount field is how a
        catalogue ends up with a product marked "40% off" whose prices imply 12%.
        """
        if not self.slug:
            # Brand-prefixed, matching how shoppers search ("nordwyn linen
            # shirt") and keeping two labels' identically-named shirts apart
            # without a random suffix.
            brand_name = self.brand.name if self.brand_id else ""
            self.slug = generate_unique_slug(
                Product, f"{brand_name} {self.name}".strip(), instance_pk=self.pk
            )

        self.mrp = quantise_money(self.mrp, self.currency)
        self.selling_price = quantise_money(self.selling_price, self.currency)

        if self.mrp > 0 and self.selling_price <= self.mrp:
            self.discount_amount = quantise_money(
                self.mrp - self.selling_price, self.currency
            )
            self.discount_percentage = (
                (self.discount_amount / self.mrp) * Decimal("100")
            ).quantize(Decimal("0.01"))
        else:
            self.discount_amount = Decimal("0.00")
            self.discount_percentage = Decimal("0.00")

        super().save(*args, **kwargs)

    # -- Derived values -----------------------------------------------------

    @property
    def is_published(self) -> bool:
        """Return whether the publication time has passed."""
        return self.published_at is not None and self.published_at <= timezone.now()

    @property
    def is_visible(self) -> bool:
        """Return whether a customer may see this product."""
        return self.is_active and self.is_published

    @property
    def is_in_stock(self) -> bool:
        """Return whether any variant has unreserved stock."""
        return self.total_stock > 0

    @property
    def is_on_sale(self) -> bool:
        """Return whether the product carries a discount."""
        return self.discount_percentage > 0

    @property
    def tax_amount(self) -> Decimal:
        """Return the tax component of the selling price."""
        return quantise_money(
            self.selling_price * self.tax_percentage / Decimal("100"), self.currency
        )

    @property
    def primary_image(self) -> "ProductImage | None":
        """Return the primary image, preferring a prefetched one."""
        prefetched = getattr(self, "primary_images", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return self.images.filter(is_primary=True).first()

    def compute_stock(self) -> int:
        """Return live available stock summed across active variants."""
        aggregate = self.variants.filter(is_active=True).aggregate(
            available=models.Sum(models.F("stock") - models.F("reserved_stock"))
        )
        return max(aggregate["available"] or 0, 0)

    def derive_stock_status(self, available: int | None = None) -> str:
        """Return the label matching ``available`` units."""
        units = self.compute_stock() if available is None else available
        if units <= 0:
            return StockStatus.OUT_OF_STOCK
        if units <= LOW_STOCK_THRESHOLD:
            return StockStatus.LOW_STOCK
        return StockStatus.IN_STOCK


# ---------------------------------------------------------------------------
# Satellites
# ---------------------------------------------------------------------------


class ProductImage(BaseModel):
    """One photograph belonging to a product."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("product"),
    )
    image = models.ImageField(
        _("image"), upload_to=product_image_path, validators=[validate_product_image]
    )
    thumbnail = models.ImageField(
        _("thumbnail"),
        upload_to=product_thumbnail_path,
        blank=True,
        null=True,
        validators=[validate_thumbnail_image],
        help_text=_("Generated on save from the full image if left blank."),
    )
    alt_text = models.CharField(
        _("alt text"),
        max_length=200,
        blank=True,
        help_text=_("Screen-reader description. Falls back to the product name."),
    )
    display_order = models.PositiveSmallIntegerField(
        _("display order"), default=0, db_index=True
    )
    is_primary = models.BooleanField(_("primary"), default=False, db_index=True)

    objects = ProductImageManager()

    class Meta:
        verbose_name = _("product image")
        verbose_name_plural = _("product images")
        ordering = ["-is_primary", "display_order", "id"]
        constraints = [
            # Partial unique index: one primary image per product, enforced in
            # the database so two concurrent "make this primary" clicks cannot
            # leave a product with two hero shots.
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="unique_primary_image_per_product",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "display_order"], name="image_product_order_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} image {self.display_order}"

    def get_alt_text(self) -> str:
        """Return alt text, falling back to the product name."""
        return self.alt_text or self.product.name


class ProductVariant(BaseModel):
    """A buyable colour/size combination of a product.

    The variant, not the product, is what a cart line and an order line point
    at — a customer buys "Blue, size M", not "the shirt".
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("product"),
    )
    sku = models.CharField(
        _("SKU"), max_length=50, unique=True, validators=[sku_validator]
    )
    barcode = models.CharField(
        _("barcode"), max_length=14, blank=True, validators=[barcode_validator]
    )

    color = models.CharField(_("colour"), max_length=40, db_index=True)
    color_code = models.CharField(
        _("colour code"),
        max_length=7,
        blank=True,
        help_text=_("Hex swatch shown on the product page, e.g. #1E3A8A."),
    )
    size = models.CharField(
        _("size"), max_length=8, choices=Size.choices, db_index=True
    )

    stock = models.PositiveIntegerField(
        _("stock on hand"), default=0, validators=[validate_stock]
    )
    reserved_stock = models.PositiveIntegerField(
        _("reserved stock"),
        default=0,
        help_text=_("Units held by in-flight checkouts and unshipped orders."),
    )

    price_override = models.DecimalField(
        _("price override"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        null=True,
        blank=True,
        validators=[validate_price],
        help_text=_("Set only when this variant costs more than the base product."),
    )
    image_override = models.ImageField(
        _("variant image"),
        upload_to=variant_image_path,
        blank=True,
        null=True,
        validators=[validate_product_image],
        help_text=_("Swatch-specific photograph, shown when this colour is selected."),
    )
    weight_grams = models.PositiveIntegerField(
        _("weight (grams)"), null=True, blank=True
    )
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    objects = ProductVariantManager()

    class Meta:
        verbose_name = _("product variant")
        verbose_name_plural = _("product variants")
        ordering = ["product", "color", "size"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "color", "size"],
                name="unique_variant_per_product",
            ),
            # Reserved can never exceed on-hand, or available stock goes
            # negative and the PDP shows "-3 left".
            models.CheckConstraint(
                condition=models.Q(reserved_stock__lte=models.F("stock")),
                name="variant_reserved_not_above_stock",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "is_active"], name="variant_product_idx"),
            models.Index(fields=["color"], name="variant_color_idx"),
            models.Index(fields=["size"], name="variant_size_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} - {self.color} / {self.size}"

    @property
    def available_stock(self) -> int:
        """Return on-hand stock minus reservations, never below zero."""
        return max(self.stock - self.reserved_stock, 0)

    @property
    def is_available(self) -> bool:
        """Return whether this variant can be added to a cart."""
        return self.is_active and self.available_stock > 0

    @property
    def is_low_stock(self) -> bool:
        """Return whether availability has fallen to the warning threshold."""
        return 0 < self.available_stock <= LOW_STOCK_THRESHOLD

    @property
    def effective_price(self) -> Decimal:
        """Return the variant's price, falling back to the product's."""
        return self.price_override if self.price_override is not None else self.product.selling_price


class ProductAttribute(BaseModel):
    """A free-form key/value fact about a product.

    For facts that vary per product and are not worth a column — "Thread count",
    "Lining", "Closure". Structured, filterable properties belong on
    :class:`Product` as real fields, where they can be indexed.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="attributes",
        verbose_name=_("product"),
    )
    key = models.CharField(_("key"), max_length=80, validators=[validate_no_html])
    value = models.CharField(_("value"), max_length=255, validators=[validate_no_html])

    class Meta:
        verbose_name = _("product attribute")
        verbose_name_plural = _("product attributes")
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "key"], name="unique_attribute_key_per_product"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.key}: {self.value}"


class ProductSpecification(BaseModel):
    """An ordered row in the product page's specification table."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="specifications",
        verbose_name=_("product"),
    )
    label = models.CharField(_("label"), max_length=80, validators=[validate_no_html])
    value = models.CharField(_("value"), max_length=255, validators=[validate_no_html])
    display_order = models.PositiveSmallIntegerField(_("display order"), default=0)

    class Meta:
        verbose_name = _("product specification")
        verbose_name_plural = _("product specifications")
        ordering = ["display_order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "label"], name="unique_specification_label_per_product"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.label}: {self.value}"
