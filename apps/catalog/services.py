"""Catalog business logic.

Views stay thin: they resolve permissions, hand off to a function here, and
serialise the result. Every query that more than one caller needs — the tree,
the mega menu, each homepage rail — is defined once in this module.

Caching
-------
The tree and the mega menu are rendered on essentially every page view and
change perhaps weekly, which is the textbook case for a read-through cache.
Entries are invalidated on write by :mod:`apps.catalog.signals` rather than
left to expire, so an editor's change appears immediately; the TTL is only a
backstop against a missed invalidation.

The project cache is currently local-memory, which means one cache per worker
process. Invalidation therefore only clears the worker that handled the write.
With a short TTL the others converge within seconds; switching ``CACHES`` to
Redis makes invalidation global and is the right move before scaling out.
"""

from __future__ import annotations

from typing import Any, Iterable

from django.conf import settings
from django.core.cache import cache
from django.db.models import QuerySet

from apps.catalog.models import (
    SEASONAL_COLLECTION_TYPES,
    Brand,
    Category,
    Collection,
    CollectionType,
    SubCategory,
)

#: Bumping this string invalidates every cached catalog entry at once, which is
#: how a deploy that changes the payload shape avoids serving stale structures.
CACHE_VERSION: str = "v1"

CACHE_KEY_TREE: str = f"catalog:{CACHE_VERSION}:tree"
CACHE_KEY_MEGA_MENU: str = f"catalog:{CACHE_VERSION}:mega_menu"
CACHE_KEY_HOMEPAGE: str = f"catalog:{CACHE_VERSION}:homepage"

CACHE_KEYS: tuple[str, ...] = (
    CACHE_KEY_TREE,
    CACHE_KEY_MEGA_MENU,
    CACHE_KEY_HOMEPAGE,
)


def cache_ttl() -> int:
    """Return the catalog cache lifetime in seconds."""
    return getattr(settings, "CATALOG_CACHE_TTL", 300)


def invalidate_catalog_cache() -> None:
    """Drop every cached catalog payload.

    Called from signals whenever any catalog row changes. Deliberately coarse:
    the four models feed the same three payloads, so working out exactly which
    entry a given edit affects would add branching logic for no measurable gain
    on a cache this small.
    """
    cache.delete_many(list(CACHE_KEYS))


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def get_categories(*, include_inactive: bool = False) -> QuerySet[Category]:
    """Return categories in merchandising order.

    ``include_inactive`` is only ever passed by staff-facing callers; the
    public viewset never sets it.
    """
    queryset = Category.objects.all() if include_inactive else Category.objects.active()
    return queryset.ordered()


def get_category_by_slug(slug: str, *, include_inactive: bool = False) -> Category:
    """Return one category by slug, or raise ``Category.DoesNotExist``."""
    queryset = Category.objects.all() if include_inactive else Category.objects.active()
    return queryset.with_subcategories().get(slug=slug)


def get_featured_categories(limit: int | None = None) -> QuerySet[Category]:
    """Return the categories promoted into the homepage featured strip."""
    queryset = Category.objects.active().featured().ordered()
    return queryset[:limit] if limit else queryset


def get_trending_categories(limit: int | None = None) -> QuerySet[Category]:
    """Return the categories editorially marked as trending."""
    queryset = Category.objects.active().trending().ordered()
    return queryset[:limit] if limit else queryset


def get_luxury_categories(limit: int | None = None) -> QuerySet[Category]:
    """Return the categories in the luxury edit."""
    queryset = Category.objects.active().luxury().ordered()
    return queryset[:limit] if limit else queryset


