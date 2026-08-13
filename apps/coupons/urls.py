"""URL routes for the coupons module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.coupons.views import CouponViewSet

app_name = "coupons"

router = DefaultRouter()
router.register("coupons", CouponViewSet, basename="coupon")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
