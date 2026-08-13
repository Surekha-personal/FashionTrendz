"""Querysets and managers for the products module.

Every recurring filter, every homepage rail's ordering and every prefetch the
API needs is defined once here. Views and services compose these methods rather
than re-deriving the same ``filter()`` calls, so a rule such as "visible means
active *and* published *and* under an active category" cannot drift between the
listing, the search endpoint and the sitemap.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Case, Count, F, Prefetch, Q, Sum, When
from django.utils import timezone


class ProductQuerySet(models.QuerySet):
    """Queries over the product catalogue."""

    # -- Visibility ---------------------------------------------------------

    def active(self) -> "ProductQuerySet":
        """Restrict to products the merchandiser has switched on."""
        return self.filter(is_active=True)

    def published(self) -> "ProductQuerySet":
        """Restrict to products whose publication time has passed.

        ``published_at`` in the future means an embargoed drop. Comparing
        against ``now()`` in SQL rather than filtering in Python is what lets a
        scheduled launch go live without anyone deploying or clicking anything.
        """
        return self.filter(published_at__isnull=False, published_at__lte=timezone.now())

    def visible(self) -> "ProductQuerySet":
        """Restrict to products a customer is allowed to see.

        Active, published, and beneath an active category and subcategory —
        deactivating "Women" has to remove every product under it, not just the
        category tile.
        """
        return self.active().published().filter(
            category__is_active=True,
            subcategory__is_active=True,
        )

    # -- Merchandising flags ------------------------------------------------

    def featured(self) -> "ProductQuerySet":
        """Products promoted on the homepage."""
        return self.filter(is_featured=True)

    def trending(self) -> "ProductQuerySet":
        """Products editorially marked as trending."""
        return self.filter(is_trending=True)

    def best_sellers(self) -> "ProductQuerySet":
        """Products marked as best sellers."""
        return self.filter(is_best_seller=True)

    def new_arrivals(self) -> "ProductQuerySet":
        """Products marked as new arrivals."""
        return self.filter(is_new_arrival=True)

    def luxury(self) -> "ProductQuerySet":
        """Products in the luxury edit."""
        return self.filter(is_luxury=True)

    def recommended(self) -> "ProductQuerySet":
        """Products flagged for the recommendation rail."""
        return self.filter(is_recommended=True)

    def on_sale(self, minimum_percent: Decimal | int = 1) -> "ProductQuerySet":
        """Products discounted by at least ``minimum_percent``."""
        return self.filter(discount_percentage__gte=minimum_percent)

    def in_stock(self) -> "ProductQuerySet":
        """Products with at least one unit available across their variants."""
        return self.filter(total_stock__gt=0)

    # -- Scoping ------------------------------------------------------------

    def for_category(self, slug: str) -> "ProductQuerySet":
        """Restrict to one category, addressed by slug."""
        return self.filter(category__slug=slug)

    def for_subcategory(self, slug: str) -> "ProductQuerySet":
        """Restrict to one subcategory, addressed by slug."""
        return self.filter(subcategory__slug=slug)

    def for_brand(self, slug: str) -> "ProductQuerySet":
        """Restrict to one brand, addressed by slug."""
        return self.filter(brand__slug=slug)

    def for_collection(self, slug: str) -> "ProductQuerySet":
        """Restrict to one editorial collection, addressed by slug."""
        return self.filter(collection__slug=slug)

    def for_tag(self, slug: str) -> "ProductQuerySet":
        """Restrict to products carrying one tag."""
        return self.filter(tags__slug=slug)

    def exclude_self(self, product: models.Model) -> "ProductQuerySet":
        """Drop ``product`` from the result, for related-product rails."""
        return self.exclude(pk=product.pk)

    # -- Loading ------------------------------------------------------------

    def with_card_data(self) -> "ProductQuerySet":
        """Load everything a product *card* renders, and nothing more.

        Three joins and one prefetch. A listing page shows 24 cards; without
        this it costs 24 queries for brands, 24 for categories and 24 for the
        primary image. The image prefetch is filtered to primaries only, so a
        product with twelve gallery shots still transfers one row.
        """
        from apps.products.models import ProductImage

        return self.select_related("brand", "category", "subcategory").prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr="primary_images",
            )
        )

    def with_detail_data(self) -> "ProductQuerySet":
        """Load everything a product *detail* page renders.

        Deliberately heavier than ``with_card_data``: a detail page is one
        product, so the extra prefetches cost five queries total rather than
        five per row.
        """
        from apps.products.models import (
            ProductAttribute,
            ProductImage,
            ProductSpecification,
            ProductVariant,
        )

        return self.select_related(
            "brand", "category", "subcategory", "collection"
        ).prefetch_related(
            Prefetch("images", queryset=ProductImage.objects.order_by("display_order", "id")),
            Prefetch(
                "variants",
                queryset=ProductVariant.objects.filter(is_active=True).order_by(
                    "color", "size"
                ),
            ),
            Prefetch(
                "specifications",
                queryset=ProductSpecification.objects.order_by("display_order", "label"),
            ),
            Prefetch("attributes", queryset=ProductAttribute.objects.order_by("key")),
            "tags",
        )

    def with_stock(self) -> "ProductQuerySet":
        """Annotate live availability from the variant rows.

        ``total_stock`` on the product is a denormalised cache maintained by
        signals. This annotation reads the variants directly, for the places
        that must not trust the cache — the checkout reservation path, and the
        management command that repairs drift.
        """
        return self.annotate(
            live_stock=Sum(
                Case(
                    When(
                        variants__is_active=True,
                        then=F("variants__stock") - F("variants__reserved_stock"),
                    ),
                    default=0,
                    output_field=models.IntegerField(),
                )
            )
        )

    def with_variant_counts(self) -> "ProductQuerySet":
        """Annotate how many distinct colours and sizes a product offers."""
        return self.annotate(
            colour_count=Count(
                "variants__color",
                filter=Q(variants__is_active=True),
                distinct=True,
            ),
            size_count=Count(
                "variants__size",
                filter=Q(variants__is_active=True),
                distinct=True,
            ),
        )

    # -- Ordering -----------------------------------------------------------

    def newest(self) -> "ProductQuerySet":
        """Most recently published first."""
        return self.order_by(F("published_at").desc(nulls_last=True), "-created_at")

    def by_popularity(self) -> "ProductQuerySet":
        """Most purchased, then most viewed.

        Purchases outrank views deliberately: a view is one click of curiosity,
        a purchase is a decision. Ranking on views alone promotes whatever is
        currently linked from an ad.
        """
        return self.order_by("-purchase_count", "-view_count", "-rating_average")

    def cheapest(self) -> "ProductQuerySet":
        """Lowest selling price first."""
        return self.order_by("selling_price", "id")

    def most_expensive(self) -> "ProductQuerySet":
        """Highest selling price first."""
        return self.order_by("-selling_price", "id")

    def best_rated(self) -> "ProductQuerySet":
        """Highest rated first, with unrated products last.

        Sorting on the raw average would put a single five-star review above a
        product with four hundred reviews averaging 4.8. Requiring a minimum
        review count before the rating counts is the standard correction.
        """
        return self.order_by(
            Case(
                When(rating_count__gte=MIN_RATINGS_FOR_RANKING, then=F("rating_average")),
                default=Decimal("0"),
                output_field=models.DecimalField(max_digits=3, decimal_places=2),
            ).desc(),
            "-rating_count",
        )

    def most_discounted(self) -> "ProductQuerySet":
        """Largest discount percentage first."""
        return self.order_by("-discount_percentage", "-purchase_count")

    def most_viewed(self) -> "ProductQuerySet":
        """Most viewed first."""
        return self.order_by("-view_count", "-purchase_count")

    def best_selling(self) -> "ProductQuerySet":
        """Most purchased first."""
        return self.order_by("-purchase_count", "-rating_average")


#: Minimum number of ratings before a product's average is trusted for ranking.
MIN_RATINGS_FOR_RANKING: int = 5


class ProductVariantQuerySet(models.QuerySet):
    """Queries over colour/size variants."""

    def active(self) -> "ProductVariantQuerySet":
        """Restrict to variants a customer can buy."""
        return self.filter(is_active=True)

    def available(self) -> "ProductVariantQuerySet":
        """Restrict to variants with unreserved stock.

        Available stock is on-hand minus reserved. Ignoring reservations is how
        two customers get told the last unit is theirs.
        """
        return self.active().filter(stock__gt=F("reserved_stock"))

    def low_stock(self, threshold: int = 5) -> "ProductVariantQuerySet":
        """Restrict to variants at or below the reorder threshold."""
        return self.active().filter(
            stock__gt=F("reserved_stock"),
            stock__lte=F("reserved_stock") + threshold,
        )

    def out_of_stock(self) -> "ProductVariantQuerySet":
        """Restrict to variants with nothing available."""
        return self.active().filter(stock__lte=F("reserved_stock"))

    def with_product(self) -> "ProductVariantQuerySet":
        """Join the parent product row."""
        return self.select_related("product")


class ProductImageQuerySet(models.QuerySet):
    """Queries over product imagery."""

    def primary(self) -> "ProductImageQuerySet":
        """Restrict to the single primary image per product."""
        return self.filter(is_primary=True)

    def gallery(self) -> "ProductImageQuerySet":
        """Restrict to the non-primary gallery shots, in display order."""
        return self.filter(is_primary=False).order_by("display_order", "id")


ProductManager = models.Manager.from_queryset(ProductQuerySet)
ProductVariantManager = models.Manager.from_queryset(ProductVariantQuerySet)
ProductImageManager = models.Manager.from_queryset(ProductImageQuerySet)
