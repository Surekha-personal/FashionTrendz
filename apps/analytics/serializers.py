"""Analytics serializers.

Thin, and mostly declarative. The analytics services return plain dicts of
already-computed figures, so these classes exist to document the response shape
in the OpenAPI schema rather than to transform anything.

Money is serialised as a string via ``DecimalField``, not as a float. JSON
floats cannot represent 1234.55 exactly, and a finance dashboard that is a
paisa out is a dashboard finance stops using.
"""

from __future__ import annotations

from rest_framework import serializers


class MoneyField(serializers.DecimalField):
    """A rupee amount. Two places, string on the wire."""

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)  # type: ignore[arg-type]


class RevenueSerializer(serializers.Serializer):
    """Gross revenue and its components."""

    gross = MoneyField()
    net = MoneyField()
    subtotal = MoneyField()
    discount = MoneyField()
    coupon_discount = MoneyField()
    tax = MoneyField()
    shipping = MoneyField()
    platform_fee = MoneyField()
    refunded = MoneyField()
    orders = serializers.IntegerField(read_only=True)


class RevenuePointSerializer(serializers.Serializer):
    """One day on the revenue chart."""

    date = serializers.CharField(read_only=True)
    revenue = MoneyField()
    orders = serializers.IntegerField(read_only=True)


class OrderMetricsSerializer(serializers.Serializer):
    """Order counts and the rates derived from them.

    Named "metrics" rather than "summary" to avoid colliding with
    ``orders.serializers.OrderSummarySerializer`` in the OpenAPI component
    namespace — two components with one name produce a schema that silently
    describes the wrong shape.
    """

    total = serializers.IntegerField(read_only=True)
    delivered = serializers.IntegerField(read_only=True)
    cancelled = serializers.IntegerField(read_only=True)
    pending = serializers.IntegerField(read_only=True)
    in_transit = serializers.IntegerField(read_only=True)
    cancellation_rate = serializers.FloatField(read_only=True)
    fulfilment_rate = serializers.FloatField(read_only=True)
    by_status = serializers.DictField(read_only=True)
    by_payment_status = serializers.DictField(read_only=True)


class CustomerSummarySerializer(serializers.Serializer):
    """Customer counts and the returning-customer share."""

    total = serializers.IntegerField(read_only=True)
    new = serializers.IntegerField(read_only=True)
    buyers = serializers.IntegerField(read_only=True)
    returning = serializers.IntegerField(read_only=True)
    returning_rate = serializers.FloatField(read_only=True)
    conversion_rate = serializers.FloatField(read_only=True)


class ProductSummarySerializer(serializers.Serializer):
    """Catalogue health."""

    total = serializers.IntegerField(read_only=True)
    active = serializers.IntegerField(read_only=True)
    published = serializers.IntegerField(read_only=True)
    out_of_stock = serializers.IntegerField(read_only=True)
    unrated = serializers.IntegerField(read_only=True)
    on_sale = serializers.IntegerField(read_only=True)


class InventorySummarySerializer(serializers.Serializer):
    """Stock health."""

    variants = serializers.IntegerField(read_only=True)
    units_in_stock = serializers.IntegerField(read_only=True)
    low_stock = serializers.IntegerField(read_only=True)
    out_of_stock = serializers.IntegerField(read_only=True)
    threshold = serializers.IntegerField(read_only=True)


class DashboardCardSerializer(serializers.Serializer):
    """One headline figure with its period-on-period change."""

    value = serializers.CharField(read_only=True)
    previous = serializers.CharField(read_only=True, required=False)
    change = serializers.FloatField(read_only=True, required=False)
    total = serializers.IntegerField(read_only=True, required=False)


class TopProductSerializer(serializers.Serializer):
    """One row of the best-sellers table."""

    product_id = serializers.IntegerField(read_only=True, allow_null=True)
    product_name = serializers.CharField(read_only=True)
    product_slug = serializers.CharField(read_only=True, allow_blank=True)
    brand_name = serializers.CharField(read_only=True, allow_blank=True)
    units = serializers.IntegerField(read_only=True)
    revenue = MoneyField()


class ReportListItemSerializer(serializers.Serializer):
    """One entry in the report catalogue."""

    key = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)


class ReportSerializer(serializers.Serializer):
    """A rendered report, for in-browser preview."""

    key = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    headers = serializers.ListField(child=serializers.CharField(), read_only=True)
    rows = serializers.ListField(read_only=True)
    row_count = serializers.IntegerField(read_only=True)
    generated_at = serializers.DateTimeField(read_only=True)


class RecentOrderSerializer(serializers.Serializer):
    """One row of the dashboard's activity strip."""

    order_number = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    payment_status = serializers.CharField(read_only=True)
    grand_total = MoneyField()
    currency = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    customer = serializers.SerializerMethodField()

    def get_customer(self, obj: object) -> str:
        """Return the buyer's email, or blank for a deleted account."""
        user = getattr(obj, "user", None)
        return getattr(user, "email", "") or ""


class RefundQueueSerializer(serializers.Serializer):
    """One refund awaiting action."""

    id = serializers.UUIDField(source="uuid", read_only=True)
    amount = MoneyField()
    currency = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    reason = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    order_number = serializers.CharField(
        source="payment.order.order_number", read_only=True
    )
