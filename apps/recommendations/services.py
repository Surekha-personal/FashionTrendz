"""Recommendation business logic.

Two halves. The first tracks and serves a shopper's browsing trail; the second
builds the eight recommendation rails.

Every rail is rule-based — no model training, no vector store, no nightly
pipeline beyond one management command that materialises the co-purchase graph.
The signals a fashion catalogue already stores (taxonomy, brand, price band,
purchase and view counters, ratings, wishlist adds) rank well enough that a
learned model would be a second system to operate for a difference nobody in
the business could measure.

Every rail returns a ``Product`` queryset loaded through
``ProductQuerySet.with_card_data()``, so the API layer can hand any of them to
``ProductCardSerializer`` without knowing which rail it came from.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, QuerySet

from apps.core.choices import OrderStatus
from apps.orders.models import OrderItem
from apps.products.models import Product
from apps.products.services import (
    get_related_products,
    get_similar_products,
    visible_products,
)
from apps.recommendations.models import MAX_RECENTLY_VIEWED, ProductAffinity, RecentlyViewed
from apps.recommendations.scoring import score_products

#: Default rail length. Matches the products module so every strip on the
#: homepage is the same width.
RAIL_SIZE: int = 12

#: How long a computed rail stays cached. Rails are read on every page view and
#: change when a nightly job runs or a counter ticks; a few minutes of staleness
#: is invisible to a shopper and removes most of the query load.
RAIL_CACHE_TTL: int = 300

#: Window for the "recently popular" rail, in days.
RECENT_POPULARITY_DAYS: int = 30

#: Order states that count as a real purchase for affinity and popularity.
#: Pending and cancelled orders are intent and noise respectively.
PURCHASED_ORDER_STATUSES: tuple[str, ...] = (
    OrderStatus.CONFIRMED,
    OrderStatus.PACKED,
    OrderStatus.SHIPPED,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
)


def rail_cache_ttl() -> int:
    """Return the rail cache lifetime in seconds."""
    return int(getattr(settings, "RECOMMENDATION_CACHE_TTL", RAIL_CACHE_TTL))


def max_recently_viewed() -> int:
    """Return how many products a shopper's trail keeps."""
    return int(getattr(settings, "MAX_RECENTLY_VIEWED", MAX_RECENTLY_VIEWED))


# ---------------------------------------------------------------------------
# Recently viewed
# ---------------------------------------------------------------------------


def _owner_filter(*, user: Any = None, session_key: str = "") -> dict[str, Any]:
    """Return the ownership kwargs for a trail row.

    One place decides "user or session", so the create path and the read path
    cannot disagree about which a request belongs to.
    """
    if user is not None and getattr(user, "is_authenticated", False):
        return {"user": user, "session_key": ""}
    return {"user": None, "session_key": session_key}


@transaction.atomic
def record_view(
    product: Product, *, user: Any = None, session_key: str = ""
) -> RecentlyViewed | None:
    """Add a product to a shopper's trail, or move it back to the top.

    Returns ``None`` when there is no owner — a request with neither a signed-in
    user nor a session key has nowhere to store a trail, and silently doing
    nothing is better than raising on what is a fire-and-forget call from a
    product page.

    Bumped in place rather than deleted and re-inserted: the row carries a
    ``view_count`` worth keeping, and re-inserting would churn a primary key on
    every page refresh.
    """
    from django.utils import timezone

    owner = _owner_filter(user=user, session_key=session_key)
    if owner["user"] is None and not owner["session_key"]:
        return None

    try:
        row, created = RecentlyViewed.objects.get_or_create(product=product, **owner)
    except IntegrityError:
        # Two tabs loaded the same product at once. The row exists; that is the
        # desired end state.
        return RecentlyViewed.objects.filter(product=product, **owner).first()

    if not created:
        # One UPDATE moves the row to the top of the rail and counts the visit.
        # ``F()`` so two open tabs both count; ``viewed_at`` set explicitly
        # because ``.update()`` bypasses ``auto_now``.
        RecentlyViewed.objects.filter(pk=row.pk).update(
            view_count=F("view_count") + 1, viewed_at=timezone.now()
        )

    _trim_trail(**owner)
    return row


