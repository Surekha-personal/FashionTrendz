"""URL routes for the cart module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.cart.views import CartViewSet

app_name = "cart"

router = DefaultRouter()
router.register("cart", CartViewSet, basename="cart")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
