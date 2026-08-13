"""Report generation.

Eight reports, all built the same way: a title, a header row, and rows pulled
from :mod:`apps.analytics.services`. Nothing here computes a figure — if a
report shows a number the dashboard also shows, both read the same function, so
they cannot disagree.

CSV output only, via :mod:`csv` from the standard library. Finance opens these
in Excel and immediately pivots them; a formatted PDF would be a picture of
data they then have to retype. ReportLab is already a dependency for invoices
if a rendered report is ever genuinely wanted.
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from decimal import Decimal
from typing import Any, Callable

from django.utils import timezone

from apps.analytics import services


class Report:
    """One report: a name, a header row and a row builder."""

    __slots__ = ("key", "title", "headers", "builder")

    def __init__(
        self,
        key: str,
        title: str,
        headers: list[str],
        builder: Callable[[Any, Any], list[list[Any]]],
    ) -> None:
        self.key = key
        self.title = title
        self.headers = headers
        self.builder = builder

    def rows(self, start: Any = None, end: Any = None) -> list[list[Any]]:
        """Build the report body for a window."""
        return self.builder(start, end)

    def to_csv(self, start: Any = None, end: Any = None) -> str:
        """Render the report as CSV text."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(self.headers)
        writer.writerows(_stringify(row) for row in self.rows(start, end))
        return buffer.getvalue()

    def to_dict(self, start: Any = None, end: Any = None) -> dict[str, Any]:
        """Render the report as JSON for an in-browser preview."""
        rows = self.rows(start, end)
        return {
            "key": self.key,
            "title": self.title,
            "headers": self.headers,
            "rows": [_stringify(row) for row in rows],
            "row_count": len(rows),
            "generated_at": timezone.now().isoformat(),
        }


def _stringify(row: list[Any]) -> list[Any]:
    """Coerce a row into CSV-safe values.

    ``Decimal`` is written as a plain string rather than a float: money read
    back through a float loses the last paisa, and a finance report that does
    not reconcile to the paisa is a finance report nobody trusts.
    """
    return [
        f"{value:.2f}" if isinstance(value, Decimal) else ("" if value is None else value)
        for value in row
    ]


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------


def _sales_rows(start: Any, end: Any) -> list[list[Any]]:
    """Best-selling products with units and revenue."""
    return [
        [
            row["product_name"],
            row["product_slug"],
            row["brand_name"],
            row["units"],
            row["revenue"],
        ]
        for row in services.get_top_products(limit=500, start=start, end=end)
    ]


def _revenue_rows(start: Any, end: Any) -> list[list[Any]]:
    """Daily revenue across the window.

    Falls back to the last 90 days when no window is given, because an
    unbounded daily series over a store's whole history is a spreadsheet nobody
    scrolls to the bottom of.
    """
    days = (end - start).days if (start and end) else 90
    return [
        [row["date"], row["orders"], row["revenue"]]
        for row in services.get_revenue_series(max(days, 1))
    ]


def _inventory_rows(start: Any, end: Any) -> list[list[Any]]:
    """Every variant at or below the reorder point, plus everything empty."""
    rows = [
        [
            row["product__name"],
            row["sku"],
            row["size"],
            row["color"],
            row["product__brand__name"] or "",
            row["stock"],
            "Low",
        ]
        for row in services.get_low_stock(limit=1000)
    ]
    rows += [
        [
            row["product__name"],
            row["sku"],
            row["size"],
            row["color"],
            "",
            0,
            "Out of stock",
        ]
        for row in services.get_out_of_stock(limit=1000)
    ]
    return rows


def _customer_rows(start: Any, end: Any) -> list[list[Any]]:
    """Highest-spending customers."""
    return [
        [
            row["user__email"],
            row["user__first_name"] or "",
            row["orders"],
            row["spent"],
        ]
        for row in services.get_top_customers(limit=500, start=start, end=end)
    ]