def _trim_trail(*, user: Any = None, session_key: str = "") -> int:
    """Drop the oldest rows beyond the per-shopper ceiling.

    Trimming on write rather than on a schedule: the trail can only exceed its
    limit immediately after an insert, so this is the one moment it needs
    checking, and it keeps the table from growing between cleanup runs.

    Deleted by primary key from a sliced read — ``delete()`` cannot be called
    on a sliced queryset.
    """
    limit = max_recently_viewed()
    owned = RecentlyViewed.objects.filter(user=user, session_key=session_key).newest()

    surplus = list(owned.values_list("pk", flat=True)[limit:])
    if not surplus:
        return 0
    return RecentlyViewed.objects.filter(pk__in=surplus).delete()[0]


def get_recently_viewed(
    *, user: Any = None, session_key: str = "", limit: int | None = None
) -> list[Product]:
    """Return a shopper's trail as product cards, most recent first.

    Two queries: ids from the trail, then cards from the products module. The
    order comes from the trail and cannot be expressed in the product query, so
    the rows are re-sorted in Python — the same approach
    ``products.services.get_recently_viewed`` uses for the client-side list.
    """
    ids = (
        RecentlyViewed.objects.owned_by(user=user, session_key=session_key)
        .newest()
        .product_ids()
    )[: limit or max_recently_viewed()]

    if not ids:
        return []

    found = {
        product.pk: product
        for product in visible_products().filter(pk__in=ids).with_card_data()
    }
    return [found[pk] for pk in ids if pk in found]


@transaction.atomic
def merge_recently_viewed(user: Any, session_key: str) -> int:
    """Fold a guest's trail into their account on login.

    Guest rows the account already has are dropped rather than merged: the
    account's own ``viewed_at`` is at least as good, and the unique constraint
    would reject the move anyway. The rest are re-pointed with one ``UPDATE``
    instead of a row-by-row save.

    Mirrors ``cart.services.merge_carts`` so a shopper who signs in mid-session
    keeps both their bag and their browsing history.
    """
    if not session_key or not getattr(user, "is_authenticated", False):
        return 0

    guest = RecentlyViewed.objects.filter(user__isnull=True, session_key=session_key)
    already_owned = RecentlyViewed.objects.filter(user=user).values("product_id")

    guest.filter(product_id__in=already_owned).delete()
    moved = guest.update(user=user, session_key="")

    _trim_trail(user=user, session_key="")
    return moved


def clear_recently_viewed(*, user: Any = None, session_key: str = "") -> int:
    """Erase a shopper's trail at their request."""
    return RecentlyViewed.objects.owned_by(
        user=user, session_key=session_key
    ).delete()[0]


def remove_from_recently_viewed(
    product_slug: str, *, user: Any = None, session_key: str = ""
) -> int:
    """Drop one product from the trail."""
    return RecentlyViewed.objects.owned_by(
        user=user, session_key=session_key
    ).filter(product__slug=product_slug).delete()[0]


def purge_stale_trails(days: int = 90) -> int:
    """Delete browsing history older than ``days``.

    The retention job, run from a cron or the management command. Guests first
    because a signed-out trail keyed to an expired session can never be read
    again — it is pure storage.
    """
    return RecentlyViewed.objects.stale(days).delete()[0]


# ---------------------------------------------------------------------------
# Rails
# ---------------------------------------------------------------------------


def _cached(key: str, builder: Any) -> list[Product]:
    """Return a cached rail, materialising it on a miss.

    Rails are cached as lists rather than querysets — a queryset is lazy, so
    caching one would store a promise to run the query later, which is not what
    anybody wants back out of a cache.
    """
    hit = cache.get(key)
    if hit is not None:
        return hit

    value = list(builder())
    cache.set(key, value, rail_cache_ttl())
    return value


