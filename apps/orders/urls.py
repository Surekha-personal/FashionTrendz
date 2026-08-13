"""URL routes for the orders module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.orders.views import CheckoutViewSet, OrderViewSet

app_name = "orders"

router = DefaultRouter()
router.register("checkout", CheckoutViewSet, basename="checkout")
router.register("orders", OrderViewSet, basename="order")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
