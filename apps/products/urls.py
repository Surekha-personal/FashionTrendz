"""URL routes for the products module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.products.views import ProductTagViewSet, ProductViewSet

app_name = "products"

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("product-tags", ProductTagViewSet, basename="product-tag")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