def _order_rows(start: Any, end: Any) -> list[list[Any]]:
    """Every order in the window, one row each."""
    from apps.orders.models import Order

    queryset = Order.objects.select_related("user").order_by("-created_at")
    if start:
        queryset = queryset.filter(created_at__gte=start)
    if end:
        queryset = queryset.filter(created_at__lte=end)

    return [
        [
            order.order_number,
            order.created_at.date().isoformat(),
            order.user.email if order.user_id else "",
            order.status,
            order.payment_status,
            order.payment_method,
            order.subtotal,
            order.discount + order.coupon_discount,
            order.tax,
            order.shipping_charge,
            order.grand_total,
        ]
        for order in queryset[:5000]
    ]


def _coupon_rows(start: Any, end: Any) -> list[list[Any]]:
    """Coupon redemptions and the discount each campaign cost."""
    return [
        [row["coupon__code"], row["redemptions"], row["discount"]]
        for row in services.get_coupon_summary(start, end)["top_coupons"]
    ]


def _payment_rows(start: Any, end: Any) -> list[list[Any]]:
    """Captured payment volume by gateway and by method."""
    summary = services.get_payment_summary(start, end)
    rows: list[list[Any]] = [
        ["gateway", row["gateway"], row["total"], row["value"]]
        for row in summary["by_gateway"]
    ]
    rows += [
        ["method", row["method"], row["total"], row["value"]]
        for row in summary["by_method"]
    ]
    return rows


def _review_rows(start: Any, end: Any) -> list[list[Any]]:
    """Rating distribution across approved reviews."""
    summary = services.get_review_summary(start, end)
    return [[row["rating"], row["total"]] for row in summary["by_rating"]]


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------

REPORTS: dict[str, Report] = {
    "sales": Report(
        "sales",
        "Sales by product",
        ["Product", "Slug", "Brand", "Units", "Revenue"],
        _sales_rows,
    ),
    "revenue": Report(
        "revenue",
        "Revenue by day",
        ["Date", "Orders", "Revenue"],
        _revenue_rows,
    ),
    "inventory": Report(
        "inventory",
        "Inventory status",
        ["Product", "SKU", "Size", "Colour", "Brand", "Stock", "Status"],
        _inventory_rows,
    ),
    "customers": Report(
        "customers",
        "Customers by spend",
        ["Email", "Name", "Orders", "Total spent"],
        _customer_rows,
    ),
    "orders": Report(
        "orders",
        "Orders",
        [
            "Order",
            "Date",
            "Customer",
            "Status",
            "Payment status",
            "Method",
            "Subtotal",
            "Discount",
            "Tax",
            "Shipping",
            "Total",
        ],
        _order_rows,
    ),
    "coupons": Report(
        "coupons",
        "Coupon redemptions",
        ["Code", "Redemptions", "Discount given"],
        _coupon_rows,
    ),
    "payments": Report(
        "payments",
        "Payments",
        ["Dimension", "Value", "Count", "Amount"],
        _payment_rows,
    ),
    "reviews": Report(
        "reviews",
        "Review ratings",
        ["Stars", "Reviews"],
        _review_rows,
    ),
}


def get_report(key: str) -> Report:
    """Return the report registered under ``key``."""
    try:
        return REPORTS[key]
    except KeyError as exc:
        raise KeyError(
            f"Unknown report {key!r}. Available: {', '.join(sorted(REPORTS))}"
        ) from exc


def list_reports() -> list[dict[str, str]]:
    """Return the report catalogue, for the admin's download menu."""
    return [
        {"key": report.key, "title": report.title} for report in REPORTS.values()
    ]


def filename_for(key: str, start: Any = None, end: Any = None) -> str:
    """Return a download filename that says what is inside it.

    Dated, because "sales.csv" in a downloads folder alongside four other
    "sales(1).csv" files is worthless a week later.
    """
    today = timezone.localdate().isoformat()
    if start and end:
        return f"fashion-trendz-{key}-{start.date()}-to-{end.date()}.csv"
    return f"fashion-trendz-{key}-{today}.csv"
