"""Admin dashboard, analytics and report APIs. Thin by construction."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.analytics import reports, services
from apps.orders.models import Order
from apps.analytics.permissions import IsAnalyticsViewer
from apps.analytics.serializers import (
    CustomerSummarySerializer,
    InventorySummarySerializer,
    OrderMetricsSerializer,
    ProductSummarySerializer,
    RecentOrderSerializer,
    RefundQueueSerializer,
    ReportListItemSerializer,
    ReportSerializer,
    RevenueSerializer,
    TopProductSerializer,
)
from apps.analytics.validators import clamp_days, parse_window
from apps.core.throttling import AnalyticsThrottle, ReportThrottle
from apps.reviews.serializers import ReviewModerationSerializer

DAYS_PARAM = OpenApiParameter(
    "days", int, description="Window length in days. Default 30, capped at 365."
)
WINDOW_PARAMS = [
    OpenApiParameter("start", str, description="ISO date, inclusive."),
    OpenApiParameter("end", str, description="ISO date, inclusive."),
]


class WindowMixin:
    """Resolves the date window a request is asking about.

    Shared by both viewsets so "days versus explicit dates" is decided once.
    An explicit ``start``/``end`` pair wins over ``days``; asking for both is a
    client bug, and honouring the more specific one is the kinder reading.
    """

    request: Request

    def window(self, default_days: int = 30) -> tuple[Any, Any]:
        """Return ``(start, end)`` for this request."""
        return parse_window(
            self.request.query_params.get("start"),
            self.request.query_params.get("end"),
            default_days=self.days(default_days),
        )

    def days(self, default: int = 30) -> int:
        """Return the requested window length, clamped."""
        return clamp_days(self.request.query_params.get("days"), default)


@extend_schema(tags=["Admin — Dashboard"], parameters=[DAYS_PARAM])
class DashboardViewSet(WindowMixin, viewsets.GenericViewSet):
    """The admin dashboard.

    ``summary`` returns everything the page renders in one payload; the other
    routes exist for widgets that refresh on their own.
    """

    permission_classes = [IsAnalyticsViewer]
    throttle_classes = [AnalyticsThrottle]
    pagination_class = None
    serializer_class = RevenueSerializer
    # Never queried — every figure is computed in services. Present so
    # drf-spectacular can introspect the viewset instead of warning.
    queryset = Order.objects.none()

    @extend_schema(summary="Everything the dashboard renders", responses={200: None})
    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        """Return the whole dashboard payload, cached."""
        from apps.core.responses import success_response

        return success_response(
            services.get_dashboard(self.days()), message="Dashboard retrieved."
        )

    @extend_schema(
        summary="Revenue", parameters=WINDOW_PARAMS, responses={200: RevenueSerializer}
    )
    @action(detail=False, methods=["get"])
    def revenue(self, request: Request) -> Response:
        """Return gross and net revenue with its components."""
        from apps.core.responses import success_response

        start, end = self.window()
        return success_response(
            RevenueSerializer(services.get_revenue(start, end)).data,
            message="Revenue retrieved.",
        )

    @extend_schema(
        summary="Orders",
        parameters=WINDOW_PARAMS,
        responses={200: OrderMetricsSerializer},
    )
    @action(detail=False, methods=["get"])
    def orders(self, request: Request) -> Response:
        """Return order counts and fulfilment rates."""
        from apps.core.responses import success_response

        start, end = self.window()
        return success_response(
            OrderMetricsSerializer(services.get_order_summary(start, end)).data,
            message="Order summary retrieved.",
        )

    @extend_schema(
        summary="Customers",
        parameters=WINDOW_PARAMS,
        responses={200: CustomerSummarySerializer},
    )
    @action(detail=False, methods=["get"])
    def customers(self, request: Request) -> Response:
        """Return customer counts and the returning-customer share."""
        from apps.core.responses import success_response

        start, end = self.window()
        return success_response(
            CustomerSummarySerializer(services.get_customer_summary(start, end)).data,
            message="Customer summary retrieved.",
        )

    @extend_schema(summary="Catalogue health", responses={200: ProductSummarySerializer})
    @action(detail=False, methods=["get"])
    def products(self, request: Request) -> Response:
        """Return catalogue counts."""
        from apps.core.responses import success_response

        return success_response(
            ProductSummarySerializer(services.get_product_summary()).data,
            message="Product summary retrieved.",
        )

    @extend_schema(summary="Revenue and order charts", responses={200: None})
    @action(detail=False, methods=["get"])
    def charts(self, request: Request) -> Response:
        """Return the two time series the dashboard plots."""
        from apps.core.responses import success_response

        days = self.days()
        return success_response(
            {
                "revenue": services.get_revenue_series(days),
                "orders": services.get_order_series(days),
                "monthly_revenue": services.get_monthly_revenue(),
            },
            message="Charts retrieved.",
        )

    @extend_schema(summary="Recent orders", responses={200: RecentOrderSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="recent-orders")
    def recent_orders(self, request: Request) -> Response:
        """Return the newest orders for the activity strip."""
        from apps.core.responses import success_response

        return success_response(
            RecentOrderSerializer(services.get_recent_orders(), many=True).data,
            message="Recent orders retrieved.",
        )

    @extend_schema(
        summary="Reviews awaiting moderation",
        responses={200: ReviewModerationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="pending-reviews")
    def pending_reviews(self, request: Request) -> Response:
        """Return the head of the moderation queue."""
        from apps.core.responses import success_response

        return success_response(
            ReviewModerationSerializer(services.get_pending_reviews(), many=True).data,
            message="Pending reviews retrieved.",
        )

    @extend_schema(summary="Low stock", responses={200: None})
    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request: Request) -> Response:
        """Return the reorder list and the out-of-stock list."""
        from apps.core.responses import success_response

        return success_response(
            {
                "summary": InventorySummarySerializer(
                    services.get_inventory_summary()
                ).data,
                "low_stock": services.get_low_stock(),
                "out_of_stock": services.get_out_of_stock(),
            },
            message="Inventory retrieved.",
        )

    @extend_schema(
        summary="Refunds awaiting action",
        responses={200: RefundQueueSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="refund-queue")
    def refund_queue(self, request: Request) -> Response:
        """Return refunds still owed to customers, oldest first."""
        from apps.core.responses import success_response

        return success_response(
            RefundQueueSerializer(services.get_refund_queue(), many=True).data,
            message="Refund queue retrieved.",
        )


@extend_schema(tags=["Admin — Analytics"], parameters=WINDOW_PARAMS)
class AnalyticsViewSet(WindowMixin, viewsets.GenericViewSet):
    """The analytics figures that are not on the dashboard."""

    permission_classes = [IsAnalyticsViewer]
    throttle_classes = [AnalyticsThrottle]
    pagination_class = None
    serializer_class = TopProductSerializer
    # Never queried — every figure is computed in services. Present so
    # drf-spectacular can introspect the viewset instead of warning.
    queryset = Order.objects.none()

    def _respond(self, payload: Any, message: str) -> Response:
        """Wrap a computed payload in the project envelope."""
        from apps.core.responses import success_response

        return success_response(payload, message=message)

    @extend_schema(summary="Sales", responses={200: None})
    @action(detail=False, methods=["get"])
    def sales(self, request: Request) -> Response:
        """Return units, lines and revenue for the window."""
        start, end = self.window()
        return self._respond(
            services.get_sales_summary(start, end), "Sales summary retrieved."
        )

    @extend_schema(summary="Top selling products", responses={200: TopProductSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="top-products")
    def top_products(self, request: Request) -> Response:
        """Return the best sellers by units."""
        start, end = self.window()
        return self._respond(
            services.get_top_products(self.days(10), start, end),
            "Top products retrieved.",
        )

    @extend_schema(summary="Top categories", responses={200: None})
    @action(detail=False, methods=["get"], url_path="top-categories")
    def top_categories(self, request: Request) -> Response:
        """Return revenue by category."""
        start, end = self.window()
        return self._respond(
            services.get_top_categories(10, start, end), "Top categories retrieved."
        )

    @extend_schema(summary="Top brands", responses={200: None})
    @action(detail=False, methods=["get"], url_path="top-brands")
    def top_brands(self, request: Request) -> Response:
        """Return revenue by brand."""
        start, end = self.window()
        return self._respond(
            services.get_top_brands(10, start, end), "Top brands retrieved."
        )

    @extend_schema(summary="Top customers", responses={200: None})
    @action(detail=False, methods=["get"], url_path="top-customers")
    def top_customers(self, request: Request) -> Response:
        """Return the highest-spending customers."""
        start, end = self.window()
        return self._respond(
            services.get_top_customers(10, start, end), "Top customers retrieved."
        )

    @extend_schema(summary="Payments", responses={200: None})
    @action(detail=False, methods=["get"])
    def payments(self, request: Request) -> Response:
        """Return payment volume and success rate."""
        start, end = self.window()
        return self._respond(
            services.get_payment_summary(start, end), "Payment analytics retrieved."
        )

    @extend_schema(summary="Refunds", responses={200: None})
    @action(detail=False, methods=["get"])
    def refunds(self, request: Request) -> Response:
        """Return refund volume, value and reasons."""
        start, end = self.window()
        return self._respond(
            services.get_refund_summary(start, end), "Refund analytics retrieved."
        )

    @extend_schema(summary="Coupons", responses={200: None})
    @action(detail=False, methods=["get"])
    def coupons(self, request: Request) -> Response:
        """Return redemptions and the discount they cost."""
        start, end = self.window()
        return self._respond(
            services.get_coupon_summary(start, end), "Coupon analytics retrieved."
        )

    @extend_schema(summary="Reviews", responses={200: None})
    @action(detail=False, methods=["get"])
    def reviews(self, request: Request) -> Response:
        """Return review volume and the rating spread."""
        start, end = self.window()
        return self._respond(
            services.get_review_summary(start, end), "Review analytics retrieved."
        )

    @extend_schema(summary="Inventory", responses={200: InventorySummarySerializer})
    @action(detail=False, methods=["get"])
    def inventory(self, request: Request) -> Response:
        """Return stock health."""
        return self._respond(
            InventorySummarySerializer(services.get_inventory_summary()).data,
            "Inventory analytics retrieved.",
        )


@extend_schema(tags=["Admin — Reports"], parameters=WINDOW_PARAMS)
class ReportViewSet(WindowMixin, viewsets.GenericViewSet):
    """Downloadable reports."""

    permission_classes = [IsAnalyticsViewer]
    # Reports walk thousands of rows; they get their own, tighter budget.
    throttle_classes = [ReportThrottle]
    pagination_class = None
    serializer_class = ReportSerializer
    # Never queried — every figure is computed in services. Present so
    # drf-spectacular can introspect the viewset instead of warning.
    queryset = Order.objects.none()
    lookup_field = "key"
    lookup_url_kwarg = "key"

    @extend_schema(summary="Available reports", responses={200: ReportListItemSerializer(many=True)})
    def list(self, request: Request) -> Response:
        """Return the report catalogue."""
        from apps.core.responses import success_response

        return success_response(
            reports.list_reports(), message="Reports retrieved."
        )

    @extend_schema(summary="Preview a report", responses={200: ReportSerializer})
    def retrieve(self, request: Request, key: str) -> Response:
        """Return a report as JSON, for an in-browser preview."""
        from apps.core.exceptions import BusinessRuleViolation
        from apps.core.responses import success_response

        try:
            report = reports.get_report(key)
        except KeyError as exc:
            raise BusinessRuleViolation(str(exc)) from exc

        start, end = self.window(90)
        return success_response(
            report.to_dict(start, end), message=f"{report.title} generated."
        )

    @extend_schema(
        summary="Download a report as CSV",
        responses={(200, "text/csv"): OpenApiParameter},
    )
    @action(detail=True, methods=["get"])
    def download(self, request: Request, key: str) -> HttpResponse:
        """Stream a report as a CSV attachment.

        Returns a bare ``HttpResponse``, not the project envelope: the client
        is a browser download, and wrapping a CSV in JSON would defeat the
        point of the endpoint.
        """
        from apps.core.exceptions import BusinessRuleViolation

        try:
            report = reports.get_report(key)
        except KeyError as exc:
            raise BusinessRuleViolation(str(exc)) from exc

        start, end = self.window(90)
        response = HttpResponse(report.to_csv(start, end), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="{reports.filename_for(key, start, end)}"'
        )
        return response
