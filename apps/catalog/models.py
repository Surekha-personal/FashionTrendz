"""Catalog models: Category, SubCategory, Brand and Collection.

All four inherit :class:`apps.core.mixins.BaseModel` (timestamps + public UUID)
and :class:`apps.core.mixins.SEOFieldsMixin` (slug + meta tags), so Module 3's
abstractions supply every shared column and no field is declared twice.

Note on naming: the SEO columns are ``meta_title`` / ``meta_description``,
inherited from ``SEOFieldsMixin``. The API exposes them as ``seo_title`` /
``seo_description`` through a serializer alias — see
:class:`apps.catalog.serializers.SEOFieldsSerializerMixin`.
"""

from __future__ import annotations

from typing import Any

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalog.managers import (
    BrandManager,
    CategoryManager,
    CollectionManager,
    SubCategoryManager,
)
from apps.catalog.utils import (
    brand_banner_path,
    brand_logo_path,
    build_brand_slug,
    build_category_slug,
    build_collection_slug,
    build_subcategory_slug,
    category_banner_path,
    category_icon_path,
    category_image_path,
    category_menu_path,
    collection_banner_path,
    collection_image_path,
    subcategory_banner_path,
    subcategory_image_path,
)
from apps.catalog.validators import (
    validate_banner_image,
    validate_display_order,
    validate_founded_year,
    validate_icon_image,
    validate_tile_image,
)
from apps.core.mixins import BaseModel, SEOFieldsMixin
from apps.core.validators import validate_no_html


class CollectionType(models.TextChoices):
    """Editorial bucket a collection belongs to.

    Drives which homepage rail a collection renders in, so the frontend needs
    no hard-coded list of collection titles.
    """

    NEW_ARRIVALS = "new_arrivals", _("New Arrivals")
    TRENDING = "trending", _("Trending")
    LUXURY = "luxury", _("Luxury")
    EDITORS_PICKS = "editors_picks", _("Editor's Picks")
    BEST_SELLERS = "best_sellers", _("Best Sellers")
    FESTIVAL = "festival", _("Festival Collection")
    WEDDING = "wedding", _("Wedding Collection")
    SUMMER = "summer", _("Summer Collection")
    WINTER = "winter", _("Winter Collection")


#: Types the ``/collections/seasonal/`` endpoint returns. Defined next to the
#: enum so the grouping is not re-derived in a view, a serializer and a
#: template and allowed to disagree.
SEASONAL_COLLECTION_TYPES: frozenset[str] = frozenset(
    {
        CollectionType.FESTIVAL,
        CollectionType.WEDDING,
        CollectionType.SUMMER,
        CollectionType.WINTER,
    }
)


