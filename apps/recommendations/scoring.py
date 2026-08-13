"""The trending-score algorithm.

A single, documented, reusable scoring function. Everything that needs to rank
products by momentum — the trending rail, the "recently popular" rail, the
admin dashboard, the recommendation fallback — calls in here, so there is one
formula to tune and one place to explain when merchandising asks why a product
is at position three.

The score
=========

For each product::

    score = W_view      * ln(1 + views)
          + W_purchase  * ln(1 + purchases)
          + W_wishlist  * ln(1 + wishlist_adds)
          + W_review    * ln(1 + review_count)
          + W_rating    * bayesian_rating
          + W_recency   * freshness

Why each piece is shaped the way it is:

**Logarithms on the counters.** Raw counts make the ranking a popularity
ratchet: one product with 40,000 views outranks everything else on views alone
for as long as the store exists, and nothing new can ever surface. ``ln(1+x)``
means the step from 10 to 100 views is worth the same as the step from 100 to
1,000 — momentum, not accumulated total. ``1 +`` keeps ``ln(0)`` finite.

**Purchases weigh most.** A view is one click of curiosity, possibly from an
ad. A purchase is a decision backed by money. A wishlist add sits between:
intent without commitment.

**Bayesian rating, not the raw average.** A single five-star review is a 5.0
average and would beat a product with four hundred reviews at 4.6. The prior
pulls thin evidence toward the store mean and lets real evidence override it::

    bayesian = (C * m + sum_of_ratings) / (C + rating_count)

where ``m`` is the store-wide mean rating and ``C`` is the number of reviews
worth of prior. At ``C = 10``, a product needs about ten reviews before its own
average dominates. This is the IMDb weighted-rating formula, and it is here for
the same reason IMDb uses it.

**Recency decay.** Momentum is time-bounded. A product's freshness falls off
with a half-life so that last quarter's hit stops occupying the trending rail::

    freshness = 0.5 ** floor(days_since_published / HALF_LIFE_DAYS)

At the default 30-day half-life a two-month-old product contributes a quarter
of the recency term a brand-new one does. Note that only this term decays —
a genuinely popular older product still ranks on its counters.

The curve is sampled once per half-life rather than computed continuously,
because a continuous version needs the age of a row as a number of seconds and
extracting an epoch from a datetime difference is PostgreSQL-only. See
``_freshness_expression`` for the trade.

Tuning
======

Every weight reads from settings, so merchandising can be re-tuned in ``.env``
without a deploy::

    TRENDING_WEIGHT_VIEW=1.0
    TRENDING_WEIGHT_PURCHASE=3.0
    TRENDING_WEIGHT_WISHLIST=2.0
    TRENDING_WEIGHT_REVIEW=1.5
    TRENDING_WEIGHT_RATING=2.0
    TRENDING_WEIGHT_RECENCY=4.0
    TRENDING_HALF_LIFE_DAYS=30
    TRENDING_RATING_PRIOR=10

Where it runs
=============

In the database, as an annotation, not in Python. ``score_products`` returns an
annotated queryset so ranking a catalogue of thousands costs one query and
sorting happens in Postgres. Pulling every product into Python to score it
would work on the seed data and fall over on the real catalogue.

The only Python-side value is ``store_mean_rating``, one cached aggregate
shared by every product in the ranking.
"""

from __future__ import annotations

import math
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import (
    Avg,
    Case,
    ExpressionWrapper,
    F,
    FloatField,
    Func,
    Q,
    QuerySet,
    Value,
    When,
)
from django.db.models.functions import Cast
from django.utils import timezone

from apps.products.models import Product

#: How long the store-wide mean rating is cached. It moves glacially — one new
#: review against thousands — so re-aggregating it per request buys nothing.
STORE_MEAN_TTL: int = 3600

STORE_MEAN_CACHE_KEY = "recommendations:store_mean_rating"

#: Fallback store mean for an empty catalogue. Neutral rather than optimistic:
#: on a store with no reviews the rating term should not favour anyone.
DEFAULT_STORE_MEAN: float = 3.5


class Ln(Func):
    """``LN(x)`` — natural logarithm, available in both Postgres and SQLite."""

    function = "LN"
    arity = 1
    output_field = FloatField()


def _weight(name: str, default: float) -> float:
    """Read one tunable weight from settings."""
    return float(getattr(settings, name, default))


def weights() -> dict[str, float]:
    """Return the current scoring weights.

    Exposed as a function rather than module constants so a settings override
    in a test or a changed ``.env`` takes effect without a reimport.
    """
    return {
        "view": _weight("TRENDING_WEIGHT_VIEW", 1.0),
        "purchase": _weight("TRENDING_WEIGHT_PURCHASE", 3.0),
        "wishlist": _weight("TRENDING_WEIGHT_WISHLIST", 2.0),
        "review": _weight("TRENDING_WEIGHT_REVIEW", 1.5),
        "rating": _weight("TRENDING_WEIGHT_RATING", 2.0),
        "recency": _weight("TRENDING_WEIGHT_RECENCY", 4.0),
        "half_life_days": _weight("TRENDING_HALF_LIFE_DAYS", 30.0),
        "rating_prior": _weight("TRENDING_RATING_PRIOR", 10.0),
    }


def store_mean_rating(*, use_cache: bool = True) -> float:
    """Return the catalogue-wide mean rating, cached.

    The ``m`` in the Bayesian formula: what we assume about a product before
    its own reviews tell us otherwise. Averaged over products that actually
    have ratings — including the unrated ones as zero would drag the prior to
    near-nothing and defeat the smoothing.
    """
    if use_cache:
        cached = cache.get(STORE_MEAN_CACHE_KEY)
        if cached is not None:
            return float(cached)

    mean = (
        Product.objects.filter(rating_count__gt=0)
        .aggregate(mean=Avg("rating_average"))
        .get("mean")
    )
    value = float(mean) if mean else DEFAULT_STORE_MEAN

    if use_cache:
        cache.set(STORE_MEAN_CACHE_KEY, value, STORE_MEAN_TTL)
    return value


