"""Recommendation serializers.

Every rail returns product cards, so ``ProductCardSerializer`` is reused
throughout rather than redefined. The classes here exist only for the payloads
that carry something *besides* a card — the co-purchase evidence, the score
breakdown, the diagnostics.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.products.serializers import ProductCardSerializer
from apps.recommendations.models import RecentlyViewed


class RecentlyViewedSerializer(serializers.ModelSerializer):
    """One entry in the browsing trail."""

    product = ProductCardSerializer(read_only=True)

    class Meta:
        model = RecentlyViewed
        fields = ("product", "viewed_at", "view_count")
        read_only_fields = fields


class RecordViewSerializer(serializers.Serializer):
    """Payload for recording a product view."""

    product = serializers.SlugField(max_length=255)


class BundleItemSerializer(serializers.Serializer):
    """One "frequently bought together" suggestion, with its evidence.

    The counts ship alongside the card deliberately. A rail that claims a
    pairing is frequent should be able to say how frequent, and merchandising
    reviewing the rail needs the number more than the shopper does.
    """

    product = ProductCardSerializer(read_only=True)
    co_purchase_count = serializers.IntegerField(read_only=True)
    confidence = serializers.FloatField(read_only=True)
    bundle_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )


class ScoreBreakdownSerializer(serializers.Serializer):
    """One product's trending score, term by term."""

    views = serializers.FloatField(read_only=True)
    purchases = serializers.FloatField(read_only=True)
    wishlist = serializers.FloatField(read_only=True)
    reviews = serializers.FloatField(read_only=True)
    rating = serializers.FloatField(read_only=True)
    recency = serializers.FloatField(read_only=True)
    bayesian_rating = serializers.FloatField(read_only=True)
    age_days = serializers.FloatField(read_only=True)
    total = serializers.FloatField(read_only=True)


class TrendingRowSerializer(serializers.Serializer):
    """One row of the admin trending leaderboard."""

    rank = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    brand = serializers.CharField(read_only=True, allow_blank=True)
    score = serializers.FloatField(read_only=True)
    breakdown = ScoreBreakdownSerializer(read_only=True)


class RailCountsSerializer(serializers.Serializer):
    """How many products each rail produced for one product."""

    related = serializers.IntegerField(read_only=True)
    similar = serializers.IntegerField(read_only=True)
    frequently_bought_together = serializers.IntegerField(read_only=True)
    customers_also_viewed = serializers.IntegerField(read_only=True)


class SignalsSerializer(serializers.Serializer):
    """The raw counters feeding a product's score."""

    views = serializers.IntegerField(read_only=True)
    purchases = serializers.IntegerField(read_only=True)
    wishlist_adds = serializers.IntegerField(read_only=True)
    reviews = serializers.IntegerField(read_only=True)
    rating_average = serializers.FloatField(read_only=True)
    rating_count = serializers.IntegerField(read_only=True)


class DiagnosticsSerializer(serializers.Serializer):
    """Why the engine recommends what it recommends for one product."""

    product = serializers.CharField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    trending_score = ScoreBreakdownSerializer(read_only=True)
    signals = SignalsSerializer(read_only=True)
    rails = RailCountsSerializer(read_only=True)
    affinity_edges = serializers.IntegerField(read_only=True)
    trail_rows = serializers.IntegerField(read_only=True)
