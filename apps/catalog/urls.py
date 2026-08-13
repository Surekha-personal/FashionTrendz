"""URL routes for the catalog module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.catalog.views import (
    BrandViewSet,
    CategoryViewSet,
    CollectionViewSet,
    SubCategoryViewSet,
)

app_name = "catalog"

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("subcategories", SubCategoryViewSet, basename="subcategory")
router.register("brands", BrandViewSet, basename="brand")
router.register("collections", CollectionViewSet, basename="collection")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