def get_related(product: Product, limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Rail 1 — same subcategory, ranked by popularity.

    Delegates to ``products.services.get_related_products``, which already
    implements exactly this. Reimplementing it here would give the store two
    definitions of "related" that drift apart.
    """
    return get_related_products(product, limit=limit)


def get_similar(product: Product, limit: int = RAIL_SIZE) -> QuerySet[Product]:
    """Rail 2 — resembling this one on brand, material, occasion and price.

    Also delegated: ``products.services.get_similar_products`` scores partial
    trait matches rather than requiring all of them, which is what stops the
    rail from coming back empty on most of the catalogue.
    """
    return get_similar_products(product, limit=limit)


def get_frequently_bought_together(
    product: Product, limit: int = 4
) -> list[dict[str, Any]]:
    """Rail 3 — products that shared an order with this one.

    Reads the materialised affinity graph and returns ranked *combinations*,
    each carrying the evidence behind it: how many orders contained both, and
    what share of this product's orders that was. The frontend shows the bundle
    price; the confidence is what a merchandiser needs to trust the rail.

    Falls back to nothing rather than to a generic rail. "Frequently bought
    together" with no co-purchase data is a claim the store cannot support.
    """
    edges = (
        ProductAffinity.objects.for_product(product)
        .strong()
        .visible()
        .ranked()
        .select_related("related_product", "related_product__brand")[:limit]
    )

    return [
        {
            "product": edge.related_product,
            "co_purchase_count": edge.co_purchase_count,
            "confidence": round(edge.score, 3),
            "bundle_price": product.selling_price + edge.related_product.selling_price,
        }
        for edge in edges
    ]


def get_trending(limit: int = RAIL_SIZE) -> list[Product]:
    """Rail 4 — highest trending score across the catalogue.

    The score is documented in :mod:`apps.recommendations.scoring`. Cached,
    because it is the same ranking for every visitor and it is the most
    expensive annotation the module runs.
    """
    return _cached(
        f"reco:trending:{limit}",
        lambda: score_products(visible_products())
        .with_card_data()
        .order_by("-trending_score")[:limit],
    )


def get_recently_popular(
    limit: int = RAIL_SIZE, days: int = RECENT_POPULARITY_DAYS
) -> list[Product]:
    """Rail 5 — most units actually sold in the last ``days``.

    Distinct from trending: this counts orders inside a window and nothing
    else. Trending blends views, wishlists, ratings and recency, so a product
    can trend on attention alone. This rail cannot — it only moves when someone
    pays.
    """
    from django.utils import timezone
    from datetime import timedelta

    since = timezone.now() - timedelta(days=days)

    def build() -> QuerySet[Product]:
        return (
            visible_products()
            .annotate(
                _recent_sales=Count(
                    "order_items",
                    filter=Q(
                        order_items__order__created_at__gte=since,
                        order_items__order__status__in=PURCHASED_ORDER_STATUSES,
                    ),
                )
            )
            .filter(_recent_sales__gt=0)
            .with_card_data()
            .order_by("-_recent_sales", "-purchase_count")[:limit]
        )

    return _cached(f"reco:recent-popular:{days}:{limit}", build)


def get_customers_also_viewed(product: Product, limit: int = RAIL_SIZE) -> list[Product]:
    """Rail 6 — what other shoppers looked at in the same browsing session.

    Read straight off :class:`RecentlyViewed`: find the shoppers who viewed this
    product, then count what else those shoppers viewed. This is collaborative
    filtering at its simplest, and on a catalogue this size it is a two-query
    aggregate rather than a matrix factorisation.

    Falls back to the related rail when the trail data is too thin, which it
    always is on a new store — an empty strip looks broken.
    """
    viewer_rows = RecentlyViewed.objects.filter(product=product)

    also = (
        RecentlyViewed.objects.filter(
            Q(user__in=viewer_rows.filter(user__isnull=False).values("user"))
            | Q(
                session_key__in=viewer_rows.filter(user__isnull=True).values(
                    "session_key"
                )
            )
        )
        .exclude(product=product)
        .values("product_id")
        .annotate(viewers=Count("id"))
        .order_by("-viewers")[: limit * 2]
    )

    ids = [row["product_id"] for row in also]
    if not ids:
        return list(get_related(product, limit=limit))

    found = {
        item.pk: item
        for item in visible_products().filter(pk__in=ids).with_card_data()
    }
    ranked = [found[pk] for pk in ids if pk in found][:limit]

    return ranked or list(get_related(product, limit=limit))


def get_new_for_you(user: Any, limit: int = RAIL_SIZE) -> list[Product]:
    """Rail 7 — recent arrivals in the categories this shopper actually browses.

    "New arrivals" filtered by taste. An unfiltered new-in rail shows a menswear
    shopper this week's sarees; this one reads their trail and their orders for
    the subcategories they engage with, and shows what landed there.

    Signed-out shoppers get plain new arrivals, because there is nothing to
    personalise from.
    """
    if not getattr(user, "is_authenticated", False):
        return list(visible_products().with_card_data().order_by("-published_at")[:limit])

    subcategory_ids = _affinity_subcategories(user)
    queryset = visible_products().with_card_data()

    if subcategory_ids:
        queryset = queryset.filter(subcategory_id__in=subcategory_ids)

    return list(queryset.order_by("-published_at", "-view_count")[:limit])


def get_recommended_for_you(user: Any, limit: int = RAIL_SIZE) -> list[Product]:
    """Rail 8 — the personalised catch-all on the homepage and account page.

    Blends the shopper's revealed taste with what is doing well right now: the
    trending score, restricted to the subcategories and brands they engage
    with, minus what they have already bought or are currently looking at.

    Signed-out or brand-new shoppers get the trending rail. Personalisation
    with no history is just a slower way to show the same list.
    """
    if not getattr(user, "is_authenticated", False):
        return get_trending(limit)

    subcategory_ids = _affinity_subcategories(user)
    brand_ids = _affinity_brands(user)

    if not subcategory_ids and not brand_ids:
        return get_trending(limit)

    taste = Q()
    if subcategory_ids:
        taste |= Q(subcategory_id__in=subcategory_ids)
    if brand_ids:
        taste |= Q(brand_id__in=brand_ids)

    purchased = OrderItem.objects.filter(order__user=user).values("product_id")

    return list(
        score_products(visible_products().filter(taste))
        .exclude(pk__in=purchased)
        .with_card_data()
        .order_by("-trending_score")[:limit]
    )


# ---------------------------------------------------------------------------
# Taste signals
# ---------------------------------------------------------------------------

#: How many subcategories or brands count as a shopper's taste. Wide enough to
#: cover someone who shops for a household, narrow enough that the filter still
#: filters.
TASTE_BREADTH: int = 5


def _affinity_subcategories(user: Any) -> list[int]:
    """Return the subcategories this shopper engages with most.

    Weighted by signal strength: a purchase says more than a wishlist add,
    which says more than a page view. Counted in Python over three small
    queries rather than as one union — the inputs are a handful of rows per
    shopper, and the weighting is clearer written out than expressed in SQL.
    """
    tally: Counter[int] = Counter()

    for product_id, weight in _taste_sources(user):
        tally[product_id] += weight

    if not tally:
        return []

    rows = Product.objects.filter(pk__in=tally).values_list("pk", "subcategory_id")
    by_subcategory: Counter[int] = Counter()
    for product_id, subcategory_id in rows:
        if subcategory_id:
            by_subcategory[subcategory_id] += tally[product_id]

    return [key for key, _ in by_subcategory.most_common(TASTE_BREADTH)]


def _affinity_brands(user: Any) -> list[int]:
    """Return the brands this shopper engages with most."""
    tally: Counter[int] = Counter()

    for product_id, weight in _taste_sources(user):
        tally[product_id] += weight

    if not tally:
        return []

    rows = Product.objects.filter(pk__in=tally).values_list("pk", "brand_id")
    by_brand: Counter[int] = Counter()
    for product_id, brand_id in rows:
        if brand_id:
            by_brand[brand_id] += tally[product_id]

    return [key for key, _ in by_brand.most_common(TASTE_BREADTH)]


#: Relative weights of the three engagement signals.
SIGNAL_WEIGHTS: dict[str, int] = {"purchase": 5, "wishlist": 3, "view": 1}


def _taste_sources(user: Any) -> list[tuple[int, int]]:
    """Return ``(product_id, weight)`` pairs describing what a shopper likes.

    One place reads the three signals, so the two callers above cannot weight
    them differently.
    """
    pairs: list[tuple[int, int]] = [
        (pk, SIGNAL_WEIGHTS["purchase"])
        for pk in OrderItem.objects.filter(order__user=user).values_list(
            "product_id", flat=True
        )[:100]
    ]

    from apps.wishlist.models import WishlistItem

    pairs += [
        (pk, SIGNAL_WEIGHTS["wishlist"])
        for pk in WishlistItem.objects.filter(wishlist__user=user).values_list(
            "product_id", flat=True
        )[:100]
    ]

    pairs += [
        (pk, SIGNAL_WEIGHTS["view"])
        for pk in RecentlyViewed.objects.filter(user=user).values_list(
            "product_id", flat=True
        )[:100]
    ]
    return pairs


# ---------------------------------------------------------------------------
# Affinity graph
# ---------------------------------------------------------------------------


def rebuild_affinities(*, minimum: int = 2) -> dict[str, int]:
    """Recompute the co-purchase graph from order history.

    Run nightly from ``manage.py rebuild_affinities``. Rebuilt wholesale rather
    than maintained incrementally: the whole graph on a catalogue of this size
    is one pass over order lines, and an incremental updater is a second code
    path that silently drifts from the batch one.

    Orders are read as ``(order_id, product_id)`` pairs and paired up in
    Python. The SQL alternative is a self-join of the order-line table against
    itself, which is quadratic in lines-per-order on the database's time rather
    than ours, and far harder to reason about.
    """
    pairs = OrderItem.objects.filter(
        order__status__in=PURCHASED_ORDER_STATUSES
    ).values_list("order_id", "product_id")

    baskets: dict[int, set[int]] = {}
    for order_id, product_id in pairs.iterator(chunk_size=5000):
        baskets.setdefault(order_id, set()).add(product_id)

    co_counts: Counter[tuple[int, int]] = Counter()
    order_counts: Counter[int] = Counter()

    for products in baskets.values():
        for product_id in products:
            order_counts[product_id] += 1
        if len(products) < 2:
            continue
        for left in products:
            for right in products:
                if left != right:
                    co_counts[(left, right)] += 1

    rows = [
        ProductAffinity(
            product_id=left,
            related_product_id=right,
            co_purchase_count=count,
            # Confidence: of the orders containing the left product, what share
            # also contained the right one. Directed on purpose — the same pair
            # scores differently viewed from each side.
            score=count / order_counts[left] if order_counts[left] else 0.0,
        )
        for (left, right), count in co_counts.items()
        if count >= minimum
    ]

    with transaction.atomic():
        ProductAffinity.objects.all().delete()
        ProductAffinity.objects.bulk_create(rows, batch_size=1000)

    return {"baskets": len(baskets), "edges": len(rows)}


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def diagnose(product: Product) -> dict[str, Any]:
    """Explain what the engine would recommend alongside ``product``, and why.

    Powers the admin diagnostics page. Every rail reports its size, so an empty
    strip on the storefront can be traced to the rail that produced nothing
    rather than guessed at.
    """
    from apps.recommendations.scoring import explain_score

    fbt = get_frequently_bought_together(product)

    return {
        "product": product.name,
        "slug": product.slug,
        "trending_score": explain_score(product),
        "signals": {
            "views": product.view_count,
            "purchases": product.purchase_count,
            "wishlist_adds": product.wishlist_count,
            "reviews": product.review_count,
            "rating_average": float(product.rating_average or 0),
            "rating_count": product.rating_count,
        },
        "rails": {
            "related": get_related(product).count(),
            "similar": get_similar(product).count(),
            "frequently_bought_together": len(fbt),
            "customers_also_viewed": len(get_customers_also_viewed(product)),
        },
        "affinity_edges": ProductAffinity.objects.for_product(product).count(),
        "trail_rows": RecentlyViewed.objects.filter(product=product).count(),
    }


def get_trending_dashboard(limit: int = 25) -> list[dict[str, Any]]:
    """Return the admin's trending leaderboard with per-term breakdowns."""
    from apps.recommendations.scoring import explain_score, store_mean_rating

    mean = store_mean_rating()
    ranked = (
        score_products(visible_products())
        .select_related("brand")
        .order_by("-trending_score")[:limit]
    )

    return [
        {
            "rank": position,
            "name": product.name,
            "slug": product.slug,
            "brand": product.brand.name if product.brand_id else "",
            "score": round(getattr(product, "trending_score", 0.0), 4),
            "breakdown": explain_score(product, mean=mean),
        }
        for position, product in enumerate(ranked, start=1)
    ]
