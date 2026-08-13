"""URL routes for the banner module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.banner.views import BannerAdminViewSet, BannerViewSet

app_name = "banner"

router = DefaultRouter()
router.register("banners", BannerViewSet, basename="banner")
router.register("admin/banners", BannerAdminViewSet, basename="banner-admin")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