class Category(BaseModel, SEOFieldsMixin):
    """A top-level department such as Women, Men or Footwear.

    The root of the navigation tree: Category to SubCategory to Product.
    """

    name = models.CharField(
        _("name"),
        max_length=120,
        unique=True,
        validators=[validate_no_html],
    )
    description = models.TextField(_("description"), blank=True)

    icon = models.ImageField(
        _("icon"),
        upload_to=category_icon_path,
        blank=True,
        null=True,
        validators=[validate_icon_image],
        help_text=_("Small square glyph shown in the mega menu."),
    )
    image = models.ImageField(
        _("tile image"),
        upload_to=category_image_path,
        blank=True,
        null=True,
        validators=[validate_tile_image],
        help_text=_("Card artwork for category grids."),
    )
    banner_image = models.ImageField(
        _("banner image"),
        upload_to=category_banner_path,
        blank=True,
        null=True,
        validators=[validate_banner_image],
        help_text=_("Full-width hero on the category landing page."),
    )
    menu_image = models.ImageField(
        _("menu image"),
        upload_to=category_menu_path,
        blank=True,
        null=True,
        validators=[validate_tile_image],
        help_text=_("Promotional panel inside the mega menu flyout."),
    )

    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    is_featured = models.BooleanField(_("featured"), default=False, db_index=True)
    is_trending = models.BooleanField(_("trending"), default=False, db_index=True)
    is_luxury = models.BooleanField(_("luxury"), default=False, db_index=True)

    display_order = models.PositiveSmallIntegerField(
        _("display order"),
        default=0,
        db_index=True,
        validators=[validate_display_order],
        help_text=_("Lower numbers appear first."),
    )

    objects = CategoryManager()

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["display_order", "name"]
        indexes = [
            # Backs the storefront's "active, in merchandising order" read,
            # which is the single most frequent query in the module.
            models.Index(
                fields=["is_active", "display_order"],
                name="category_active_order_idx",
            ),
            models.Index(
                fields=["is_featured", "is_active"],
                name="category_featured_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Fill in the slug on first save if an editor did not supply one."""
        if not self.slug:
            self.slug = build_category_slug(self.name, instance_pk=self.pk)
        super().save(*args, **kwargs)

    @property
    def active_subcategory_count(self) -> int:
        """Return the number of visible children.

        Prefers the ``with_counts()`` annotation and the ``with_subcategories()``
        prefetch when either is present, so rendering a list never issues one
        query per row.
        """
        annotated = getattr(self, "subcategory_count", None)
        if annotated is not None:
            return annotated

        prefetched = getattr(self, "active_subcategories", None)
        if prefetched is not None:
            return len(prefetched)

        return self.subcategories.filter(is_active=True).count()


class SubCategory(BaseModel, SEOFieldsMixin):
    """A second-level grouping such as Dresses under Women."""

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="subcategories",
        verbose_name=_("category"),
    )
    name = models.CharField(
        _("name"),
        max_length=120,
        validators=[validate_no_html],
    )
    description = models.TextField(_("description"), blank=True)

    image = models.ImageField(
        _("tile image"),
        upload_to=subcategory_image_path,
        blank=True,
        null=True,
        validators=[validate_tile_image],
    )
    banner_image = models.ImageField(
        _("banner image"),
        upload_to=subcategory_banner_path,
        blank=True,
        null=True,
        validators=[validate_banner_image],
    )

    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    display_order = models.PositiveSmallIntegerField(
        _("display order"),
        default=0,
        db_index=True,
        validators=[validate_display_order],
    )

    objects = SubCategoryManager()

    class Meta:
        verbose_name = _("subcategory")
        verbose_name_plural = _("subcategories")
        ordering = ["category__display_order", "display_order", "name"]
        constraints = [
            # A category may not hold two children with the same name. The slug
            # is separately unique globally (from SEOFieldsMixin); this guards
            # the human-facing label, which the slug alone would not, because
            # slug generation would happily append a suffix and produce two
            # "Dresses" entries in one menu.
            models.UniqueConstraint(
                fields=["category", "name"],
                name="unique_subcategory_name_per_category",
            ),
        ]
        indexes = [
            models.Index(
                fields=["category", "is_active", "display_order"],
                name="subcat_cat_active_order_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category.name} / {self.name}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Fill in the parent-scoped slug on first save."""
        if not self.slug:
            self.slug = build_subcategory_slug(
                self.category, self.name, instance_pk=self.pk
            )
        super().save(*args, **kwargs)

    @property
    def is_visible(self) -> bool:
        """Return whether this row and its parent are both active."""
        return self.is_active and self.category.is_active


class Brand(BaseModel, SEOFieldsMixin):
    """A label whose products the storefront sells."""

    name = models.CharField(
        _("name"),
        max_length=120,
        unique=True,
        validators=[validate_no_html],
    )
    description = models.TextField(_("description"), blank=True)

    logo = models.ImageField(
        _("logo"),
        upload_to=brand_logo_path,
        blank=True,
        null=True,
        validators=[validate_tile_image],
    )
    banner = models.ImageField(
        _("banner"),
        upload_to=brand_banner_path,
        blank=True,
        null=True,
        validators=[validate_banner_image],
    )

    website = models.URLField(_("website"), max_length=255, blank=True)
    country = models.CharField(
        _("country of origin"),
        max_length=100,
        blank=True,
        validators=[validate_no_html],
    )
    founded_year = models.PositiveSmallIntegerField(
        _("founded year"),
        null=True,
        blank=True,
        validators=[validate_founded_year],
    )

    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    is_featured = models.BooleanField(_("featured"), default=False, db_index=True)
    is_luxury = models.BooleanField(_("luxury"), default=False, db_index=True)

    display_order = models.PositiveSmallIntegerField(
        _("display order"),
        default=0,
        db_index=True,
        validators=[validate_display_order],
    )
    popularity_score = models.PositiveIntegerField(
        _("popularity score"),
        default=0,
        db_index=True,
        help_text=_(
            "Ranking weight for the 'popular brands' rail. Maintained "
            "editorially until order data exists to derive it from."
        ),
    )

    # Which departments a brand is merchandised under. Drives the "popular
    # brands" column of each category's mega-menu flyout.
    categories = models.ManyToManyField(
        Category,
        related_name="brands",
        blank=True,
        verbose_name=_("categories"),
    )

    objects = BrandManager()

    class Meta:
        verbose_name = _("brand")
        verbose_name_plural = _("brands")
        ordering = ["display_order", "name"]
        indexes = [
            models.Index(
                fields=["is_active", "display_order"],
                name="brand_active_order_idx",
            ),
            models.Index(
                fields=["is_active", "-popularity_score"],
                name="brand_popularity_idx",
            ),
            models.Index(
                fields=["is_luxury", "is_active"],
                name="brand_luxury_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Fill in the slug on first save if an editor did not supply one."""
        if not self.slug:
            self.slug = build_brand_slug(self.name, instance_pk=self.pk)
        super().save(*args, **kwargs)


class Collection(BaseModel, SEOFieldsMixin):
    """An editorial grouping of products, such as "Wedding Edit"."""

    title = models.CharField(
        _("title"),
        max_length=150,
        unique=True,
        validators=[validate_no_html],
    )
    description = models.TextField(_("description"), blank=True)

    type = models.CharField(
        _("type"),
        max_length=24,
        choices=CollectionType.choices,
        default=CollectionType.NEW_ARRIVALS,
        db_index=True,
    )

    image = models.ImageField(
        _("tile image"),
        upload_to=collection_image_path,
        blank=True,
        null=True,
        validators=[validate_tile_image],
    )
    banner = models.ImageField(
        _("banner"),
        upload_to=collection_banner_path,
        blank=True,
        null=True,
        validators=[validate_banner_image],
    )

    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    is_featured = models.BooleanField(
        _("featured"),
        default=False,
        db_index=True,
        help_text=_("Show this collection on the homepage and in the mega menu."),
    )
    display_order = models.PositiveSmallIntegerField(
        _("display order"),
        default=0,
        db_index=True,
        validators=[validate_display_order],
    )

    categories = models.ManyToManyField(
        Category,
        related_name="collections",
        blank=True,
        verbose_name=_("categories"),
    )

    objects = CollectionManager()

    class Meta:
        verbose_name = _("collection")
        verbose_name_plural = _("collections")
        ordering = ["display_order", "title"]
        indexes = [
            models.Index(
                fields=["is_active", "display_order"],
                name="collection_active_order_idx",
            ),
            models.Index(
                fields=["type", "is_active"],
                name="collection_type_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Fill in the slug on first save if an editor did not supply one."""
        if not self.slug:
            self.slug = build_collection_slug(self.title, instance_pk=self.pk)
        super().save(*args, **kwargs)

    @property
    def is_seasonal(self) -> bool:
        """Return whether this collection is season- or festival-driven."""
        return self.type in SEASONAL_COLLECTION_TYPES