def get_category_tree(*, use_cache: bool = True) -> list[dict[str, Any]]:
    """Return the full Category to SubCategory tree as plain data.

    Returns dictionaries rather than model instances so the result is
    directly cacheable. Pickling querysets into a cache works but stores model
    state that is stale the moment it lands; plain dicts are what the client
    receives anyway.
    """
    if use_cache:
        cached = cache.get(CACHE_KEY_TREE)
        if cached is not None:
            return cached

    tree = [
        {
            "id": str(category.uuid),
            "name": category.name,
            "slug": category.slug,
            "icon": _file_url(category.icon),
            "image": _file_url(category.image),
            "display_order": category.display_order,
            "is_featured": category.is_featured,
            "subcategories": [
                {
                    "id": str(sub.uuid),
                    "name": sub.name,
                    "slug": sub.slug,
                    "image": _file_url(sub.image),
                    "display_order": sub.display_order,
                }
                for sub in category.active_subcategories
            ],
        }
        for category in Category.objects.active().with_subcategories().ordered()
    ]

    if use_cache:
        cache.set(CACHE_KEY_TREE, tree, cache_ttl())
    return tree


def get_mega_menu(*, use_cache: bool = True) -> list[dict[str, Any]]:
    """Return the nested navigation payload for the header mega menu.

    Shape per category: subcategories, featured collections and popular brands
    — the four-column flyout the storefront renders.

    Built from a single prefetching queryset, so the whole menu costs four
    queries regardless of how many categories exist. Assembled naively it would
    be one query per category per column.
    """
    if use_cache:
        cached = cache.get(CACHE_KEY_MEGA_MENU)
        if cached is not None:
            return cached

    menu = [
        {
            "id": str(category.uuid),
            "name": category.name,
            "slug": category.slug,
            "icon": _file_url(category.icon),
            "menu_image": _file_url(category.menu_image),
            "subcategories": [
                {"name": sub.name, "slug": sub.slug}
                for sub in category.active_subcategories
            ],
            "collections": [
                {"title": item.title, "slug": item.slug, "type": item.type}
                for item in category.menu_collections
            ],
            "brands": [
                {"name": brand.name, "slug": brand.slug, "logo": _file_url(brand.logo)}
                for brand in category.menu_brands[:MEGA_MENU_BRAND_LIMIT]
            ],
        }
        for category in Category.objects.active().with_menu_relations().ordered()
    ]

    if use_cache:
        cache.set(CACHE_KEY_MEGA_MENU, menu, cache_ttl())
    return menu


#: Brands shown per category flyout. More than eight overflows the column and
#: the ninth is never clicked.
MEGA_MENU_BRAND_LIMIT: int = 8


# ---------------------------------------------------------------------------
# Subcategories
# ---------------------------------------------------------------------------


def get_subcategories(
    *,
    category_slug: str | None = None,
    include_inactive: bool = False,
) -> QuerySet[SubCategory]:
    """Return subcategories, optionally narrowed to one parent category."""
    queryset = (
        SubCategory.objects.all() if include_inactive else SubCategory.objects.visible()
    )
    if category_slug:
        queryset = queryset.for_category(category_slug)
    return queryset.with_category().ordered()


def get_subcategory_by_slug(
    slug: str,
    *,
    include_inactive: bool = False,
) -> SubCategory:
    """Return one subcategory by slug, or raise ``SubCategory.DoesNotExist``."""
    queryset = (
        SubCategory.objects.all() if include_inactive else SubCategory.objects.visible()
    )
    return queryset.with_category().get(slug=slug)


# ---------------------------------------------------------------------------
# Brands
# ---------------------------------------------------------------------------


def get_brands(*, include_inactive: bool = False) -> QuerySet[Brand]:
    """Return brands in merchandising order."""
    queryset = Brand.objects.all() if include_inactive else Brand.objects.active()
    return queryset.ordered()


def get_featured_brands(limit: int | None = None) -> QuerySet[Brand]:
    """Return brands promoted on the homepage."""
    queryset = Brand.objects.active().featured().ordered()
    return queryset[:limit] if limit else queryset


def get_luxury_brands(limit: int | None = None) -> QuerySet[Brand]:
    """Return brands in the luxury edit."""
    queryset = Brand.objects.active().luxury().ordered()
    return queryset[:limit] if limit else queryset