def invalidate_store_mean() -> None:
    """Drop the cached store mean. Called when ratings change materially."""
    cache.delete(STORE_MEAN_CACHE_KEY)


def _log(field: str) -> Func:
    """Return ``LN(1 + field)`` as a float expression."""
    return Ln(Cast(F(field), FloatField()) + Value(1.0))


#: How many half-lives the freshness ladder covers before flooring at zero.
#: Seven is where ``0.5 ** 7`` (0.008) stops being distinguishable from nothing.
FRESHNESS_STEPS: int = 7


def _freshness_expression(half_life_days: float) -> Case:
    """Return the recency term as a portable SQL expression.

    The curve is ``0.5 ** (age_days / half_life)``, sampled once per half-life
    and expressed as a ``CASE`` over precomputed timestamp cutoffs.

    Computing it exactly would need ``age`` as a number of seconds, and
    extracting an epoch from a datetime difference is PostgreSQL-specific —
    which would leave this module unable to run under SQLite in tests. Python
    does the datetime arithmetic instead and SQL only compares ``published_at``
    against constants, so the comparison uses the existing index and the
    expression works on every backend.

    The cost is resolution: a product 31 days old scores the same as one 59
    days old at a 30-day half-life. For ranking a rail of twelve products, a
    half-life of granularity is well below the noise in the counters.
    """
    now = timezone.now()

    # Branch ``step`` matches products younger than ``(step + 1)`` half-lives
    # and scores them ``0.5 ** step``. ``CASE`` takes the first match, so the
    # branches must run youngest-first — which ``range`` already does.
    #
    # The null arm covers drafts and legacy rows with no ``published_at``;
    # ``created_at`` stands in for them.
    branches = [
        When(
            Q(published_at__gte=now - timedelta(days=half_life_days * (step + 1)))
            | Q(
                published_at__isnull=True,
                created_at__gte=now - timedelta(days=half_life_days * (step + 1)),
            ),
            then=Value(0.5**step),
        )
        for step in range(FRESHNESS_STEPS)
    ]
    return Case(*branches, default=Value(0.0), output_field=FloatField())


def score_products(
    queryset: QuerySet[Product] | None = None, *, mean: float | None = None
) -> QuerySet[Product]:
    """Annotate ``trending_score`` onto a product queryset.

    The single entry point. Callers add their own filters and ordering::

        score_products(visible_products()).order_by("-trending_score")[:12]

    Every term is computed in SQL, so this stays one query regardless of
    catalogue size.
    """
    products = Product.objects.visible() if queryset is None else queryset
    w = weights()
    m = store_mean_rating() if mean is None else mean
    prior = w["rating_prior"]

    # Bayesian rating: (C*m + sum_of_ratings) / (C + n), where the stored
    # average times the count reconstructs the sum without a join back to
    # the review rows.
    bayesian = ExpressionWrapper(
        (
            Value(prior * m)
            + Cast(F("rating_average"), FloatField()) * Cast(F("rating_count"), FloatField())
        )
        / (Value(prior) + Cast(F("rating_count"), FloatField())),
        output_field=FloatField(),
    )

    freshness = _freshness_expression(w["half_life_days"])

    return products.annotate(
        _bayesian_rating=bayesian,
        _freshness=freshness,
        trending_score=ExpressionWrapper(
            Value(w["view"]) * _log("view_count")
            + Value(w["purchase"]) * _log("purchase_count")
            + Value(w["wishlist"]) * _log("wishlist_count")
            + Value(w["review"]) * _log("review_count")
            + Value(w["rating"]) * bayesian
            + Value(w["recency"]) * freshness,
            output_field=FloatField(),
        ),
    )


def explain_score(product: Product, *, mean: float | None = None) -> dict[str, float]:
    """Break one product's score into its contributing terms.

    Powers the admin diagnostics page. Recomputed in Python from the same
    inputs so the breakdown adds up to the SQL total — merchandising asking
    "why is this ranked here" deserves an answer with numbers in it.
    """
    w = weights()
    m = store_mean_rating() if mean is None else mean
    prior = w["rating_prior"]

    rating_count = product.rating_count or 0
    bayesian = (prior * m + float(product.rating_average or 0) * rating_count) / (
        prior + rating_count
    )

    published = product.published_at or product.created_at
    age_days = max((timezone.now() - published).total_seconds() / 86400.0, 0.0)
    # Mirrors the ``CASE`` ladder in ``_freshness_expression`` step for step;
    # a smooth curve here would not match the number the ranking actually used.
    step = int(age_days // w["half_life_days"])
    freshness = 0.5**step if step < FRESHNESS_STEPS else 0.0

    terms = {
        "views": w["view"] * math.log1p(product.view_count or 0),
        "purchases": w["purchase"] * math.log1p(product.purchase_count or 0),
        "wishlist": w["wishlist"] * math.log1p(product.wishlist_count or 0),
        "reviews": w["review"] * math.log1p(product.review_count or 0),
        "rating": w["rating"] * bayesian,
        "recency": w["recency"] * freshness,
    }
    return {
        **{key: round(value, 4) for key, value in terms.items()},
        "bayesian_rating": round(bayesian, 4),
        "age_days": round(age_days, 1),
        "total": round(sum(terms.values()), 4),
    }
