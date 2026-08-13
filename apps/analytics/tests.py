"""Tests for the analytics and reporting module.

The risk in analytics is not a crash, it is a plausible wrong number. Most of
these tests exist to pin down what counts and what does not: cancelled orders
are not revenue, a refund reduces net but not gross, and a pending order is not
a sale.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.analytics import reports, services
from apps.analytics.validators import clamp_days, parse_window
from apps.catalog.models import Brand, Category, SubCategory
from apps.core.choices import OrderStatus, PaymentStatus
from apps.orders.models import Order, OrderItem
from apps.products.models import Product, ProductVariant, Size
from apps.users.models import User

STRONG_PASSWORD = "Tr3ndz!Shopper42"


class AnalyticsFixtureMixin:
    """Builds a small but complete sales history."""

    def build_world(self) -> None:
        """Create a catalogue, customers and a spread of orders."""
        cache.clear()
        self._order_seq = 0

        self.category = Category.objects.create(name="Women")
        self.other_category = Category.objects.create(name="Men")
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Dresses"
        )
        self.men_subcategory = SubCategory.objects.create(
            category=self.other_category, name="Shirts"
        )
        self.brand = Brand.objects.create(name="Nordwyn")
        self.other_brand = Brand.objects.create(name="Calloway")

        self.dress = self.make_product("Classic Midi Dress", "FT-A0001")
        self.shirt = self.make_product(
            "Oxford Shirt",
            "FT-A0002",
            category=self.other_category,
            subcategory=self.men_subcategory,
            brand=self.other_brand,
            selling_price=Decimal("900.00"),
        )

        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.stranger = User.objects.create_user(
            email="other@example.com", password=STRONG_PASSWORD, first_name="Rhea"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com",
            password=STRONG_PASSWORD,
            first_name="Staff",
            is_staff=True,
        )

    def make_product(self, name: str, sku: str, **extra: Any) -> Product:
        """Create a published product with one stocked variant."""
        defaults: dict[str, Any] = {
            "name": name,
            "sku": sku,
            "category": self.category,
            "subcategory": self.subcategory,
            "brand": self.brand,
            "mrp": Decimal("2000.00"),
            "selling_price": Decimal("1500.00"),
            "published_at": timezone.now() - timedelta(days=10),
        }
        defaults.update(extra)
        product = Product.objects.create(**defaults)
        ProductVariant.objects.create(
            product=product, sku=f"{sku}-0", color="Navy", size=Size.M, stock=10
        )
        return product

    def make_order(
        self,
        *,
        user: User | None = None,
        status_value: str = OrderStatus.DELIVERED,
        products: list[Product] | None = None,
        total: Decimal = Decimal("1500.00"),
        quantity: int = 1,
    ) -> Order:
        """Create an order carrying one line per product."""
        self._order_seq += 1
        order = Order.objects.create(
            user=user or self.user,
            order_number=f"FT-AN-{self._order_seq:05d}",
            status=status_value,
            payment_status=(
                PaymentStatus.PAID
                if status_value != OrderStatus.PENDING
                else PaymentStatus.PENDING
            ),
            shipping_address={"city": "Mumbai"},
            billing_address={"city": "Mumbai"},
            subtotal=total,
            grand_total=total,
            delivered_at=timezone.now()
            if status_value == OrderStatus.DELIVERED
            else None,
        )
        for product in products or [self.dress]:
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                product_slug=product.slug,
                brand_name=product.brand.name,
                sku=product.sku,
                mrp=product.mrp,
                selling_price=product.selling_price,
                quantity=quantity,
                subtotal=product.selling_price * quantity,
                grand_total=product.selling_price * quantity,
            )
        return order


class AnalyticsTestCase(AnalyticsFixtureMixin, TestCase):
    """Base case with the world built."""

    def setUp(self) -> None:
        self.build_world()


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------


class RevenueTests(AnalyticsTestCase):
    """What counts as money earned."""

    def test_a_delivered_order_is_revenue(self) -> None:
        self.make_order()
        self.assertEqual(services.get_revenue()["gross"], Decimal("1500.00"))

    def test_a_cancelled_order_is_not_revenue(self) -> None:
        # A dashboard that counts abandoned checkouts as revenue is worse than
        # no dashboard.
        self.make_order(status_value=OrderStatus.CANCELLED)
        self.assertEqual(services.get_revenue()["gross"], Decimal("0.00"))

    def test_a_pending_order_is_not_revenue(self) -> None:
        self.make_order(status_value=OrderStatus.PENDING)
        self.assertEqual(services.get_revenue()["gross"], Decimal("0.00"))

    def test_a_confirmed_order_is_revenue_before_delivery(self) -> None:
        self.make_order(status_value=OrderStatus.CONFIRMED)
        self.assertEqual(services.get_revenue()["orders"], 1)

    def test_an_empty_period_returns_zero_not_none(self) -> None:
        revenue = services.get_revenue()
        self.assertEqual(revenue["gross"], Decimal("0.00"))
        self.assertEqual(revenue["net"], Decimal("0.00"))

    def test_a_refund_reduces_net_but_not_gross(self) -> None:
        from apps.payments.models import Payment, PaymentState, Refund, RefundState

        order = self.make_order()
        payment = Payment.objects.create(
            order=order,
            gateway="razorpay",
            amount=Decimal("1500.00"),
            status=PaymentState.CAPTURED,
        )
        Refund.objects.create(
            payment=payment, amount=Decimal("500.00"), status=RefundState.PROCESSED
        )

        revenue = services.get_revenue()
        self.assertEqual(revenue["gross"], Decimal("1500.00"))
        self.assertEqual(revenue["net"], Decimal("1000.00"))

    def test_the_window_excludes_older_orders(self) -> None:
        order = self.make_order()
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(days=90)
        )
        start, end = services.period_bounds(30)
        self.assertEqual(services.get_revenue(start, end)["gross"], Decimal("0.00"))

    def test_average_order_value(self) -> None:
        self.make_order(total=Decimal("1000.00"))
        self.make_order(total=Decimal("2000.00"))
        self.assertEqual(services.get_average_order_value(), Decimal("1500.00"))

    def test_average_order_value_of_nothing_is_zero_not_a_crash(self) -> None:
        self.assertEqual(services.get_average_order_value(), Decimal("0.00"))

    def test_the_revenue_series_fills_quiet_days(self) -> None:
        # Without the fill the chart draws a line through a quiet week and
        # makes it look busy.
        self.make_order()
        series = services.get_revenue_series(7)

        self.assertEqual(len(series), 8)
        self.assertTrue(any(point["revenue"] > 0 for point in series))
        self.assertTrue(any(point["revenue"] == Decimal("0.00") for point in series))


# ---------------------------------------------------------------------------
# Orders and customers
# ---------------------------------------------------------------------------


class OrderAnalyticsTests(AnalyticsTestCase):
    """Order counts and the rates derived from them."""

    def test_counts_are_split_by_status(self) -> None:
        self.make_order()
        self.make_order(status_value=OrderStatus.CANCELLED)

        summary = services.get_order_summary()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["delivered"], 1)
        self.assertEqual(summary["cancelled"], 1)

    def test_cancellation_rate_is_a_percentage_of_all_orders(self) -> None:
        self.make_order()
        self.make_order(status_value=OrderStatus.CANCELLED)
        self.assertEqual(services.get_order_summary()["cancellation_rate"], 50.0)

    def test_rates_of_no_orders_are_zero_not_a_crash(self) -> None:
        summary = services.get_order_summary()
        self.assertEqual(summary["cancellation_rate"], 0.0)
        self.assertEqual(summary["fulfilment_rate"], 0.0)


class CustomerAnalyticsTests(AnalyticsTestCase):
    """Customer counts and the returning share."""

    def test_staff_are_not_counted_as_customers(self) -> None:
        self.assertEqual(services.get_customer_summary()["total"], 2)

    def test_a_second_order_makes_a_customer_returning(self) -> None:
        self.make_order()
        self.assertEqual(services.get_customer_summary()["returning"], 0)

        self.make_order()
        self.assertEqual(services.get_customer_summary()["returning"], 1)

    def test_returning_rate_is_a_share_of_buyers_not_of_registrations(self) -> None:
        self.make_order()
        self.make_order()
        self.make_order(user=self.stranger)

        summary = services.get_customer_summary()
        self.assertEqual(summary["buyers"], 2)
        self.assertEqual(summary["returning_rate"], 50.0)

    def test_top_customers_are_ranked_by_spend(self) -> None:
        self.make_order(total=Decimal("500.00"))
        self.make_order(user=self.stranger, total=Decimal("5000.00"))

        top = services.get_top_customers()
        self.assertEqual(top[0]["user__email"], self.stranger.email)


# ---------------------------------------------------------------------------
# Products, brands, categories
# ---------------------------------------------------------------------------


class ProductAnalyticsTests(AnalyticsTestCase):
    """Best sellers and catalogue health."""

    def test_top_products_rank_by_units(self) -> None:
        self.make_order(products=[self.dress], quantity=1)
        self.make_order(products=[self.shirt], quantity=5)

        top = services.get_top_products()
        self.assertEqual(top[0]["product_name"], self.shirt.name)

    def test_a_cancelled_order_does_not_make_a_best_seller(self) -> None:
        self.make_order(products=[self.dress], status_value=OrderStatus.CANCELLED)
        self.assertEqual(services.get_top_products(), [])

    def test_top_products_survive_a_deleted_product(self) -> None:
        # Order lines snapshot the name; last quarter's numbers must not change
        # because the catalogue did.
        self.make_order(products=[self.dress])
        name = self.dress.name
        self.dress.delete()

        top = services.get_top_products()
        self.assertEqual(top[0]["product_name"], name)

    def test_top_categories_are_ranked_by_revenue(self) -> None:
        self.make_order(products=[self.shirt], quantity=5)
        top = services.get_top_categories()
        self.assertEqual(top[0]["product__category__name"], self.other_category.name)

    def test_top_brands_use_the_snapshot(self) -> None:
        self.make_order(products=[self.dress])
        top = services.get_top_brands()
        self.assertEqual(top[0]["brand_name"], self.brand.name)

    def test_the_product_summary_counts_the_catalogue(self) -> None:
        summary = services.get_product_summary()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["active"], 2)


class InventoryAnalyticsTests(AnalyticsTestCase):
    """Stock health."""

    def test_low_stock_is_reported_scarcest_first(self) -> None:
        ProductVariant.objects.filter(product=self.dress).update(stock=1)
        ProductVariant.objects.filter(product=self.shirt).update(stock=4)

        low = services.get_low_stock()
        self.assertEqual(low[0]["stock"], 1)

    def test_an_empty_variant_is_out_of_stock_not_low_stock(self) -> None:
        ProductVariant.objects.filter(product=self.dress).update(stock=0)

        self.assertEqual(len(services.get_low_stock()), 0)
        self.assertEqual(len(services.get_out_of_stock()), 1)

    def test_the_inventory_summary_counts_units(self) -> None:
        summary = services.get_inventory_summary()
        self.assertEqual(summary["variants"], 2)
        self.assertEqual(summary["units_in_stock"], 20)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class DashboardTests(AnalyticsTestCase):
    """The headline payload."""

    def test_the_dashboard_returns_every_section(self) -> None:
        self.make_order()
        payload = services.get_dashboard(use_cache=False)

        for key in ("cards", "revenue_series", "orders", "customers", "inventory"):
            self.assertIn(key, payload)

    def test_growth_from_nothing_reports_one_hundred_percent(self) -> None:
        # Dividing by a zero baseline is undefined; reporting infinity makes the
        # card unreadable and reporting zero hides a launch.
        self.make_order()
        self.assertEqual(services.get_dashboard_cards()["revenue"]["change"], 100.0)

    def test_no_change_from_nothing_reports_zero(self) -> None:
        self.assertEqual(services.get_dashboard_cards()["revenue"]["change"], 0.0)

    def test_the_dashboard_is_cached(self) -> None:
        first = services.get_dashboard(30)
        self.make_order()
        self.assertEqual(services.get_dashboard(30), first)

    def test_invalidation_drops_the_cache(self) -> None:
        services.get_dashboard(30)
        self.make_order()
        services.invalidate_dashboard_cache()

        self.assertEqual(services.get_dashboard(30)["cards"]["orders"]["value"], 1)

    def test_warming_populates_every_window_the_ui_offers(self) -> None:
        self.assertEqual(services.warm_dashboard_cache()["warmed"], [7, 30, 90])

    def test_the_refund_queue_is_oldest_first(self) -> None:
        from apps.payments.models import Payment, PaymentState, Refund, RefundState

        order = self.make_order()
        payment = Payment.objects.create(
            order=order,
            gateway="razorpay",
            amount=Decimal("1500.00"),
            status=PaymentState.CAPTURED,
        )
        older = Refund.objects.create(
            payment=payment, amount=Decimal("100.00"), status=RefundState.PENDING
        )
        Refund.objects.create(
            payment=payment, amount=Decimal("200.00"), status=RefundState.PENDING
        )
        Refund.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timedelta(days=5)
        )

        self.assertEqual(services.get_refund_queue()[0].pk, older.pk)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class ReportTests(AnalyticsTestCase):
    """CSV generation."""

    def test_every_registered_report_generates(self) -> None:
        self.make_order()
        for key in reports.REPORTS:
            payload = reports.get_report(key).to_dict()
            self.assertIn("headers", payload, msg=key)

    def test_the_csv_header_matches_the_report(self) -> None:
        self.make_order()
        csv_text = reports.get_report("sales").to_csv()
        self.assertTrue(csv_text.startswith("Product,Slug,Brand,Units,Revenue"))

    def test_money_is_written_with_two_decimal_places(self) -> None:
        # A finance report that does not reconcile to the paisa is one nobody
        # trusts.
        self.make_order()
        self.assertIn("1500.00", reports.get_report("sales").to_csv())

    def test_an_unknown_report_names_the_known_ones(self) -> None:
        with self.assertRaises(KeyError) as caught:
            reports.get_report("profit_and_loss")
        self.assertIn("sales", str(caught.exception))

    def test_the_order_report_carries_one_row_per_order(self) -> None:
        self.make_order()
        self.make_order()
        self.assertEqual(len(reports.get_report("orders").rows()), 2)

    def test_the_filename_is_dated(self) -> None:
        self.assertIn(timezone.localdate().isoformat(), reports.filename_for("sales"))

    def test_the_catalogue_lists_every_report(self) -> None:
        self.assertEqual(len(reports.list_reports()), len(reports.REPORTS))


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class WindowTests(TestCase):
    """Query-string hygiene."""

    def test_a_mangled_days_value_falls_back(self) -> None:
        self.assertEqual(clamp_days("last tuesday", 30), 30)

    def test_an_enormous_window_is_capped_at_a_year(self) -> None:
        self.assertEqual(clamp_days(99999, 30), 365)

    def test_a_missing_window_defaults_to_the_last_n_days(self) -> None:
        start, end = parse_window(None, None, default_days=7)
        self.assertEqual((end - start).days, 7)

    def test_the_end_date_is_inclusive(self) -> None:
        # Asking for end=2026-08-04 and losing that day's orders is the classic
        # off-by-one in every reporting tool.
        _, end = parse_window("2026-08-01", "2026-08-04")
        self.assertEqual(end.hour, 23)

    def test_a_reversed_range_is_swapped_not_rejected(self) -> None:
        start, end = parse_window("2026-08-04", "2026-08-01")
        self.assertLess(start, end)

    def test_a_multi_year_range_is_capped(self) -> None:
        start, end = parse_window("2019-01-01", "2026-08-04")
        self.assertLessEqual((end - start).days, 366)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class AnalyticsAPITests(AnalyticsFixtureMixin, APITestCase):
    """The HTTP surface."""

    def setUp(self) -> None:
        self.build_world()
        self.make_order()

    def test_the_dashboard_requires_authentication(self) -> None:
        response = self.client.get(reverse("analytics:dashboard-summary"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_customer_cannot_read_revenue(self) -> None:
        # "It is only a GET" is how revenue ends up in a screenshot.
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("analytics:dashboard-revenue"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_read_the_dashboard(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("analytics:dashboard-summary"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("cards", response.json()["data"])

    def test_revenue_is_serialised_as_a_string_not_a_float(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("analytics:dashboard-revenue"))
        self.assertEqual(response.json()["data"]["gross"], "1500.00")

    def test_the_charts_endpoint_returns_both_series(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("analytics:dashboard-charts"))

        data = response.json()["data"]
        self.assertIn("revenue", data)
        self.assertIn("orders", data)

    def test_recent_orders(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("analytics:dashboard-recent-orders"))
        self.assertEqual(len(response.json()["data"]), 1)

    def test_low_stock_returns_both_lists(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("analytics:dashboard-low-stock"))

        data = response.json()["data"]
        self.assertIn("low_stock", data)
        self.assertIn("out_of_stock", data)

    def test_the_refund_queue_endpoint(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("analytics:dashboard-refund-queue"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_top_products(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("analytics:analytics-top-products"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 1)

    def test_the_report_catalogue_is_listed(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("analytics:report-list"))
        self.assertEqual(len(response.json()["data"]), len(reports.REPORTS))

    def test_a_report_previews_as_json(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse("analytics:report-detail", kwargs={"key": "sales"})
        )
        self.assertEqual(response.json()["data"]["key"], "sales")

    def test_a_report_downloads_as_csv(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse("analytics:report-download", kwargs={"key": "sales"})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_an_unknown_report_is_a_400_not_a_500(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse("analytics:report-detail", kwargs={"key": "nonsense"})
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------


class HealthCheckTests(APITestCase):
    """The monitoring endpoints."""

    def setUp(self) -> None:
        self.staff = User.objects.create_user(
            email="ops@example.com",
            password=STRONG_PASSWORD,
            first_name="Ops",
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="customer@example.com", password=STRONG_PASSWORD, first_name="Cust"
        )

    def test_health_is_public(self) -> None:
        # A load balancer has no credentials.
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_health_reports_the_database_and_cache(self) -> None:
        payload = self.client.get(reverse("core:health")).json()
        names = {check["name"] for check in payload["checks"]}
        self.assertEqual(names, {"database", "cache"})

    def test_health_is_not_wrapped_in_the_project_envelope(self) -> None:
        # Uptime monitors parse a fixed JSON path and should not have to know
        # about {success, message, data} to read a boolean.
        payload = self.client.get(reverse("core:health")).json()
        self.assertIn("healthy", payload)
        self.assertNotIn("data", payload)

    def test_an_anonymous_caller_cannot_request_deep_checks(self) -> None:
        payload = self.client.get(reverse("core:health"), {"deep": "true"}).json()
        self.assertEqual(len(payload["checks"]), 2)

    def test_staff_can_request_deep_checks(self) -> None:
        self.client.force_authenticate(user=self.staff)
        payload = self.client.get(reverse("core:health"), {"deep": "true"}).json()

        names = {check["name"] for check in payload["checks"]}
        self.assertIn("email", names)
        self.assertIn("celery", names)

    def test_readiness_is_public(self) -> None:
        response = self.client.get(reverse("core:ready"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["ready"])

    def test_status_is_staff_only(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("core:status"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_status_leaks_no_credentials(self) -> None:
        self.client.force_authenticate(user=self.staff)
        body = str(self.client.get(reverse("core:status")).json())

        self.assertNotIn(STRONG_PASSWORD, body)
        self.assertNotIn("SECRET", body.upper().replace("SECRET_KEY_CONFIGURED", ""))

    def test_system_information_is_staff_only(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("core:system"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_read_system_information(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("core:system"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("python", response.json()["data"])
