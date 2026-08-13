"""Product business logic.

Views resolve permissions, call a function here, and serialise the result.
Every rail, listing, search and recommendation query is defined once in this
module so the same rule cannot drift between the homepage, the listing page and
the sitemap.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count, Max, Min, Q, QuerySet
from django.utils import timezone

from apps.catalog.models import Brand, Category
from apps.core.choices import StockStatus
from apps.products.models import (
    LOW_STOCK_THRESHOLD,
    Product,
    ProductTag,
    ProductVariant,
    Size,
)

CACHE_VERSION: str = "v1"
CACHE_KEY_HOMEPAGE: str = f"products:{CACHE_VERSION}:homepage"
CACHE_KEY_FACETS: str = f"products:{CACHE_VERSION}:facets"
CACHE_KEY_TRENDING_SEARCHES: str = f"products:{CACHE_VERSION}:trending_searches"

CACHE_KEYS: tuple[str, ...] = (
    CACHE_KEY_HOMEPAGE,
    CACHE_KEY_FACETS,
    CACHE_KEY_TRENDING_SEARCHES,
)

#: How many items each homepage rail returns.
RAIL_SIZE: int = 12

#: Maximum slugs accepted by the recently-viewed endpoint. The list comes from
#: the client, so it needs a ceiling or one request can ask for the catalogue.
MAX_RECENTLY_VIEWED: int = 24


def cache_ttl() -> int:
    """Return the product cache lifetime in seconds."""
    return getattr(settings, "PRODUCT_CACHE_TTL", 300)


def invalidate_product_cache() -> None:
    """Drop every cached product payload."""
    cache.delete_many(list(CACHE_KEYS))


def visible_products() -> QuerySet[Product]:
    """Return the base queryset every public endpoint starts from."""
    return Product.objects.visible()


# ---------------------------------------------------------------------------
# Homepage rails
# ---------------------------------------------------------------------------


def get_featured_products(limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Products promoted on the homepage."""
    return visible_products().featured().with_card_data().by_popularity()[:limit]


