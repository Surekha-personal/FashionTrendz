"""URL routes for the wishlist module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.wishlist.views import WishlistViewSet

app_name = "wishlist"

router = DefaultRouter()
# Registered with an empty prefix so the routes read /api/v1/wishlist/ and
# /api/v1/wishlist/toggle/ rather than /wishlist/wishlist/.
router.register("wishlist", WishlistViewSet, basename="wishlist")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