def get_popular_brands(limit: int | None = None) -> QuerySet[Brand]:
    """Return brands ranked by popularity score.

    ponytail: ranks on the editorially maintained ``popularity_score``. Once
    the orders module exists, replace the column's maintenance with a scheduled
    recompute from real sales volume — the endpoint and its ordering do not
    change, only what feeds the number.
    """
    queryset = Brand.objects.active().popular()
    return queryset[:limit] if limit else queryset


def get_top_brands(limit: int = 12) -> QuerySet[Brand]:
    """Return the homepage's "Top Brands" rail.

    Featured brands first if any are marked, otherwise the most popular — so
    the rail is never empty on a fresh install with no editorial curation yet.
    """
    featured = Brand.objects.active().featured().ordered()
    if featured.exists():
        return featured[:limit]
    return get_popular_brands(limit)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def get_collections(
    *,
    collection_type: str | None = None,
    include_inactive: bool = False,
) -> QuerySet[Collection]:
    """Return collections, optionally narrowed to one type."""
    queryset = (
        Collection.objects.all() if include_inactive else Collection.objects.active()
    )
    if collection_type:
        queryset = queryset.of_type(collection_type)
    return queryset.ordered()


def get_featured_collections(limit: int | None = None) -> QuerySet[Collection]:
    """Return collections promoted on the homepage."""
    queryset = Collection.objects.active().featured().ordered()
    return queryset[:limit] if limit else queryset


def get_seasonal_collections(limit: int | None = None) -> QuerySet[Collection]:
    """Return the season- and festival-driven collections."""
    queryset = Collection.objects.active().seasonal().ordered()
    return queryset[:limit] if limit else queryset


def get_editors_picks(limit: int | None = None) -> QuerySet[Collection]:
    """Return the Editor's Picks collections."""
    queryset = (
        Collection.objects.active().of_type(CollectionType.EDITORS_PICKS).ordered()
    )
    return queryset[:limit] if limit else queryset


def get_homepage_collections() -> dict[str, QuerySet[Collection]]:
    """Return the collection rails the homepage renders, keyed by rail name."""
    return {
        "featured": get_featured_collections(),
        "new_arrivals": Collection.objects.active()
        .of_type(CollectionType.NEW_ARRIVALS)
        .ordered(),
        "trending": Collection.objects.active()
        .of_type(CollectionType.TRENDING)
        .ordered(),
        "best_sellers": Collection.objects.active()
        .of_type(CollectionType.BEST_SELLERS)
        .ordered(),
        "editors_picks": get_editors_picks(),
        "seasonal": get_seasonal_collections(),
    }


# ---------------------------------------------------------------------------
# Homepage aggregate
# ---------------------------------------------------------------------------


def get_homepage_payload() -> dict[str, Any]:
    """Return every catalog rail the homepage needs, in one call.

    A single endpoint rather than eight is the point: the homepage is the most
    latency-sensitive page on the site, and eight sequential round-trips from
    the browser costs far more than the queries themselves.
    """
    collections = get_homepage_collections()
    return {
        "featured_categories": get_featured_categories(),
        "trending_categories": get_trending_categories(),
        "luxury_categories": get_luxury_categories(),
        "top_brands": get_top_brands(),
        "featured_brands": get_featured_brands(limit=12),
        "luxury_brands": get_luxury_brands(limit=12),
        "featured_collections": collections["featured"],
        "editors_picks": collections["editors_picks"],
        "seasonal_collections": collections["seasonal"],
    }


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _file_url(field: Any) -> str | None:
    """Return a file field's URL, or None when no file is attached.

    Accessing ``.url`` on an empty ``ImageField`` raises ``ValueError``, so
    every cached payload has to guard it — and a missing category icon is the
    normal state before an editor uploads artwork, not an error.
    """
    if not field:
        return None
    try:
        return field.url
    except ValueError:  # pragma: no cover - only when storage is misconfigured
        return None


def seasonal_types() -> Iterable[str]:
    """Return the collection types considered seasonal."""
    return SEASONAL_COLLECTION_TYPES