def get_trending_products(limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Products marked as trending."""
    return visible_products().trending().with_card_data().by_popularity()[:limit]


def get_new_arrivals(limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Newest published products, whether or not editorially flagged.

    Falls back to publication order when nothing carries the flag, so the rail
    is never empty on a fresh catalogue.
    """
    flagged = visible_products().new_arrivals().with_card_data().newest()
    if flagged.exists():
        return flagged[:limit]
    return visible_products().with_card_data().newest()[:limit]


def get_best_sellers(limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Products marked as best sellers, ranked by actual purchases."""
    flagged = visible_products().best_sellers().with_card_data().best_selling()
    if flagged.exists():
        return flagged[:limit]
    return visible_products().with_card_data().best_selling()[:limit]


def get_luxury_products(limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Products in the luxury edit, most expensive first."""
    return visible_products().luxury().with_card_data().most_expensive()[:limit]


def get_recommended_products(limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Products flagged for the recommendation rail."""
    return visible_products().recommended().with_card_data().by_popularity()[:limit]


def get_flash_sale_products(
    minimum_discount: Decimal | int = 40,
    limit: int = RAIL_SIZE,
) -> QuerySet[Product]:
    """Heavily discounted, in-stock products.

    In-stock is part of the definition, not a nicety: a flash sale rail whose
    items cannot be bought is the fastest way to lose a customer's trust in the
    whole page.
    """
    return (
        visible_products()
        .on_sale(minimum_discount)
        .in_stock()
        .with_card_data()
        .most_discounted()[:limit]
    )


def get_editors_picks(limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Products inside a collection of the Editor's Picks type."""
    from apps.catalog.models import CollectionType

    return (
        visible_products()
        .filter(collection__type=CollectionType.EDITORS_PICKS)
        .with_card_data()
        .by_popularity()[:limit]
    )


def get_trending_this_week(limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Recently published products ranked by views.

    ponytail: "this week" is approximated by publication recency plus view
    count, because no per-day view history is recorded. When an analytics table
    exists, only this function changes.
    """
    week_ago = timezone.now() - timezone.timedelta(days=7)
    recent = (
        visible_products()
        .filter(published_at__gte=week_ago)
        .with_card_data()
        .most_viewed()
    )
    if recent.exists():
        return recent[:limit]
    return visible_products().with_card_data().most_viewed()[:limit]


def get_recently_added(limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Most recently created products, regardless of publication flags."""
    return visible_products().with_card_data().order_by("-created_at")[:limit]


def get_homepage_payload() -> dict[str, QuerySet[Product]]:
    """Return every product rail the homepage renders, in one call."""
    return {
        "featured": get_featured_products(),
        "trending": get_trending_products(),
        "new_arrivals": get_new_arrivals(),
        "best_sellers": get_best_sellers(),
        "luxury": get_luxury_products(),
        "flash_sale": get_flash_sale_products(),
        "editors_picks": get_editors_picks(),
        "trending_this_week": get_trending_this_week(),
        "recommended": get_recommended_products(),
        "recently_added": get_recently_added(),
    }


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

#: Query-parameter value to queryset-method mapping for ``?sort=``.
SORT_OPTIONS: dict[str, str] = {
    "newest": "newest",
    "popularity": "by_popularity",
    "price_low": "cheapest",
    "price_high": "most_expensive",
    "rating": "best_rated",
    "discount": "most_discounted",
    "views": "most_viewed",
    "best_seller": "best_selling",
}

DEFAULT_SORT: str = "popularity"


def apply_sort(queryset: QuerySet[Product], sort: str | None) -> QuerySet[Product]:
    """Apply a named sort, falling back to popularity for anything unknown.

    Unknown values fall back rather than erroring: a stale bookmark carrying
    ``?sort=cheapest_first`` should still render the page.
    """
    method_name = SORT_OPTIONS.get(sort or DEFAULT_SORT, SORT_OPTIONS[DEFAULT_SORT])
    return getattr(queryset, method_name)()


def get_products_for_category(slug: str) -> QuerySet[Product]:
    """Every visible product under one category."""
    return visible_products().for_category(slug).with_card_data()


def get_products_for_subcategory(slug: str) -> QuerySet[Product]:
    """Every visible product under one subcategory."""
    return visible_products().for_subcategory(slug).with_card_data()


def get_products_for_brand(slug: str) -> QuerySet[Product]:
    """Every visible product from one brand."""
    return visible_products().for_brand(slug).with_card_data()


def get_products_for_collection(slug: str) -> QuerySet[Product]:
    """Every visible product in one collection."""
    return visible_products().for_collection(slug).with_card_data()


def get_sale_products(minimum_discount: Decimal | int = 1) -> QuerySet[Product]:
    """Every discounted product."""
    return visible_products().on_sale(minimum_discount).with_card_data()


# ---------------------------------------------------------------------------
# Detail page
# ---------------------------------------------------------------------------


def get_product_detail(slug: str, *, include_hidden: bool = False) -> Product:
    """Return one product with everything the detail page needs.

    Raises ``Product.DoesNotExist`` when missing or not visible.
    """
    queryset = Product.objects.all() if include_hidden else visible_products()
    return queryset.with_detail_data().get(slug=slug)


def get_related_products(product: Product, limit: int = 8) -> QuerySet[Product]:
    """Products from the same subcategory — "customers also looked at".

    Subcategory rather than category: "Dresses" is a useful neighbourhood,
    "Women" is the entire store.
    """
    return (
        visible_products()
        .filter(subcategory_id=product.subcategory_id)
        .exclude_self(product)
        .with_card_data()
        .by_popularity()[:limit]
    )


def get_similar_products(product: Product, limit: int = 8) -> QuerySet[Product]:
    """Products resembling this one on price, brand or material.

    Scored by counting matching traits rather than requiring all of them: a
    strict AND across brand, material and price band returns nothing for most
    products in a catalogue this size, and an empty "similar" strip looks broken.
    """
    price_floor = product.selling_price * Decimal("0.7")
    price_ceiling = product.selling_price * Decimal("1.3")

    return (
        visible_products()
        .filter(category_id=product.category_id)
        .exclude_self(product)
        .annotate(
            similarity=Count("id", filter=Q(brand_id=product.brand_id))
            + Count("id", filter=Q(material=product.material))
            + Count("id", filter=Q(occasion=product.occasion))
            + Count(
                "id",
                filter=Q(selling_price__gte=price_floor, selling_price__lte=price_ceiling),
            )
        )
        .with_card_data()
        .order_by("-similarity", "-purchase_count")[:limit]
    )


def get_recently_viewed(slugs: Iterable[str]) -> list[Product]:
    """Return products for ``slugs``, preserving the caller's order.

    The list is owned by the client (localStorage), not the server. That avoids
    a table, a cleanup job and a privacy question, and it works for signed-out
    shoppers — who are most of the traffic on a product page.

    Database ordering cannot express "the order they were given", so the rows
    are fetched in one query and re-sorted in Python.
    """
    wanted = [slug for slug in slugs if slug][:MAX_RECENTLY_VIEWED]
    if not wanted:
        return []

    found = {
        product.slug: product
        for product in visible_products().filter(slug__in=wanted).with_card_data()
    }
    return [found[slug] for slug in wanted if slug in found]


def record_product_view(product: Product) -> None:
    """Increment the view counter without a read-modify-write race.

    ``F("view_count") + 1`` is applied by the database, so concurrent viewers
    each add one. Loading the value into Python and saving it back would lose
    increments under exactly the traffic that makes the counter interesting.
    """
    from django.db.models import F

    Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

#: Minimum query length before searching. One or two characters match most of
#: the catalogue and cost a full scan to discover it.
MIN_SEARCH_LENGTH: int = 2


def search_products(query: str) -> QuerySet[Product]:
    """Return products matching ``query`` across name, brand and taxonomy.

    ponytail: ``icontains`` across a handful of columns, ranked by exact-prefix
    then popularity. Portable and correct, but it cannot use a b-tree index for
    the leading-wildcard case, so it degrades on a large catalogue.

    The upgrade path when that bites is PostgreSQL full-text search: add a
    ``SearchVectorField`` with a GIN index, populate it in the same signal that
    already recomputes stock, and replace the ``Q`` chain below with
    ``SearchRank``. No caller changes — they all go through this function.
    """
    from django.db.models import Case, IntegerField, Value, When

    term = (query or "").strip()
    if len(term) < MIN_SEARCH_LENGTH:
        return visible_products().none()

    matches = (
        Q(name__icontains=term)
        | Q(short_description__icontains=term)
        | Q(brand__name__icontains=term)
        | Q(category__name__icontains=term)
        | Q(subcategory__name__icontains=term)
        | Q(tags__name__icontains=term)
        | Q(sku__iexact=term)
    )

    return (
        visible_products()
        .filter(matches)
        .distinct()
        .annotate(
            relevance=Case(
                When(name__iexact=term, then=Value(100)),
                When(name__istartswith=term, then=Value(80)),
                When(name__icontains=term, then=Value(60)),
                When(brand__name__istartswith=term, then=Value(40)),
                default=Value(10),
                output_field=IntegerField(),
            )
        )
        .with_card_data()
        .order_by("-relevance", "-purchase_count", "-rating_average")
    )


def get_search_suggestions(query: str, limit: int = 8) -> dict[str, list[dict[str, str]]]:
    """Return autocomplete suggestions grouped by type.

    Products, brands and categories are returned separately so the dropdown can
    label each group rather than mixing three kinds of result into one list.
    """
    term = (query or "").strip()
    if len(term) < MIN_SEARCH_LENGTH:
        return {"products": [], "brands": [], "categories": []}

    products = [
        {"label": product.name, "slug": product.slug, "type": "product"}
        for product in visible_products()
        .filter(name__icontains=term)
        .by_popularity()
        .only("name", "slug")[:limit]
    ]
    brands = [
        {"label": brand.name, "slug": brand.slug, "type": "brand"}
        for brand in Brand.objects.active()
        .filter(name__icontains=term)
        .only("name", "slug")[:limit]
    ]
    categories = [
        {"label": category.name, "slug": category.slug, "type": "category"}
        for category in Category.objects.active()
        .filter(name__icontains=term)
        .only("name", "slug")[:limit]
    ]

    return {"products": products, "brands": brands, "categories": categories}


def get_popular_products(limit: int = 10) -> QuerySet[Product]:
    """Products shown in an empty search box."""
    return visible_products().with_card_data().by_popularity()[:limit]


def get_trending_searches(limit: int = 10) -> list[str]:
    """Return suggested search terms for an empty search box.

    ponytail: derived from the most popular products' brand and category names
    rather than from a search-log table, which does not exist yet. Cached,
    since it changes daily at most.
    """
    cached = cache.get(CACHE_KEY_TRENDING_SEARCHES)
    if cached is not None:
        return cached

    terms: list[str] = []
    for product in (
        visible_products().select_related("brand", "subcategory").by_popularity()[:40]
    ):
        for candidate in (product.subcategory.name, product.brand.name):
            if candidate not in terms:
                terms.append(candidate)
        if len(terms) >= limit:
            break

    result = terms[:limit]
    cache.set(CACHE_KEY_TRENDING_SEARCHES, result, cache_ttl())
    return result


# ---------------------------------------------------------------------------
# Filter facets
# ---------------------------------------------------------------------------


def get_filter_facets(queryset: QuerySet[Product] | None = None) -> dict[str, Any]:
    """Return the filter options available for a result set.

    Computed from the *current* result set, not the whole catalogue, so the
    sidebar never offers a filter that would return nothing — the single most
    common complaint about faceted navigation.
    """
    products = queryset if queryset is not None else visible_products()

    price_range = products.aggregate(
        min_price=Min("selling_price"), max_price=Max("selling_price")
    )

    brands = list(
        Brand.objects.filter(products__in=products)
        .distinct()
        .annotate(product_count=Count("products", distinct=True))
        .order_by("name")
        .values("name", "slug", "product_count")
    )

    categories = list(
        Category.objects.filter(products__in=products)
        .distinct()
        .annotate(product_count=Count("products", distinct=True))
        .order_by("display_order", "name")
        .values("name", "slug", "product_count")
    )

    colours = list(
        ProductVariant.objects.filter(product__in=products, is_active=True)
        .values("color", "color_code")
        .annotate(product_count=Count("product", distinct=True))
        .order_by("color")
    )

    sizes = list(
        ProductVariant.objects.filter(product__in=products, is_active=True)
        .values("size")
        .annotate(product_count=Count("product", distinct=True))
        .order_by("size")
    )

    materials = list(
        products.exclude(material="")
        .values("material")
        .annotate(product_count=Count("id"))
        .order_by("material")
    )

    return {
        "price": {
            "min": price_range["min_price"] or Decimal("0.00"),
            "max": price_range["max_price"] or Decimal("0.00"),
        },
        "brands": brands,
        "categories": categories,
        "colors": colours,
        "sizes": sizes,
        "materials": materials,
        "discount_buckets": [10, 20, 30, 40, 50, 60, 70],
        "rating_buckets": [4, 3, 2, 1],
        "sort_options": sorted(SORT_OPTIONS),
        "availability": [StockStatus.IN_STOCK, StockStatus.LOW_STOCK],
    }


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def sync_product_stock(product: Product) -> Product:
    """Recompute and persist a product's cached stock figures.

    Called from the variant signals. ``update()`` rather than ``save()`` avoids
    re-entering ``Product.save`` and re-firing the post_save signal, which would
    recurse.
    """
    available = product.compute_stock()
    status = product.derive_stock_status(available)

    Product.objects.filter(pk=product.pk).update(
        total_stock=available, stock_status=status
    )
    product.total_stock = available
    product.stock_status = status
    return product


def get_low_stock_variants(threshold: int = LOW_STOCK_THRESHOLD) -> QuerySet[ProductVariant]:
    """Variants at or below the reorder threshold, for the operations dashboard."""
    return ProductVariant.objects.low_stock(threshold).with_product().order_by(
        "stock", "product__name"
    )


def get_variant_availability(product: Product) -> dict[str, Any]:
    """Return the colour/size availability matrix the product page renders.

    Shaped as colour to sizes so the page can grey out sizes the moment a
    swatch is clicked, without another request.
    """
    matrix: dict[str, dict[str, Any]] = {}

    for variant in product.variants.filter(is_active=True).order_by("color", "size"):
        entry = matrix.setdefault(
            variant.color,
            {"color": variant.color, "color_code": variant.color_code, "sizes": []},
        )
        entry["sizes"].append(
            {
                "size": variant.size,
                "sku": variant.sku,
                "available": variant.available_stock,
                "is_available": variant.is_available,
                "is_low_stock": variant.is_low_stock,
                "price": variant.effective_price,
            }
        )

    return {
        "colors": list(matrix.values()),
        "sizes": sorted({v["size"] for c in matrix.values() for v in c["sizes"]}),
        "total_stock": product.total_stock,
        "stock_status": product.stock_status,
    }


def recompute_rating(product: Product) -> Product:
    """Recompute the cached rating from review rows.

    Delegates to the reviews module, which owns the rule this function cannot
    know about: only **approved** reviews count. Aggregating the raw relation
    here would let a rejected one-star spam review move the number shoppers
    see, and rejecting it later would not move it back.

    Kept as a thin forwarder rather than deleted so existing callers and the
    products admin keep working.
    """
    from apps.reviews.services import recompute_product_rating

    return recompute_product_rating(product)


def get_tags(active_only: bool = True) -> QuerySet[ProductTag]:
    """Return merchandising tags."""
    queryset = ProductTag.objects.all()
    return queryset.filter(is_active=True) if active_only else queryset
